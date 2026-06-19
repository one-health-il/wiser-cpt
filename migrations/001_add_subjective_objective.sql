-- Adds the subjective/objective answer column to an EXISTING criteria table.
-- Run once in the Supabase SQL Editor.
alter table public.criteria
    add column if not exists subjective_objective text not null default '';
