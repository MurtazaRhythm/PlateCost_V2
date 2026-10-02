-- Receipt sessions: one physical receipt, many ordered images.
-- Existing receipt tables stay in place so the folder-based pipeline keeps working.

create table if not exists public.restaurants (
    id         uuid primary key default gen_random_uuid(),
    owner_id   uuid not null unique references auth.users (id) on delete cascade,
    name       text not null default 'My Restaurant',
    created_at timestamptz not null default now()
);

create table if not exists public.receipt_sessions (
    id            uuid primary key default gen_random_uuid(),
    restaurant_id uuid not null references public.restaurants (id) on delete cascade,
    status        text not null default 'capturing'
                  check (status in ('capturing', 'uploading', 'processing', 'completed', 'failed')),
    created_at    timestamptz not null default now(),
    processed_at  timestamptz
);

alter table public.receipts
    add column if not exists receipt_session_id uuid unique references public.receipt_sessions (id) on delete cascade;

alter table public.receipts
    add column if not exists category text;

alter table public.receipt_items
    add column if not exists name text;

alter table public.receipt_items
    add column if not exists confidence numeric(4, 3);

alter table public.receipt_images
    alter column receipt_id drop not null;

alter table public.receipt_images
    add column if not exists receipt_session_id uuid references public.receipt_sessions (id) on delete cascade;

alter table public.receipt_images
    add column if not exists sequence_number integer;

alter table public.receipt_images
    add column if not exists image_url text;

alter table public.receipt_images
    add column if not exists created_at timestamptz not null default now();

update public.receipt_images
set sequence_number = page_order
where sequence_number is null;

update public.receipt_images
set image_url = storage_path
where image_url is null;

update public.receipt_items
set name = description
where name is null;

alter table public.receipt_images
    alter column sequence_number set not null;

alter table public.receipt_images
    drop constraint if exists receipt_images_owner_chk;

alter table public.receipt_images
    add constraint receipt_images_owner_chk
    check (receipt_id is not null or receipt_session_id is not null);

create index if not exists receipt_sessions_restaurant_created_idx
    on public.receipt_sessions (restaurant_id, created_at desc);

create index if not exists receipts_session_idx
    on public.receipts (receipt_session_id);

create index if not exists receipt_images_session_sequence_idx
    on public.receipt_images (receipt_session_id, sequence_number);

create unique index if not exists receipt_images_session_sequence_uidx
    on public.receipt_images (receipt_session_id, sequence_number)
    where receipt_session_id is not null;

create or replace function public.sync_receipt_item_name()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.name is null or btrim(new.name) = '' then
        new.name := new.description;
    elsif new.description is null or btrim(new.description) = '' then
        new.description := new.name;
    end if;
    return new;
end;
$$;

drop trigger if exists receipt_items_sync_name on public.receipt_items;
create trigger receipt_items_sync_name
    before insert or update on public.receipt_items
    for each row execute function public.sync_receipt_item_name();

create or replace function public.sync_receipt_image_fields()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if new.sequence_number is null then
        new.sequence_number := new.page_order;
    end if;
    if new.page_order is null then
        new.page_order := new.sequence_number;
    end if;
    if new.image_url is null then
        new.image_url := new.storage_path;
    end if;
    return new;
end;
$$;

drop trigger if exists receipt_images_sync_fields on public.receipt_images;
create trigger receipt_images_sync_fields
    before insert or update on public.receipt_images
    for each row execute function public.sync_receipt_image_fields();

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;

create or replace function private.current_restaurant_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
    select id from public.restaurants where owner_id = auth.uid() limit 1;
$$;

revoke all on function private.current_restaurant_id() from public, anon;
grant execute on function private.current_restaurant_id() to authenticated;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.restaurants (owner_id, name)
    values (
        new.id,
        coalesce(nullif(new.raw_user_meta_data->>'restaurant_name', ''), 'My Restaurant')
    )
    on conflict (owner_id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

alter table public.restaurants enable row level security;
alter table public.receipt_sessions enable row level security;

drop policy if exists "owners read own restaurant" on public.restaurants;
create policy "owners read own restaurant"
    on public.restaurants for select to authenticated
    using (owner_id = auth.uid());

drop policy if exists "owners read own sessions" on public.receipt_sessions;
create policy "owners read own sessions"
    on public.receipt_sessions for select to authenticated
    using (restaurant_id = private.current_restaurant_id());

drop policy if exists "owners read own receipts" on public.receipts;
create policy "owners read own receipts"
    on public.receipts for select to authenticated
    using (
        receipt_session_id in (
            select id from public.receipt_sessions
            where restaurant_id = private.current_restaurant_id()
        )
    );

drop policy if exists "owners read own receipt items" on public.receipt_items;
create policy "owners read own receipt items"
    on public.receipt_items for select to authenticated
    using (
        receipt_id in (
            select rec.id
            from public.receipts rec
            join public.receipt_sessions s on s.id = rec.receipt_session_id
            where s.restaurant_id = private.current_restaurant_id()
        )
    );

drop policy if exists "owners read own receipt taxes" on public.receipt_taxes;
create policy "owners read own receipt taxes"
    on public.receipt_taxes for select to authenticated
    using (
        receipt_id in (
            select rec.id
            from public.receipts rec
            join public.receipt_sessions s on s.id = rec.receipt_session_id
            where s.restaurant_id = private.current_restaurant_id()
        )
    );

drop policy if exists "owners read own receipt images" on public.receipt_images;
create policy "owners read own receipt images"
    on public.receipt_images for select to authenticated
    using (
        receipt_session_id in (
            select id from public.receipt_sessions
            where restaurant_id = private.current_restaurant_id()
        )
        or receipt_id in (
            select rec.id
            from public.receipts rec
            join public.receipt_sessions s on s.id = rec.receipt_session_id
            where s.restaurant_id = private.current_restaurant_id()
        )
    );

revoke all on function public.handle_new_user() from public, anon, authenticated;
drop function if exists public.current_restaurant_id();

grant select on public.restaurants to authenticated;
grant select on public.receipt_sessions to authenticated;
grant all on public.restaurants to service_role;
grant all on public.receipt_sessions to service_role;
