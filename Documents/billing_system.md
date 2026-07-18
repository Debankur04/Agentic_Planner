# LogPose AI - Elixpo Pay Billing System

Billing now uses Elixpo Pay catalog sync. Products and prices are declared in `payouts.catalog.json`, pushed to Elixpo Pay with a server secret, and read back from the public catalog for the frontend pricing page.

## Plans

1. **Pirate**: Free tier. 15 messages/week.
2. **Warlord**: Paid tier. Rs. 99/month. 50 messages/week. Priority support.
3. **Emperor**: Custom tier. Custom monthly price and custom message limit.

## Catalog

- File: `payouts.catalog.json`
- Sync script: `node scripts/sync-catalog.mjs`
- Required env: `ELIXPO_PAY_API_KEY`
- Optional env: `ELIXPO_PAY_BASE_URL`, `ELIXPO_PAY_APP_ID`, `ELIXPO_PAY_PRODUCT_PAGE_URL`, `ELIXPO_PAY_CATALOG_PATH`
- Demo env: `DEMO_BILLING_PASSWORD`

Elixpo Pay sync returns HTTP 200 even when a product is rejected, so both the script and backend service inspect the response body and fail on `ok: false` or a non-empty `errors` array.

## API Endpoints

- `GET /billing/elixpo/catalog`: Reads the live public catalog from Elixpo Pay.
- `POST /billing/elixpo/checkout`: Returns the best checkout/product handoff URL for a requested tier.
- `POST /billing/elixpo/sync-catalog`: Admin-protected catalog sync using `ADMIN_PLAN_PASSWORD`.
- `POST /billing/demo/activate-warlord`: Activates a local Warlord entitlement for demos when the correct `DEMO_BILLING_PASSWORD` is supplied.
- `POST /billing/emperor/request`: Records a custom pricing request.

## Entitlements

The quota system still enforces access from the local `user_plans` table. When Elixpo Pay entitlement webhook details are available, webhook handling should update `user_plans` for grants, renewals, cancellations, and expirations.

For portfolio and interview demos, `/billing/demo/activate-warlord` proves the entitlement path without requiring a real payment. It updates `user_plans`, records a demo transaction, and the quota endpoint immediately reports the Warlord limit.
