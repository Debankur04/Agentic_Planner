import json
import re
from datetime import datetime, timezone
from typing import Any

from backend.supabase_client.supabase_init import supabase_admin
from backend.supabase_client.db_operations import get_conversation_memory


class ContextManager:
    def __init__(self, recent_limit: int = 8, memory_limit: int = 5, max_memory_chars: int = 600):
        self.recent_limit = recent_limit
        self.memory_limit = memory_limit
        self.max_memory_chars = max_memory_chars

    def _tokens(self, text: str) -> set[str]:
        return {t for t in re.findall(r"[a-zA-Z0-9]+", (text or "").lower()) if len(t) > 2}

    def get_recent_messages(self, conversation_id: str, limit: int | None = None) -> list[dict[str, str]]:
        limit = limit or self.recent_limit
        try:
            response = (
                supabase_admin
                .table("messages")
                .select("role, content, created_at")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            rows = list(reversed(response.data or []))
        except Exception:
            rows = []
        return [
            {"role": row.get("role", ""), "content": str(row.get("content", ""))[:1200]}
            for row in rows[-limit:]
        ]

    def retrieve_relevant_memories(self, user_id: str, conversation_id: str, query: str, trace=None) -> list[dict[str, Any]]:
        if trace:
            trace.record("memory_retrieval_start", {"user_id": user_id, "conversation_id": conversation_id})

        try:
            response = (
                supabase_admin
                .table("long_term_memories")
                .select("*")
                .eq("user_id", user_id)
                .order("importance", desc=True)
                .limit(50)
                .execute()
            )
            candidates = response.data or []
        except Exception as exc:
            if trace:
                trace.record("memory_retrieval_failed", {"error": str(exc)})
            return []

        query_terms = self._tokens(query)
        scored = []
        for row in candidates:
            text = str(row.get("memory_text", ""))
            tags = row.get("tags") or []
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = [tags]
            haystack = text + " " + " ".join(map(str, tags))
            score = len(query_terms.intersection(self._tokens(haystack))) + float(row.get("importance") or 0)
            if score > 0:
                scored.append((score, row))

        selected = [row for _, row in sorted(scored, key=lambda item: item[0], reverse=True)[:self.memory_limit]]
        if not selected:
            try:
                legacy_memory = get_conversation_memory(conversation_id)
                if legacy_memory:
                    selected = [{
                        "id": "legacy_conversation_memory",
                        "memory_text": str(legacy_memory)[:self.max_memory_chars],
                        "importance": 0,
                    }]
            except Exception:
                selected = []

        for row in selected:
            if row.get("id") == "legacy_conversation_memory":
                continue
            try:
                supabase_admin.table("long_term_memories").update({
                    "last_used_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", row["id"]).execute()
            except Exception:
                pass

        if trace:
            trace.record("memory_retrieval_end", {
                "memory_candidates_count": len(candidates),
                "memory_selected_count": len(selected),
                "memory_ids": [row.get("id") for row in selected],
            })
        return selected

    def build_context_bundle(self, user_id: str, conversation_id: str, current_query: str, trace=None) -> dict:
        recent = self.get_recent_messages(conversation_id)
        relevant = []
        relevant_text = "\n".join(
            f"- {str(row.get('memory_text', ''))[:self.max_memory_chars]}" for row in relevant
        )
        recent_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in recent[-self.recent_limit:]
        )
        return {
            "relevant_memory": relevant_text,
            "recent_messages": recent,
            "recent_messages_text": recent_text,
            "current_query": current_query,
            "memory_ids": [row.get("id") for row in relevant],
        }

    def store_memory(self, user_id: str, conversation_id: str, memory_text: str, memory_type: str = "travel_preference", tags: list[str] | None = None, importance: int = 1, trace=None):
        memory_text = str(memory_text or "").strip()
        if not memory_text:
            return None
        memory_text = memory_text[:self.max_memory_chars]

        try:
            response = supabase_admin.table("long_term_memories").insert({
                "user_id": user_id,
                "conversation_id": conversation_id,
                "memory_text": memory_text,
                "memory_type": memory_type,
                "tags": tags or [],
                "importance": importance,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_used_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            if trace:
                trace.record("memory_stored", {"memory_length": len(memory_text)})
            return response.data
        except Exception as exc:
            if trace:
                trace.record("memory_update_failed", {"error": str(exc)})
            return None

    def prune_user_memories(self, user_id: str, max_count: int = 100, trace=None):
        try:
            response = (
                supabase_admin
                .table("long_term_memories")
                .select("id")
                .eq("user_id", user_id)
                .order("importance", desc=True)
                .order("last_used_at", desc=True)
                .execute()
            )
            rows = response.data or []
            overflow = rows[max_count:]
            for row in overflow:
                supabase_admin.table("long_term_memories").delete().eq("id", row["id"]).execute()
            if trace and overflow:
                trace.record("memory_pruned", {"count": len(overflow)})
        except Exception as exc:
            if trace:
                trace.record("memory_prune_failed", {"error": str(exc)})
