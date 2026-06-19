"""One-time setup: migrate existing accounts into Supabase and verify tables.

Prerequisite: run schema.sql in the Supabase SQL Editor first.

What it does:
  1. Confirms the `users` and `criteria` tables exist.
  2. Imports any accounts from users.csv into the `users` table (skips dupes).
  3. Seeds each user's 34 criteria (if they have none yet).

Run:  python setup_supabase.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "lib"))

import db  # noqa: E402

USERS_CSV = ROOT / "users.csv"


def check_tables():
    for table in ("users", "criteria"):
        try:
            db.get_client().table(table).select("*").limit(1).execute()
        except Exception as e:
            print(f"❌ Table '{table}' not reachable — did you run schema.sql? "
                  f"({str(e)[:120]})")
            sys.exit(1)
    print("✅ Tables 'users' and 'criteria' exist.")


def import_users():
    if not USERS_CSV.exists():
        print("• No users.csv to import.")
        return
    df = pd.read_csv(USERS_CSV, dtype=str).fillna("")
    client = db.get_client()
    for _, r in df.iterrows():
        u = r["username"].strip()
        if not u:
            continue
        if db.user_exists(u):
            print(f"• User '{u}' already in Supabase — skipping.")
            continue
        client.table("users").insert(
            {"username": u, "password": r["password"]}).execute()
        print(f"✅ Imported user '{u}'.")


def seed_all():
    rows = db.get_client().table("users").select("username").execute().data
    for r in rows:
        db.seed_user(r["username"])
        n = (db.get_client().table("criteria").select("row_id", count="exact")
             .eq("username", r["username"]).execute()).count
        print(f"✅ '{r['username']}' has {n} criteria.")


if __name__ == "__main__":
    check_tables()
    import_users()
    seed_all()
    print("\nDone. Supabase is ready.")
