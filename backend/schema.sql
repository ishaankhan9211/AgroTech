-- ==============================================================================
-- AgroTech Role-Based Platform Schema (Farmer, Provider, Admin)
-- Database: Supabase / PostgreSQL (Self-Contained & Production-Ready)
-- Run this in your Supabase SQL Editor (https://supabase.com/dashboard/project/_/sql)
-- ==============================================================================

-- Enable cryptographic extension for UUID generation
create extension if not exists pgcrypto;

-- Ensure schema usage permissions
grant usage on schema public to postgres, anon, authenticated, service_role;

-- ==============================================================================
-- 0. Schema Migration & Type Compatibility Check
-- Automatically converts any existing UUID columns to TEXT so foreign keys match!
-- ==============================================================================
do $$
declare
    r record;
begin
    -- 1. Drop existing foreign key constraints on public.users to allow type conversion
    for r in (
        select tc.table_schema, tc.table_name, tc.constraint_name
        from information_schema.table_constraints tc
        join information_schema.constraint_column_usage ccu
          on ccu.constraint_name = tc.constraint_name
          and ccu.table_schema = tc.table_schema
        where tc.constraint_type = 'FOREIGN KEY'
          and ccu.table_name = 'users'
          and ccu.column_name = 'id'
          and tc.table_schema = 'public'
    ) loop
        execute format('alter table %I.%I drop constraint if exists %I', r.table_schema, r.table_name, r.constraint_name);
    end loop;

    -- 2. Convert public.users.id from UUID to TEXT if needed
    if exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'users' and column_name = 'id' and data_type = 'uuid'
    ) then
        alter table public.users alter column id type text using id::text;
        alter table public.users alter column id set default gen_random_uuid()::text;
    end if;

    -- 3. Convert all referencing columns from UUID to TEXT if needed
    if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'services' and column_name = 'posted_by' and data_type = 'uuid') then
        alter table public.services alter column posted_by type text using posted_by::text;
    end if;

    if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'service_requests' and column_name = 'farmer_id' and data_type = 'uuid') then
        alter table public.service_requests alter column farmer_id type text using farmer_id::text;
    end if;

    if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'service_requests' and column_name = 'provider_id' and data_type = 'uuid') then
        alter table public.service_requests alter column provider_id type text using provider_id::text;
    end if;

    if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'complaints' and column_name = 'user_id' and data_type = 'uuid') then
        alter table public.complaints alter column user_id type text using user_id::text;
    end if;

    if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'alerts' and column_name = 'user_id' and data_type = 'uuid') then
        alter table public.alerts alter column user_id type text using user_id::text;
    end if;

    if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'alerts' and column_name = 'created_by' and data_type = 'uuid') then
        alter table public.alerts alter column created_by type text using created_by::text;
    end if;

    if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'notifications' and column_name = 'created_by' and data_type = 'uuid') then
        alter table public.notifications alter column created_by type text using created_by::text;
    end if;

    -- 4. Drop any outdated check constraints on tables so updated values are accepted
    for r in (
        select c.conname, t.relname
        from pg_constraint c
        join pg_class t on c.conrelid = t.oid
        join pg_namespace n on t.relnamespace = n.oid
        where c.contype = 'c'
          and n.nspname = 'public'
          and t.relname in ('users', 'services', 'service_requests', 'complaints', 'alerts', 'registration_otps')
    ) loop
        execute format('alter table public.%I drop constraint if exists %I', r.relname, r.conname);
    end loop;
end $$;

-- ==============================================================================
-- 1. Users Table (Farmer, Provider, Admin)
-- ==============================================================================
create table if not exists public.users (
  id text primary key default gen_random_uuid()::text,
  name text not null,
  email text not null unique,
  phone text not null,
  password_hash text not null,
  location text default '',
  role text not null default 'farmer' check (role in ('farmer', 'provider', 'seller', 'admin')),
  status text not null default 'active' check (status in ('active', 'blocked', 'pending', 'inactive')),
  created_at timestamptz not null default now()
);

-- ==============================================================================
-- 2. Services Table (Machinery, Equipment & Farm Supplies)
-- ==============================================================================
create table if not exists public.services (
  id bigint generated by default as identity primary key,
  name text not null,
  category text not null,
  price numeric(12, 2) not null,
  unit text not null default 'per day',
  description text default '',
  location text default '',
  image text default '',
  rating numeric(3, 2) default 4.5,
  reviews integer default 0,
  available boolean default true,
  status text not null default 'approved' check (status in ('pending', 'approved', 'rejected', 'active', 'inactive')),
  posted_by text references public.users(id) on delete set null,
  created_at timestamptz not null default now()
);

-- ==============================================================================
-- 3. Service Requests / Bookings Table
-- ==============================================================================
create table if not exists public.service_requests (
  id bigint generated by default as identity primary key,
  request_id text not null unique,
  farmer_id text references public.users(id) on delete set null,
  farmer_name text default '',
  farmer_phone text default '',
  provider_id text references public.users(id) on delete set null,
  service_id bigint references public.services(id) on delete set null,
  service_name text not null,
  quantity integer not null default 1,
  price numeric(12, 2) not null,
  payment_method text not null default 'cod',
  payment_status text not null default 'pending' check (payment_status in ('pending', 'paid', 'success', 'completed', 'failed', 'refunded')),
  status text not null default 'pending' check (status in ('pending', 'accepted', 'in_progress', 'rejected', 'confirmed', 'completed', 'cancelled')),
  address text default '',
  notes text default '',
  preferred_date text default '',
  created_at timestamptz not null default now()
);

-- ==============================================================================
-- 4. Complaints / Support Tickets Table
-- ==============================================================================
create table if not exists public.complaints (
  id bigint generated by default as identity primary key,
  user_id text references public.users(id) on delete set null,
  subject text not null,
  description text not null,
  priority text not null default 'medium' check (priority in ('low', 'medium', 'high')),
  status text not null default 'open' check (status in ('open', 'assigned', 'resolved', 'closed')),
  created_at timestamptz not null default now()
);

-- ==============================================================================
-- 5. Alerts & Notification Hub
-- ==============================================================================
create table if not exists public.alerts (
  id bigint generated by default as identity primary key,
  user_id text references public.users(id) on delete cascade,
  audience text not null default 'all' check (audience in ('all', 'farmer', 'provider', 'admin')),
  type text not null default 'system' check (type in ('request', 'status', 'system', 'promo', 'order', 'complaint', 'broadcast', 'alert')),
  title text not null default 'Notification',
  message text not null,
  is_read boolean not null default false,
  created_by text references public.users(id) on delete set null,
  created_at timestamptz not null default now()
);

-- Legacy Notifications Table
create table if not exists public.notifications (
  id bigint generated by default as identity primary key,
  audience text not null default 'all',
  message text not null,
  created_by text references public.users(id) on delete set null,
  created_at timestamptz not null default now()
);

-- ==============================================================================
-- 6. Registration OTPs Table
-- ==============================================================================
create table if not exists public.registration_otps (
  email text primary key,
  name text not null,
  phone text not null,
  password_hash text not null,
  location text default '',
  role text not null check (role in ('farmer', 'provider', 'seller', 'admin')),
  otp_code text default '',
  otp_hash text not null,
  expires_at timestamptz not null,
  attempts integer not null default 0 check (attempts >= 0),
  created_at timestamptz not null default now()
);

-- ==============================================================================
-- 7. High Performance Indexes
-- ==============================================================================
create index if not exists idx_users_email on public.users(email);
create index if not exists idx_users_role on public.users(role);
create index if not exists idx_users_status on public.users(status);
create index if not exists idx_services_posted_by on public.services(posted_by);
create index if not exists idx_services_category on public.services(category);
create index if not exists idx_services_available on public.services(available);
create index if not exists idx_services_status on public.services(status);
create index if not exists idx_service_requests_farmer on public.service_requests(farmer_id);
create index if not exists idx_service_requests_provider on public.service_requests(provider_id);
create index if not exists idx_service_requests_status on public.service_requests(status);
create index if not exists idx_complaints_user on public.complaints(user_id);
create index if not exists idx_complaints_status on public.complaints(status);
create index if not exists idx_alerts_user_id on public.alerts(user_id);
create index if not exists idx_alerts_audience on public.alerts(audience);
create index if not exists idx_alerts_is_read on public.alerts(is_read);
create index if not exists idx_registration_otps_expires_at on public.registration_otps(expires_at);

-- ==============================================================================
-- 8. Enforce Foreign Key Integrity
-- ==============================================================================
do $$
begin
    if not exists (select 1 from information_schema.table_constraints where constraint_name = 'services_posted_by_fkey' and table_schema = 'public') then
        alter table public.services add constraint services_posted_by_fkey foreign key (posted_by) references public.users(id) on delete set null;
    end if;
    if not exists (select 1 from information_schema.table_constraints where constraint_name = 'service_requests_farmer_id_fkey' and table_schema = 'public') then
        alter table public.service_requests add constraint service_requests_farmer_id_fkey foreign key (farmer_id) references public.users(id) on delete set null;
    end if;
    if not exists (select 1 from information_schema.table_constraints where constraint_name = 'service_requests_provider_id_fkey' and table_schema = 'public') then
        alter table public.service_requests add constraint service_requests_provider_id_fkey foreign key (provider_id) references public.users(id) on delete set null;
    end if;
    if not exists (select 1 from information_schema.table_constraints where constraint_name = 'complaints_user_id_fkey' and table_schema = 'public') then
        alter table public.complaints add constraint complaints_user_id_fkey foreign key (user_id) references public.users(id) on delete set null;
    end if;
    if not exists (select 1 from information_schema.table_constraints where constraint_name = 'alerts_user_id_fkey' and table_schema = 'public') then
        alter table public.alerts add constraint alerts_user_id_fkey foreign key (user_id) references public.users(id) on delete cascade;
    end if;
    if not exists (select 1 from information_schema.table_constraints where constraint_name = 'alerts_created_by_fkey' and table_schema = 'public') then
        alter table public.alerts add constraint alerts_created_by_fkey foreign key (created_by) references public.users(id) on delete set null;
    end if;

    -- Re-apply named check constraints so existing databases receive updates too.
    alter table public.users drop constraint if exists users_role_check;
    alter table public.users add constraint users_role_check check (role in ('farmer', 'provider', 'seller', 'admin'));
    if not exists (select 1 from pg_constraint c join pg_class t on c.conrelid = t.oid join pg_namespace n on t.relnamespace = n.oid where n.nspname = 'public' and t.relname = 'users' and c.conname = 'users_status_check') then
        alter table public.users add constraint users_status_check check (status in ('active', 'blocked', 'pending', 'inactive'));
    end if;
    if not exists (select 1 from pg_constraint c join pg_class t on c.conrelid = t.oid join pg_namespace n on t.relnamespace = n.oid where n.nspname = 'public' and t.relname = 'services' and c.conname = 'services_status_check') then
        alter table public.services add constraint services_status_check check (status in ('pending', 'approved', 'rejected', 'active', 'inactive'));
    end if;
    if not exists (select 1 from pg_constraint c join pg_class t on c.conrelid = t.oid join pg_namespace n on t.relnamespace = n.oid where n.nspname = 'public' and t.relname = 'service_requests' and c.conname = 'service_requests_status_check') then
        alter table public.service_requests add constraint service_requests_status_check check (status in ('pending', 'accepted', 'in_progress', 'rejected', 'confirmed', 'completed', 'cancelled'));
    end if;
    if not exists (select 1 from pg_constraint c join pg_class t on c.conrelid = t.oid join pg_namespace n on t.relnamespace = n.oid where n.nspname = 'public' and t.relname = 'service_requests' and c.conname = 'service_requests_payment_status_check') then
        alter table public.service_requests add constraint service_requests_payment_status_check check (payment_status in ('pending', 'paid', 'success', 'completed', 'failed', 'refunded'));
    end if;
    if not exists (select 1 from pg_constraint c join pg_class t on c.conrelid = t.oid join pg_namespace n on t.relnamespace = n.oid where n.nspname = 'public' and t.relname = 'complaints' and c.conname = 'complaints_priority_check') then
        alter table public.complaints add constraint complaints_priority_check check (priority in ('low', 'medium', 'high'));
    end if;
    if not exists (select 1 from pg_constraint c join pg_class t on c.conrelid = t.oid join pg_namespace n on t.relnamespace = n.oid where n.nspname = 'public' and t.relname = 'complaints' and c.conname = 'complaints_status_check') then
        alter table public.complaints add constraint complaints_status_check check (status in ('open', 'assigned', 'resolved', 'closed'));
    end if;
    if not exists (select 1 from pg_constraint c join pg_class t on c.conrelid = t.oid join pg_namespace n on t.relnamespace = n.oid where n.nspname = 'public' and t.relname = 'alerts' and c.conname = 'alerts_type_check') then
        alter table public.alerts add constraint alerts_type_check check (type in ('request', 'status', 'system', 'promo', 'order', 'complaint', 'broadcast', 'alert'));
    end if;
    if not exists (select 1 from pg_constraint c join pg_class t on c.conrelid = t.oid join pg_namespace n on t.relnamespace = n.oid where n.nspname = 'public' and t.relname = 'alerts' and c.conname = 'alerts_audience_check') then
        alter table public.alerts add constraint alerts_audience_check check (audience in ('all', 'farmer', 'provider', 'admin'));
    end if;
    if not exists (select 1 from pg_constraint c join pg_class t on c.conrelid = t.oid join pg_namespace n on t.relnamespace = n.oid where n.nspname = 'public' and t.relname = 'registration_otps' and c.conname = 'registration_otps_role_check') then
        alter table public.registration_otps add constraint registration_otps_role_check check (role in ('farmer', 'provider', 'seller', 'admin'));
    end if;
end $$;

-- ==============================================================================
-- 9. Row Level Security (RLS) & Policies
-- ==============================================================================
alter table public.users enable row level security;
alter table public.services enable row level security;
alter table public.service_requests enable row level security;
alter table public.complaints enable row level security;
alter table public.alerts enable row level security;
alter table public.notifications enable row level security;
alter table public.registration_otps enable row level security;

-- Drop existing policies to guarantee idempotent re-runs
drop policy if exists "service_role_all_users" on public.users;
drop policy if exists "public_read_users" on public.users;
drop policy if exists "service_role_all_services" on public.services;
drop policy if exists "public_read_services" on public.services;
drop policy if exists "service_role_all_requests" on public.service_requests;
drop policy if exists "service_role_all_alerts" on public.alerts;
drop policy if exists "service_role_all_complaints" on public.complaints;
drop policy if exists "service_role_all_notifications" on public.notifications;
drop policy if exists "service_role_all_registration_otps" on public.registration_otps;

-- Create clean policies
create policy "service_role_all_users" on public.users for all to service_role using (true) with check (true);
create policy "public_read_users" on public.users for select to anon, authenticated using (true);
create policy "service_role_all_services" on public.services for all to service_role using (true) with check (true);
create policy "public_read_services" on public.services for select to anon, authenticated using (true);
create policy "service_role_all_requests" on public.service_requests for all to service_role using (true) with check (true);
create policy "service_role_all_alerts" on public.alerts for all to service_role using (true) with check (true);
create policy "service_role_all_complaints" on public.complaints for all to service_role using (true) with check (true);
create policy "service_role_all_notifications" on public.notifications for all to service_role using (true) with check (true);
create policy "service_role_all_registration_otps" on public.registration_otps for all to service_role using (true) with check (true);

-- Grant Table Permissions
grant all privileges on all tables in schema public to postgres, anon, authenticated, service_role;
grant all privileges on all sequences in schema public to postgres, anon, authenticated, service_role;

-- ==============================================================================
-- 10. Seed Default Accounts (Admin, Farmer, Provider)
-- Passwords: admin123, farmer123, provider123
-- ==============================================================================
insert into public.users (id, name, email, phone, password_hash, location, role, status)
values
  (
    'usr-admin-01',
    'System Administrator',
    'admin@agrotech.com',
    '9876543210',
    'pbkdf2_sha256$09244fa07047fd617a1a7f31355bab9f$57b0f33a29c1c9a30de61bc9c4470495600e730136e38746883f760773f5e923',
    'National Head Office',
    'admin',
    'active'
  ),
  (
    'usr-farmer-01',
    'Madhur Pratap Singh',
    'farmer@agrotech.com',
    '8127059442',
    'pbkdf2_sha256$c8f69f55d74691cc7d397b014eb7400f$c8cdf3dc9a8f232504a25a9d62f869159b70da059e5f15de56681e7ae4b2c6aa',
    'Indore, MP',
    'farmer',
    'active'
  ),
  (
    'usr-provider-01',
    'Rajesh Patel (Kisan Agro Services)',
    'provider@agrotech.com',
    '9893012345',
    'pbkdf2_sha256$c9b9ead1e89bdb52f528d79f8344a80b$827b82a260d66d1dd506890d363027a37ef6e32a3194c727506d870e988f47ad',
    'Indore, MP',
    'provider',
    'active'
  )
on conflict (email) do update set
  role = excluded.role,
  status = excluded.status,
  phone = excluded.phone;

-- ==============================================================================
-- 11. Seed Initial Machinery, Equipment & Agricultural Services
-- ==============================================================================
insert into public.services (id, name, category, price, unit, description, image, rating, reviews, available, status, location, posted_by)
overriding system value
values
  (
    1,
    'Mahindra 575 DI Tractor Rental',
    'machinery',
    800.00,
    'per acre',
    'Powerful 45HP tractor suitable for ploughing, tilling, and heavy-duty farming tasks.',
    'https://5.imimg.com/data5/SELLER/Default/2021/6/CX/WL/RI/30912792/mahindra-tractor-yuvraj-bumper-1000x1000.jpg',
    4.8,
    128,
    true,
    'approved',
    'Indore, MP',
    'usr-provider-01'
  ),
  (
    2,
    'John Deere 5050 D Tractor',
    'machinery',
    1000.00,
    'per acre',
    'High-efficiency tractor with advanced hydraulics and rotary tiller attachment.',
    'https://cpimg.tistatic.com/10029058/b/4/John-deere-Tractors..jpg',
    4.9,
    95,
    true,
    'approved',
    'Bhopal, MP',
    'usr-provider-01'
  ),
  (
    3,
    'Modern Combine Harvester',
    'machinery',
    1200.00,
    'per acre',
    'Fast harvesting for wheat, soybean, and paddy. Reduces harvest loss significantly.',
    'https://5.imimg.com/data5/WC/IE/YH/ANDROID-86040604/prod-20200810-2031297210080910753376724-jpg-1000x1000.jpg',
    4.7,
    72,
    true,
    'approved',
    'Ujjain, MP',
    'usr-provider-01'
  ),
  (
    4,
    'Fieldking Heavy Rotavator',
    'machinery',
    500.00,
    'per acre',
    'Heavy-duty 7-feet rotavator for complete soil preparation and fine seedbed.',
    'https://www.fieldking.com/blogs/wp-content/uploads/2024/09/Ploughing.jpg',
    4.6,
    64,
    true,
    'approved',
    'Gwalior, MP',
    'usr-provider-01'
  ),
  (
    5,
    'Automatic Drip Irrigation Kit',
    'irrigation',
    3500.00,
    'per kit',
    'Complete drip system for 1 acre land. Saves up to 60% water and boosts yield.',
    'https://5.imimg.com/data5/SELLER/Default/2022/10/BC/MY/LI/21395960/drip-irrigation-system-1000x1000.jpg',
    4.8,
    89,
    true,
    'approved',
    'Indore, MP',
    'usr-provider-01'
  ),
  (
    6,
    'IFFCO DAP Fertilizer (50kg Bag)',
    'fertilizer',
    1350.00,
    'per bag',
    'Original certified DAP fertilizer for strong root growth and early crop establishment.',
    'https://5.imimg.com/data5/SELLER/Default/2022/5/NJ/VT/MB/26553143/dap-fertilizer-500x500.jpg',
    4.7,
    201,
    true,
    'approved',
    'Bhopal, MP',
    'usr-provider-01'
  ),
  (
    7,
    'HYV Premium Wheat Seeds (GW-322)',
    'seeds',
    450.00,
    'per kg',
    'Certified disease-resistant high yield wheat seeds with high germination rate.',
    'https://5.imimg.com/data5/SELLER/Default/2021/9/ZG/OS/PB/3131427/wheat-seeds-500x500.jpg',
    4.9,
    156,
    true,
    'approved',
    'Sehore, MP',
    'usr-provider-01'
  ),
  (
    8,
    '5-Ton Crop Transport Mini Truck',
    'transport',
    2500.00,
    'per trip',
    'Reliable door-to-mandi farm transport service with GPS tracking available 24/7.',
    'https://5.imimg.com/data5/SELLER/Default/2022/3/QF/XN/XJ/149399990/mini-truck-500x500.jpg',
    4.5,
    43,
    true,
    'approved',
    'Indore, MP',
    'usr-provider-01'
  )
on conflict (id) do update set
  name = excluded.name,
  price = excluded.price,
  available = excluded.available;

-- Reset sequence to continue after seeded IDs
select setval('public.services_id_seq', coalesce((select max(id) from public.services), 1), true);

-- ==============================================================================
-- 12. Seed Sample Service Requests / Bookings
-- ==============================================================================
insert into public.service_requests (
  id, request_id, farmer_id, farmer_name, farmer_phone, provider_id,
  service_id, service_name, quantity, price, payment_method, payment_status,
  status, address, notes, preferred_date
)
overriding system value
values
  (
    1,
    'REQ-1001',
    'usr-farmer-01',
    'Madhur Pratap Singh',
    '8127059442',
    'usr-provider-01',
    1,
    'Mahindra 575 DI Tractor Rental',
    2,
    1600.00,
    'cod',
    'pending',
    'accepted',
    'Indore Farm Sector 4',
    'Need for ploughing 2 acres land.',
    'Tomorrow 8:00 AM'
  ),
  (
    2,
    'REQ-1002',
    'usr-farmer-01',
    'Madhur Pratap Singh',
    '8127059442',
    'usr-provider-01',
    5,
    'Automatic Drip Irrigation Kit',
    1,
    3500.00,
    'upi',
    'paid',
    'pending',
    'Indore Farm Sector 4',
    'Installation assistance required.',
    'This weekend'
  )
on conflict (request_id) do nothing;

select setval('public.service_requests_id_seq', coalesce((select max(id) from public.service_requests), 1), true);

-- ==============================================================================
-- 13. Seed Sample Alerts & Announcements
-- ==============================================================================
insert into public.alerts (user_id, audience, type, title, message, is_read)
values
  (
    'usr-farmer-01',
    'farmer',
    'request',
    'Service Request Accepted ✅',
    'Your booking for Mahindra 575 DI Tractor has been accepted by the provider.',
    false
  ),
  (
    'usr-farmer-01',
    'farmer',
    'system',
    '🌾 Welcome to AgroTech!',
    'Explore available farm machinery, rental equipment and farm supplies in your region.',
    true
  ),
  (
    'usr-provider-01',
    'provider',
    'request',
    'New Booking Received 🚜',
    'Farmer Madhur Pratap Singh requested Mahindra 575 DI Tractor Rental.',
    false
  ),
  (
    null,
    'all',
    'promo',
    '🎉 Seasonal Harvesting Discounts',
    'Special 15% discount on combine harvesters and transport services this season.',
    false
  );
