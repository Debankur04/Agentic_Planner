from dotenv import load_dotenv
import os

from backend.supabase_client.db_operations import (
    create_warlord_plan,
    get_user_id_from_email,
    create_emperor_billing_transaction
)

load_dotenv()

ADMIN_PLAN_PASSWORD = os.getenv("ADMIN_PLAN_PASSWORD")
EMPEROR_COST_PER_REQUEST = float(
    os.getenv("EMPEROR_COST_PER_REQUEST", "1")
)


def emperor_key(email: str, amount: int, password: str):
    try:
        # Validate admin password
        if password != ADMIN_PLAN_PASSWORD:
            return {
                "success": False,
                "message": "Unauthorized request. Invalid admin password.",
            }

        # Validate amount
        if amount <= 0:
            return {
                "success": False,
                "message": "Amount must be greater than 0.",
            }

        # Prevent division issues
        if EMPEROR_COST_PER_REQUEST <= 0:
            return {
                "success": False,
                "message": "EMPEROR_COST_PER_REQUEST is misconfigured.",
            }

        # Calculate custom quota
        request_number = amount // EMPEROR_COST_PER_REQUEST

        if request_number <= 0:
            return {
                "success": False,
                "message": "Amount is too low for any Emperor quota allocation.",
            }

        # Lookup user
        user_lookup = get_user_id_from_email(email)

        if not user_lookup.get("success"):
            return {
                "success": False,
                "message": f"No user found with email: {email}",
            }

        user_id = user_lookup["user_id"]

        # Create / update plan
        response = create_warlord_plan(
            user_id=user_id,
            amount_paid=amount,
            weekly_limit=request_number,
        )


        if not response.get("success"):
            return {
                "success": False,
                "message": "Failed to activate Emperor plan.",
                "error": response.get("message"),
            }

        response_bill = create_emperor_billing_transaction(
            user_id=user_id,
            amount=amount,
            provider="admin"
        )

        if not response_bill.get("success"):
            return {
                "success": False,
                "message": "Failed to activate Emperor plan.",
                "error": response.get("message"),
            }

        return {
            "success": True,
            "message": "Emperor plan activated successfully.",
            "user_id": user_id,
            "email": email,
            "amount_paid": amount,
            "message_limit": request_number,
        }

    except Exception as e:
        print(f"[EMPEROR_PLAN_FAILED] {e}")

        return {
            "success": False,
            "message": "Unexpected error while processing Emperor plan.",
            "error": str(e),
        }