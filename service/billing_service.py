import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests

from backend.supabase_client.supabase_init import supabase_admin


class BillingService:
    """Elixpo Pay catalog and billing handoff integration."""

    DEFAULT_BASE_URL = "https://payouts.elixpo.com"
    DEFAULT_APP_ID = "logpose-ai"
    DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[1] / "payouts.catalog.json"

    def __init__(self):
        self.base_url = os.getenv("ELIXPO_PAY_BASE_URL", self.DEFAULT_BASE_URL).rstrip("/")
        self.api_key = os.getenv("ELIXPO_PAY_API_KEY", "")
        self.app_id = os.getenv("ELIXPO_PAY_APP_ID", self.DEFAULT_APP_ID)
        self.product_page_url = os.getenv("ELIXPO_PAY_PRODUCT_PAGE_URL", "")
        self.catalog_path = Path(os.getenv("ELIXPO_PAY_CATALOG_PATH", str(self.DEFAULT_CATALOG_PATH)))

    def load_local_catalog(self) -> dict:
        with self.catalog_path.open("r", encoding="utf-8") as catalog_file:
            return json.load(catalog_file)

    def sync_catalog(self) -> dict:
        if not self.api_key:
            raise RuntimeError("ELIXPO_PAY_API_KEY is not configured")

        catalog = self.load_local_catalog()
        response = requests.post(
            f"{self.base_url}/v1/sync",
            json=catalog,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Elixpo Pay sync returned invalid JSON") from exc

        errors = payload.get("errors") or []
        if not response.ok or payload.get("ok") is False or errors:
            raise RuntimeError(f"Elixpo Pay catalog sync failed: {errors or payload}")

        return payload

    def get_live_catalog(self) -> dict:
        response = requests.get(
            f"{self.base_url}/v1/catalog",
            params={"app": self.app_id},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def create_checkout_handoff(self, user_id: str, tier: str = "warlord", region: str = "IN", recurring: bool = True) -> dict:
        catalog = self.get_live_catalog()
        tier_key = tier.strip().lower()
        product = self._find_product(catalog, tier_key)
        if not product:
            raise RuntimeError(f"Elixpo Pay product tier '{tier_key}' was not found in the live catalog")

        price = self._find_price(product, region=region, recurring=recurring)
        checkout_url = self._extract_checkout_url(product, price)
        if not checkout_url:
            checkout_url = self._fallback_product_url(tier_key, user_id)

        return {
            "provider": "elixpo_pay",
            "checkout_url": checkout_url,
            "tier": product.get("tier") or tier_key,
            "product": product,
            "price": price or {},
        }

    def record_transaction(self, user_id: str, provider_reference: str, status: str, amount: int | None = None, currency: str = "INR"):
        try:
            payload = {
                "user_id": user_id,
                "provider": "elixpo_pay",
                "amount": amount,
                "currency": currency,
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "provider_reference": provider_reference,
            }
            return supabase_admin.table("billing_transactions").insert(payload).execute()
        except Exception:
            return None

    def create_emperor_request(self, user_id: str, message: str = "") -> dict:
        try:
            supabase_admin.table("emperor_requests").insert({
                "user_id": user_id,
                "message": message,
                "status": "open",
                "provider": "elixpo_pay",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception:
            pass
        return {"message": "Emperor custom pricing request recorded."}

    def activate_demo_warlord(self, user_id: str, activation_code: str) -> dict:
        expected_code = os.getenv("DEMO_BILLING_PASSWORD", "")
        if not expected_code or activation_code != expected_code:
            raise RuntimeError("Invalid demo activation code")

        now = datetime.now(timezone.utc)
        period_end = now + timedelta(days=30)
        payload = {
            "user_id": user_id,
            "tier": "Warlord",
            "weekly_limit": 50,
            "billing_status": "active",
            "monthly_price": 99,
            "subscription_source": "elixpo_pay_demo",
            "current_period_start": now.isoformat(),
            "current_period_end": period_end.isoformat(),
            "subscription_start_date": now.isoformat(),
            "subscription_expiry_date": period_end.isoformat(),
            "last_billed_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        supabase_admin.table("user_plans").upsert(payload, on_conflict="user_id").execute()
        self.record_transaction(
            user_id=user_id,
            provider_reference=f"demo_warlord_{int(now.timestamp())}",
            status="demo_activated",
            amount=9900,
            currency="INR",
        )
        return {
            "tier": "Warlord",
            "weekly_limit": 50,
            "billing_status": "active",
            "current_period_end": period_end.isoformat().replace("+00:00", "Z"),
            "message": "Demo Warlord entitlement activated.",
        }

    def _find_product(self, catalog: dict, tier: str) -> dict | None:
        products = catalog.get("products") or catalog.get("data", {}).get("products") or []
        for product in products:
            if str(product.get("tier", "")).lower() == tier:
                return product
        return None

    def _find_price(self, product: dict, region: str, recurring: bool) -> dict | None:
        prices = product.get("prices") or []
        preferred_type = "recurring" if recurring else "one_time"
        for price in prices:
            if price.get("type") == preferred_type and price.get("region", region) == region:
                return price
        for price in prices:
            if price.get("region", region) == region:
                return price
        return prices[0] if prices else None

    def _extract_checkout_url(self, product: dict, price: dict | None) -> str:
        candidates = [
            price or {},
            product,
        ]
        for source in candidates:
            for key in ("checkout_url", "payment_url", "url", "buy_url", "subscribe_url"):
                value = source.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value
        return ""

    def _fallback_product_url(self, tier: str, user_id: str) -> str:
        base = self.product_page_url or f"{self.base_url}/products/{self.app_id}"
        query = urlencode({"tier": tier, "user_id": user_id})
        separator = "&" if "?" in base else "?"
        return f"{base}{separator}{query}"
