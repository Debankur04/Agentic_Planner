from typing import List, Dict
from supabase_client.supabase_init import supabase_admin
from datetime import datetime


# ------------------ PREFERENCES ------------------ #

def add_preference(user_id: str, dietary_preference: str, preference_id: str) -> str:
    try:
        response = (
            supabase_admin
            .table('preferences')
            .insert({
                'user_id': user_id,
                'dietary_preference': dietary_preference,
                'preference_id': preference_id,
                'created_at': datetime.utcnow().isoformat()
            })
            .execute()
        )

        if not response.data:
            raise RuntimeError('Preference insertion returned empty response')

        return response.data[0]['id']

    except Exception as e:
        raise RuntimeError(f'[Preference INSERT FAILED] {str(e)}') from e


def update_preference(user_id: str, dietary_preference: str) -> str:
    try:
        response = (
            supabase_admin
            .table('preferences')
            .update({
                "dietary_preference": dietary_preference,
                "updated_at": datetime.utcnow().isoformat()
            })
            .eq("user_id", user_id)
            .execute()
        )

        if not response.data:
            raise RuntimeError("Preference update affected 0 rows")

        return "Preference updated successfully"

    except Exception as e:
        raise RuntimeError(f"[PREFERENCE UPDATE FAILED] {str(e)}") from e


def delete_preference(user_id: str) -> str:
    try:
        response = (
            supabase_admin
            .table('preferences')
            .delete()
            .eq("user_id", user_id)
            .execute()
        )

        if not response.data:
            raise RuntimeError("Preference delete affected 0 rows")

        return "Preference deleted successfully"

    except Exception as e:
        raise RuntimeError(f"[Preference DELETE FAILED] {str(e)}") from e


# ------------------ CONVERSATIONS ------------------ #

def create_conversation(user_id: str, title: str) -> str:
    try:
        response = (
            supabase_admin
            .table('conversations')
            .insert({
                'user_id': user_id,
                'title': title,
                'created_at': datetime.utcnow().isoformat()
            })
            .execute()
        )

        if not response.data:
            raise RuntimeError('Conversation Creation Failed')

        return response.data[0]['id']
    except Exception as e:
        raise RuntimeError(f'[Conversation INSERT FAILED] {str(e)}') from e


def delete_conversation(conversation_id: str) -> str:
    try:
        response = (
            supabase_admin
            .table('conversations')
            .delete()
            .eq("id", conversation_id)
            .execute()
        )

        if not response.data:
            raise RuntimeError("Conversation delete affected 0 rows")

        return "Conversation deleted successfully"

    except Exception as e:
        raise RuntimeError(f"[Conversation DELETE FAILED] {str(e)}") from e


# ------------------ MESSAGES ------------------ #

def add_message(user_id: str, conversation_id: str, role: str, content: str) -> str:
    try:
        response = (
            supabase_admin
            .table('messages')
            .insert({
                'user_id': user_id,
                'conversation_id': conversation_id,
                'role': role,
                'content': content,
                'created_at': datetime.utcnow().isoformat()
            })
            .execute()
        )

        if not response.data:
            raise RuntimeError('Message Creation Failed')

        return response.data[0]['id']

    except Exception as e:
        raise RuntimeError(f'[MESSAGE INSERT FAILED] {str(e)}') from e


def see_message(conversation_id: str) -> List[Dict]:
    try:
        response = (
            supabase_admin
            .table('messages')
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=False)
            .execute()
        )

        if response.data is None:
            raise RuntimeError("Failed to fetch messages")

        return response.data

    except Exception as e:
        raise RuntimeError(f"[FETCH MESSAGE FAILED] {str(e)}") from e