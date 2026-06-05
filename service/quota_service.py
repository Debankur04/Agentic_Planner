from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.supabase_client.supabase_init import supabase_admin


DEFAULT_LIMITS = {
    "Pirate": 15,
    "Warlord": 50,
    "Emperor": 999999,
}


@dataclass
class QuotaStatus:
    allowed: bool
    tier: str
    limit: int
    used: int
    remaining: int
    reset_at: str
    billing_status: str = "free"
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "tier": self.tier,
            "limit": self.limit,
            "used": self.used,
            "remaining": self.remaining,
            "reset_at": self.reset_at,
            "billing_status": self.billing_status,
            "message": self.message,
        }


class QuotaService:
    def __init__(self, redis_client=None, limits: dict | None = None):
        self.redis = redis_client
        self.limits = limits or DEFAULT_LIMITS

    def week_start(self, now: datetime | None = None) -> datetime:
        now = now or datetime.now(timezone.utc)
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)

    def week_end(self, now: datetime | None = None) -> datetime:
        return self.week_start(now) + timedelta(days=7)

    def get_user_plan(self, user_id: str) -> dict:
        try:
            response = (
                supabase_admin
                .table("user_plans")
                .select("*")
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            data = response.data or {}
        except Exception:
            data = {}

        tier = data.get("tier") or "Pirate"
        billing_status = data.get("billing_status") or ("free" if tier == "Pirate" else "active")
        weekly_limit = data.get("weekly_limit") or self.limits.get(tier, self.limits["Pirate"])

        if tier == "Warlord" and billing_status not in {"active", "trialing"}:
            tier = "Pirate"
            weekly_limit = self.limits["Pirate"]
            billing_status = "free"

        return {
            **data,
            "tier": tier,
            "weekly_limit": int(weekly_limit),
            "billing_status": billing_status,
        }

    def get_weekly_usage(self, user_id: str) -> int:
        start = self.week_start().isoformat()
        end = self.week_end().isoformat()
        try:
            response = (
                supabase_admin
                .table("quota_usage")
                .select("message_count")
                .eq("user_id", user_id)
                .eq("week_start", start)
                .single()
                .execute()
            )
            if response.data:
                return int(response.data.get("message_count") or 0)
        except Exception:
            pass

        try:
            response = (
                supabase_admin
                .table("messages")
                .select("id")
                .eq("role", "user")
                .gte("created_at", start)
                .lt("created_at", end)
                .execute()
            )
            return len(response.data or [])
        except Exception:
            return 0

    def get_status(self, user_id: str) -> QuotaStatus:
        plan = self.get_user_plan(user_id)
        used = self.get_weekly_usage(user_id)
        limit = int(plan["weekly_limit"])
        remaining = max(0, limit - used)
        return QuotaStatus(
            allowed=used < limit,
            tier=plan["tier"],
            limit=limit,
            used=used,
            remaining=remaining,
            reset_at=self.week_end().isoformat().replace("+00:00", "Z"),
            billing_status=plan["billing_status"],
        )

    def _reservation_count_key(self, user_id: str) -> str:
        return f"quota:reservations:user:{user_id}:week:{self.week_start().isoformat()}"

    def _reservation_key(self, request_id: str) -> str:
        return f"quota:reservation:{request_id}"

    def _reservation_ttl(self) -> int:
        return max(int((self.week_end() - datetime.now(timezone.utc)).total_seconds()), 60)

    def _active_reservation_count(self, user_id: str) -> int:
        if not self.redis:
            return 0
        try:
            return int(self.redis.get(self._reservation_count_key(user_id)) or 0)
        except Exception:
            return 0

    def check_and_reserve_message(self, user_id: str, request_id: str) -> QuotaStatus:
        status = self.get_status(user_id)
        reserved = self._active_reservation_count(user_id)
        if status.used + reserved >= status.limit:
            status.allowed = False
            status.remaining = 0
            status.message = "Weekly message quota exceeded."
            return status

        if not status.allowed:
            status.message = "Weekly message quota exceeded."
            return status

        if self.redis:
            ttl = self._reservation_ttl()
            reservation_key = self._reservation_key(request_id)
            count_key = self._reservation_count_key(user_id)
            pipe = self.redis.pipeline()
            pipe.setex(reservation_key, ttl, user_id)
            pipe.incr(count_key)
            pipe.expire(count_key, ttl)
            pipe.execute()
        return status

    def commit_message_usage(self, user_id: str, request_id: str):
        start = self.week_start().isoformat()
        try:
            rpc_done = False
            try:
                supabase_admin.rpc("increment_weekly_quota_usage", {
                    "p_user_id": user_id,
                    "p_week_start": start,
                }).execute()
                rpc_done = True
            except Exception:
                pass

            if not rpc_done:
                existing = (
                    supabase_admin
                    .table("quota_usage")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("week_start", start)
                    .single()
                    .execute()
                )
                if existing.data:
                    count = int(existing.data.get("message_count") or 0) + 1
                    supabase_admin.table("quota_usage").update({
                        "message_count": count,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", existing.data["id"]).execute()
                else:
                    supabase_admin.table("quota_usage").insert({
                        "user_id": user_id,
                        "week_start": start,
                        "message_count": 1,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }).execute()
        except Exception:
            pass

        if self.redis:
            self._release_reservation(user_id, request_id)

    def rollback_reservation(self, user_id: str, request_id: str):
        if self.redis:
            self._release_reservation(user_id, request_id)

    def _release_reservation(self, user_id: str, request_id: str):
        reservation_key = self._reservation_key(request_id)
        count_key = self._reservation_count_key(user_id)
        try:
            if self.redis.delete(reservation_key):
                remaining = self.redis.decr(count_key)
                if remaining <= 0:
                    self.redis.delete(count_key)
        except Exception:
            pass
