-- Fresh database: run this file, then supabase/migrations/20261002_receipt_sessions.sql.
-- The migration adds restaurants, receipt sessions, and owner read policies.

create table if not exists public.receipts (
    id              uuid primary key default gen_random_uuid(),
    source_folder   text not null unique,
    vendor_name     text,
    vendor_address  text,
    vendor_phone    text,
    receipt_number  text,
    purchase_date   date,
    purchase_time   time,
    currency        text,
    subtotal        numeric(12, 2),
    discount_total  numeric(12, 2),
    tax_total       numeric(12, 2),
    tip             numeric(12, 2),
    total           numeric(12, 2),
    payment_method  text,
    card_last4      text,
    needs_review    boolean not null default false,
    review_notes    text[],
    raw_extraction  jsonb,
    model           text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create table if not exists public.receipt_items (
    id           uuid primary key default gen_random_uuid(),
    receipt_id   uuid not null references public.receipts (id) on delete cascade,
    line_number  integer not null,
    description  text not null,
    sku          text,
    quantity     numeric(12, 3),
    unit         text,
    unit_price   numeric(12, 2),
    total_price  numeric(12, 2),
    category     text
);

create table if not exists public.receipt_taxes (
    id          uuid primary key default gen_random_uuid(),
    receipt_id  uuid not null references public.receipts (id) on delete cascade,
    name        text,
    rate        numeric(6, 3),
    amount      numeric(12, 2)
);

create table if not exists public.receipt_images (
    id            uuid primary key default gen_random_uuid(),
    receipt_id    uuid not null references public.receipts (id) on delete cascade,
    page_order    integer not null,
    storage_path  text not null
);

create index if not exists receipt_items_receipt_id_idx  on public.receipt_items (receipt_id);
create index if not exists receipt_taxes_receipt_id_idx  on public.receipt_taxes (receipt_id);
create index if not exists receipt_images_receipt_id_idx on public.receipt_images (receipt_id);

-- Writes use the service role. Owner read policies are added with receipt sessions.
alter table public.receipts       enable row level security;
alter table public.receipt_items  enable row level security;
alter table public.receipt_taxes  enable row level security;
alter table public.receipt_images enable row level security;

insert into storage.buckets (id, name, public)
values ('receipts', 'receipts', false)
on conflict (id) do nothing;
