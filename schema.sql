-- WISER-CPT — Supabase / Postgres schema
-- Run ONCE in the Supabase dashboard:  SQL Editor -> New query -> paste -> Run.

-- 1) Accounts (mirrors the old users.csv: username + bcrypt password hash)
create table if not exists public.users (
    username   text primary key,
    password   text not null,
    created_at timestamptz not null default now()
);

-- 2) Per-user criteria — one row per (user, criterion).
--    item / source / quote_from_source = the LOCKED original (Box 1).
--    changed_criteria / changed_source = the user's EDITABLE copy (Box 2),
--    blank when unchanged. 'changed' is derived: 'yes' if either changed_*
--    column has content, else 'no'. Rows answered "No" are kept (soft-delete)
--    with medically_necessary = 'No'.
create table if not exists public.criteria (
    row_id              bigint generated always as identity primary key,
    username            text not null references public.users(username) on delete cascade,
    criterion_id        text not null,              -- e.g. "1.2"
    section             text,
    item                text,                       -- original criteria  (locked)
    source              text,                       -- original source    (locked)
    quote_from_source   text,                       -- original verbatim  (locked)
    changed_criteria    text not null default '',   -- user edit (blank if unchanged)
    changed_source      text not null default '',   -- user edit (blank if unchanged)
    reviewed            text not null default '',    -- 'yes' / ''
    changed             text not null default 'no',  -- 'yes' / 'no'  (derived)
    medically_necessary text not null default '',    -- 'Yes' / 'No' / ''
    updated_at          timestamptz not null default now(),
    unique (username, criterion_id)
);

create index if not exists criteria_username_idx on public.criteria (username);

-- The app connects with the service_role key from the Streamlit backend, which
-- bypasses RLS. RLS is therefore left disabled here. Do NOT expose the anon key
-- to a browser against these tables without first adding RLS policies.
