create table if not exists public.user_plans (
  user_id text primary key,
  tier text not null default 'Pirate',
  weekly_limit integer not null default 15,
  billing_status text not null default 'free',
  current_period_start timestamptz,
  current_period_end timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.quota_usage (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  week_start timestamptz not null,
  message_count integer not null default 0,
  updated_at timestamptz not null default now(),
  unique (user_id, week_start)
);

create table if not exists public.billing_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  provider text not null,
  razorpay_order_id text,
  razorpay_payment_id text,
  amount integer not null,
  currency text not null default 'INR',
  status text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.emperor_requests (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  message text,
  status text not null default 'open',
  created_at timestamptz not null default now()
);

create table if not exists public.long_term_memories (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  conversation_id text,
  memory_text text not null,
  memory_type text not null default 'travel_preference',
  tags jsonb not null default '[]'::jsonb,
  importance integer not null default 1,
  created_at timestamptz not null default now(),
  last_used_at timestamptz,
  expires_at timestamptz
);

create index if not exists idx_quota_usage_user_week
  on public.quota_usage (user_id, week_start);

create index if not exists idx_long_term_memories_user
  on public.long_term_memories (user_id, importance desc, last_used_at desc);

create index if not exists idx_billing_transactions_user
  on public.billing_transactions (user_id, created_at desc);

create or replace function public.increment_weekly_quota_usage(
  p_user_id text,
  p_week_start timestamptz
) returns void
language plpgsql
as $$
begin
  insert into public.quota_usage (user_id, week_start, message_count, updated_at)
  values (p_user_id, p_week_start, 1, now())
  on conflict (user_id, week_start)
  do update set
    message_count = public.quota_usage.message_count + 1,
    updated_at = now();
end;
$$;
