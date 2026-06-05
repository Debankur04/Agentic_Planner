import base64
import hmac
import os
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import requests

from backend.supabase_client.supabase_init import supabase_admin


class BillingService:
    WARLORD_AMOUNT_INR = 99
    WARLORD_AMOUNT_PAISE = 9900

    def __init__(self):
        self.key_id = os.getenv("RAZORPAY_KEY_ID", "")
        self.key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
        self.warlord_plan_id = os.getenv("RAZORPAY_WARLORD_PLAN_ID", "")
        self.currency = "INR"

    def _auth_header(self) -> str:
        token = base64.b64encode(f"{self.key_id}:{self.key_secret}".encode()).decode()
        return f"Basic {token}"

    def create_warlord_order(self, user_id: str) -> dict:
        if not self.key_id or not self.key_secret:
            raise RuntimeError("Razorpay credentials are not configured")

        if self.warlord_plan_id:
            payload = {
                "plan_id": self.warlord_plan_id,
                "total_count": 12,
                "quantity": 1,
                "notes": {"user_id": user_id, "tier": "Warlord"},
            }
            response = requests.post(
                "https://api.razorpay.com/v1/subscriptions",
                json=payload,
                headers={"Authorization": self._auth_header(), "Content-Type": "application/json"},
                timeout=15,
            )
            response.raise_for_status()
            subscription = response.json()
            self.record_transaction(
                user_id=user_id,
                order_id=subscription["id"],
                payment_id="",
                status="subscription_created",
                amount=self.WARLORD_AMOUNT_PAISE,
            )
            return {
                "subscription_id": subscription["id"],
                "key_id": self.key_id,
                "amount": self.WARLORD_AMOUNT_PAISE,
                "currency": self.currency,
                "tier": "Warlord",
            }

        receipt = f"warlord_{user_id}_{int(datetime.now(timezone.utc).timestamp())}"
        payload = {
            "amount": self.WARLORD_AMOUNT_PAISE,
            "currency": self.currency,
            "receipt": receipt,
            "notes": {"user_id": user_id, "tier": "Warlord"},
        }
        response = requests.post(
            "https://api.razorpay.com/v1/orders",
            json=payload,
            headers={"Authorization": self._auth_header(), "Content-Type": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        order = response.json()

        self.record_transaction(
            user_id=user_id,
            order_id=order["id"],
            payment_id="",
            status="created",
            amount=self.WARLORD_AMOUNT_PAISE,
        )
        return {
            "order_id": order["id"],
            "key_id": self.key_id,
            "amount": self.WARLORD_AMOUNT_PAISE,
            "currency": self.currency,
            "tier": "Warlord",
        }

    def verify_signature(self, order_id: str, payment_id: str, signature: str, subscription_id: str = "") -> bool:
        if subscription_id:
            message = f"{payment_id}|{subscription_id}".encode()
        else:
            message = f"{order_id}|{payment_id}".encode()
        expected = hmac.new(self.key_secret.encode(), message, sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        expected = hmac.new(self.key_secret.encode(), raw_body, sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def verify_warlord_payment(self, user_id: str, order_id: str, payment_id: str, signature: str, subscription_id: str = "") -> dict:
        reference_id = subscription_id or order_id
        if not self.verify_signature(order_id, payment_id, signature, subscription_id=subscription_id):
            self.record_transaction(user_id, reference_id, payment_id, "verification_failed", self.WARLORD_AMOUNT_PAISE)
            raise RuntimeError("Razorpay payment verification failed")

        now = datetime.now(timezone.utc)
        period_end = now + timedelta(days=30)
        status = "subscription_active" if subscription_id else "paid"
        self.record_transaction(user_id, reference_id, payment_id, status, self.WARLORD_AMOUNT_PAISE)
        self.upsert_user_plan(
            user_id=user_id,
            tier="Warlord",
            weekly_limit=50,
            billing_status="active",
            current_period_start=now,
            current_period_end=period_end,
        )
        return {
            "tier": "Warlord",
            "weekly_limit": 50,
            "billing_status": "active",
            "current_period_end": period_end.isoformat().replace("+00:00", "Z"),
        }

    def upsert_user_plan(self, user_id: str, tier: str, weekly_limit: int, billing_status: str, current_period_start: datetime | None = None, current_period_end: datetime | None = None):
        payload = {
            "user_id": user_id,
            "tier": tier,
            "weekly_limit": weekly_limit,
            "billing_status": billing_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if current_period_start:
            payload["current_period_start"] = current_period_start.isoformat()
        if current_period_end:
            payload["current_period_end"] = current_period_end.isoformat()
        return supabase_admin.table("user_plans").upsert(payload, on_conflict="user_id").execute()

    def record_transaction(self, user_id: str, order_id: str, payment_id: str, status: str, amount: int):
        try:
            return supabase_admin.table("billing_transactions").insert({
                "user_id": user_id,
                "provider": "razorpay",
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "amount": amount,
                "currency": self.currency,
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception:
            return None

    def create_emperor_request(self, user_id: str, message: str = "") -> dict:
        try:
            supabase_admin.table("emperor_requests").insert({
                "user_id": user_id,
                "message": message,
                "status": "open",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception:
            pass
        return {"message": "Emperor custom pricing request recorded."}

    def handle_webhook_event(self, payload: dict) -> dict:
        event = payload.get("event", "")
        entity = (
            payload.get("payload", {})
            .get("subscription", {})
            .get("entity")
        ) or (
            payload.get("payload", {})
            .get("payment", {})
            .get("entity")
        ) or {}
        notes = entity.get("notes") or {}
        user_id = notes.get("user_id")
        if not user_id:
            return {"handled": False, "reason": "missing_user_id"}

        if event in {"subscription.activated", "subscription.charged", "payment.captured"}:
            now = datetime.now(timezone.utc)
            self.upsert_user_plan(
                user_id=user_id,
                tier="Warlord",
                weekly_limit=50,
                billing_status="active",
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
            )
            self.record_transaction(
                user_id=user_id,
                order_id=entity.get("subscription_id") or entity.get("order_id") or entity.get("id", ""),
                payment_id=entity.get("id", ""),
                status=event,
                amount=int(entity.get("amount") or self.WARLORD_AMOUNT_PAISE),
            )
            return {"handled": True, "tier": "Warlord", "billing_status": "active"}

        if event in {"subscription.cancelled", "subscription.halted"}:
            plan = {
                "user_id": user_id,
                "tier": "Pirate",
                "weekly_limit": 15,
                "billing_status": "cancelled",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            supabase_admin.table("user_plans").upsert(plan, on_conflict="user_id").execute()
            return {"handled": True, "tier": "Pirate", "billing_status": "cancelled"}

        return {"handled": False, "reason": f"ignored_event:{event}"}
