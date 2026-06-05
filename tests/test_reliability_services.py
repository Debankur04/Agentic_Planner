import hmac
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import Mock

from llmops.model_router import ModelRouter
from service.billing_service import BillingService
from service.quota_service import QuotaService


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def incr(self, key):
        self.store[key] = int(self.store.get(key) or 0) + 1
        return self.store[key]

    def decr(self, key):
        self.store[key] = int(self.store.get(key) or 0) - 1
        return self.store[key]

    def expire(self, key, ttl):
        return True

    def delete(self, key):
        existed = key in self.store
        self.store.pop(key, None)
        return 1 if existed else 0

    def pipeline(self):
        return self

    def execute(self):
        return []


def test_quota_reservations_count_against_limit(monkeypatch):
    service = QuotaService(redis_client=FakeRedis(), limits={"Pirate": 1, "Warlord": 50, "Emperor": 999})
    monkeypatch.setattr(service, "get_user_plan", lambda user_id: {
        "tier": "Pirate",
        "weekly_limit": 1,
        "billing_status": "free",
    })
    monkeypatch.setattr(service, "get_weekly_usage", lambda user_id: 0)

    first = service.check_and_reserve_message("user1", "req1")
    second = service.check_and_reserve_message("user1", "req2")

    assert first.allowed is True
    assert second.allowed is False
    assert second.message == "Weekly message quota exceeded."


def test_razorpay_order_signature_verification():
    service = BillingService()
    service.key_secret = "secret"
    order_id = "order_123"
    payment_id = "pay_123"
    signature = hmac.new(
        service.key_secret.encode(),
        f"{order_id}|{payment_id}".encode(),
        sha256,
    ).hexdigest()

    assert service.verify_signature(order_id, payment_id, signature)
    assert not service.verify_signature(order_id, payment_id, "bad")


def test_model_router_uses_node_primary():
    config = {
        "models": {
            "mistral_medium": {"provider": "mistral", "model_name": "mistral-medium-latest"},
            "gemini": {"provider": "gemini", "model_name": "gemini-2.0-flash"},
        },
        "node_routing": {
            "intake": {"primary": "mistral_medium", "fallback": ["gemini"]},
        },
        "routing_rules": {},
    }
    router = ModelRouter(config)

    assert router.select_model("intake") == "mistral_medium"

    router.health["mistral_medium"].circuit_open = True
    router.health["mistral_medium"].circuit_open_until = 9999999999

    assert router.select_model("intake") == "gemini"
