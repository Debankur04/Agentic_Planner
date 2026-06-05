# LogPose AI - Subscription & Billing System

## Overview
The billing system handles subscriptions, custom plans, and automated monthly invoice generation with PDF creation. It integrates tightly with the existing Quota system to limit user messaging capabilities based on their tier.

## Tiers
1. **Pirate**: Free tier. 15 messages/week.
2. **Warlord**: Paid tier. Costs ₹99/month. 50 messages/week. Priority support.
3. **Emperor**: Enterprise custom tier. Custom monthly price and custom message limit.

## Database Tables
### `user_plans`
- **Updated Columns**: `monthly_price`, `custom_message_limit`, `subscription_source`, `patreon_email`, `subscription_started_at`, `subscription_expires_at`, `last_billed_at`.
- Tracks the user's active tier, how much they pay, and their quota limit.

### `billing_invoices`
- **Columns**: `id`, `user_id`, `invoice_number`, `tier`, `amount`, `message_limit`, `invoice_month`, `status`, `pdf_path`, `created_at`, `updated_at`.
- Stores every monthly invoice generated. `pdf_path` points to a Supabase Storage bucket named `invoices`.

## Automated Invoicing (APScheduler)
A background job runs on the **1st of every month at midnight (00:00)** to generate invoices.
- **Service Method**: `billing_service.generate_monthly_invoices()`
- It queries all active paid plans, uses ReportLab to generate a PDF, uploads it to Supabase storage, and inserts a `billing_invoices` record.

## Admin Activation API
Protected by `ADMIN_PLAN_PASSWORD` environment variable.
- `POST /admin/activate-plan`: Sets a user's plan to any tier (typically Warlord).
- `POST /admin/activate-emperor`: Sets a user's plan to Emperor with custom limits.

## Supabase Storage
Ensure you have created a bucket named **`invoices`** in Supabase and made it public or restricted via policies. PDFs are saved at `invoices/YYYY/MM/<invoice_number>.pdf`.
