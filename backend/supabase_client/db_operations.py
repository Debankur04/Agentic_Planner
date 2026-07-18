from typing import List, Dict
from backend.supabase_client.supabase_init import supabase_admin
from datetime import datetime
from datetime import datetime, timedelta, timezone


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

def see_conversation(user_id:str):
    try:
        response = (
            supabase_admin
            .table('conversations')
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        )

        if response.data is None:
            raise RuntimeError("Failed to fetch messages")

        return response.data

    except Exception as e:
        raise RuntimeError(f"[FETCH MESSAGE FAILED] {str(e)}") from e

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
    

# ----------Preferences----------

def upsert_preference(user_id: str, dietary_preference: dict, custom_preference: str = None):
    """Single upsert function - handles both insert and update, avoiding duplicate key violations."""
    try:
        payload = {
            "user_id": user_id,
            "dietary_preference": dietary_preference,
            "custom_preference": custom_preference,
            "updated_at": datetime.utcnow().isoformat()
        }
        response = (
            supabase_admin
            .table("preferences")
            .upsert(payload, on_conflict="user_id")
            .execute()
        )

        if not response.data:
            raise RuntimeError("Upsert returned empty response")

        return {"message": "Preferences saved successfully", "data": response.data}

    except Exception as e:
        raise RuntimeError(f"[PREFERENCE UPSERT FAILED] {str(e)}") from e


def remove_preference(user_id: str):
    """Delete all preferences for a given user."""
    try:
        response = (
            supabase_admin
            .table("preferences")
            .delete()
            .eq("user_id", user_id)
            .execute()
        )
        return {"message": "Preference deleted successfully"}

    except Exception as e:
        raise RuntimeError(f"[PREFERENCE DELETE FAILED] {str(e)}") from e


def get_preference(user_id: str):
    try:
        response = (
            supabase_admin
            .table("preferences")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        return response.data or []

    except Exception as e:
        raise RuntimeError(f"[PREFERENCE FETCH FAILED] {str(e)}") from e
    



# add memory, get memory, update memory

def get_conversation_memory(conversation_id: str):
    try:
        response = (
            supabase_admin
            .table("conversations")
            .select("memory")
            .eq("id", conversation_id)
            .single()
            .execute()
        )

        if not response.data:
            return ""

        return response.data.get("memory", "")

    except Exception as e:
        raise RuntimeError(f"[GET MEMORY FAILED] {str(e)}") from e
    
def update_conversation_memory(conversation_id: str, memory: str):
    try:
        response = (
            supabase_admin
            .table("conversations")
            .update({"memory": memory})
            .eq("id", conversation_id)
            .execute()
        )

        return response.data

    except Exception as e:
        raise RuntimeError(f"[UPDATE MEMORY FAILED] {str(e)}") from e

def add_conversation_memory(conversation_id: str, memory: str = ""):
    try:
        response = (
            supabase_admin
            .table("conversations")
            .update({"memory": memory})
            .eq("id", conversation_id)
            .execute()
        )

        return response.data

    except Exception as e:
        raise RuntimeError(f"[ADD MEMORY FAILED] {str(e)}") from e
    

def get_user_id_from_email(email: str):
    try:
        users = supabase_admin.auth.admin.list_users()

        for user in users:
            if user.email and user.email.lower() == email.lower():
                return {
                    "success": True,
                    "user_id": user.id,
                    "email": user.email,
                }

        return {
            "success": False,
            "message": f"No user found with email {email}",
        }

    except Exception as e:
        print(f"[GET_USER_BY_EMAIL_FAILED] {e}")

        return {
            "success": False,
            "message": str(e),
        }




def create_warlord_plan(
    user_id: str,
    amount_paid: int = 99,
    weekly_limit: int = 50,
):
    try:
        now = datetime.now(timezone.utc)

        payload = {
            "user_id": user_id,
            "tier": "Warlord",
            "weekly_limit": weekly_limit,
            "billing_status": "active",
            "monthly_price": amount_paid,
            "custom_message_limit": None,
            "subscription_source": "manual",
            "patreon_email": None,
            "current_period_start": now.isoformat(),
            "current_period_end": (now + timedelta(days=30)).isoformat(),
            "subscription_start_date": now.isoformat(),
            "subscription_expiry_date": (now + timedelta(days=30)).isoformat(),
            "last_billed_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        existing = (
            supabase_admin
            .table("user_plans")
            .select("user_id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

        rows = existing.data or []

        if rows:
            result = (
                supabase_admin
                .table("user_plans")
                .update(payload)
                .eq("user_id", user_id)
                .execute()
            )
        else:
            result = (
                supabase_admin
                .table("user_plans")
                .insert(payload)
                .execute()
            )

        return {
            "success": True,
            "message": "Warlord plan activated successfully",
            "data": result.data,
        }

    except Exception as e:
        print(f"[CREATE_WARLORD_PLAN_FAILED] {e}")

        return {
            "success": False,
            "message": str(e),
        }
    
def create_emperor_billing_transaction(
    user_id: str,
    amount: int,
    provider: str = "manual",
    currency: str = "INR",
):
    """
    Create a billing transaction for an Emperor purchase.

    Args:
        user_id: Supabase user UUID
        amount: Amount paid in INR
        provider: manual / patreon / admin
        currency: INR by default

    Returns:
        dict
    """

    try:
        response = (
            supabase_admin
            .table("billing_transactions")
            .insert({
                "user_id": user_id,
                "provider": provider,
                "amount": amount,
                "currency": currency,
                "status": "paid",
                "created_at": datetime.now(timezone.utc).isoformat(),

                "razorpay_order_id": None,
                "razorpay_payment_id": None,
            })
            .execute()
        )

        return {
            "success": True,
            "message": "Billing transaction created successfully.",
            "data": response.data,
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to create billing transaction: {str(e)}",
        }
