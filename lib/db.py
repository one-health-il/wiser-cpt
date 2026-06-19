"""Supabase data-access layer for WISER-CPT.

Tables (see schema.sql):
  * users     — username + bcrypt password hash
  * criteria  — one row per (username, criterion); locked originals plus the
                user's editable changed_* columns.

The app runs server-side with the service_role key (bypasses RLS). This module
works both inside Streamlit (reads st.secrets) and in plain scripts (parses
.streamlit/secrets.toml directly), so seed/migration scripts can reuse it.
"""
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd
import streamlit_authenticator as stauth
from supabase import Client, create_client

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data" / "criteria_master.csv"
SECRETS = ROOT / ".streamlit" / "secrets.toml"

# columns we expose as a DataFrame to the app (criterion_id aliased to 'id')
CRITERIA_COLUMNS = [
    "id", "section", "item", "source", "quote_from_source",
    "changed_criteria", "changed_source", "reviewed", "changed",
    "medically_necessary", "subjective_objective",
]


def _load_secrets() -> dict:
    """Return the [supabase] secrets, from st.secrets if available else file."""
    try:
        import streamlit as st
        if "supabase" in st.secrets:
            return dict(st.secrets["supabase"])
    except Exception:
        pass
    vals = {}
    for line in open(SECRETS):
        m = re.match(r'\s*(url|service_key|anon_key)\s*=\s*"([^"]+)"', line)
        if m:
            vals[m.group(1)] = m.group(2)
    return vals


@lru_cache(maxsize=1)
def get_client() -> Client:
    cfg = _load_secrets()
    base = cfg["url"].rstrip("/")
    if base.endswith("/rest/v1"):
        base = base[: -len("/rest/v1")]
    return create_client(base, cfg["service_key"])


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
def load_credentials() -> dict:
    """Build the credentials dict streamlit-authenticator expects."""
    rows = get_client().table("users").select("username,password").execute().data
    usernames = {
        r["username"]: {"name": r["username"], "email": "", "password": r["password"]}
        for r in rows
    }
    return {"usernames": usernames}


def user_exists(username: str) -> bool:
    res = (get_client().table("users")
           .select("username").eq("username", username.strip()).execute())
    return len(res.data) > 0


def add_user(username: str, password: str) -> tuple[bool, str]:
    username = username.strip()
    if not username:
        return False, "Username is required."
    if " " in username:
        return False, "Username cannot contain spaces."
    if not password:
        return False, "Password is required."
    if user_exists(username):
        return False, f"Username '{username}' is already taken."
    hashed = stauth.Hasher.hash(password)
    get_client().table("users").insert(
        {"username": username, "password": hashed}).execute()
    seed_user(username)  # give the new account its 34 criteria
    return True, f"Account '{username}' created."


# --------------------------------------------------------------------------- #
# Criteria
# --------------------------------------------------------------------------- #
def _master_rows(username: str) -> list[dict]:
    df = pd.read_csv(MASTER, dtype=str).fillna("")
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "username": username,
            "criterion_id": r["id"],
            "section": r["section"],
            "item": r["item"],
            "source": r["source"],
            "quote_from_source": r["verbatim_anchor"],
            "changed_criteria": "",
            "changed_source": "",
            "reviewed": "",
            "changed": "no",
            "medically_necessary": "",
            "subjective_objective": "",
        })
    return rows


def seed_user(username: str) -> None:
    """Insert the 34 master criteria for a user if they have none yet."""
    existing = (get_client().table("criteria")
                .select("row_id").eq("username", username).limit(1).execute())
    if existing.data:
        return
    get_client().table("criteria").insert(_master_rows(username)).execute()


def load_user(username: str) -> pd.DataFrame:
    """Return the user's criteria as a DataFrame (seeding on first use)."""
    seed_user(username)
    rows = (get_client().table("criteria")
            .select("*").eq("username", username).execute().data)
    df = pd.DataFrame(rows).rename(columns={"criterion_id": "id"})
    if df.empty:
        return pd.DataFrame(columns=["row_id"] + CRITERIA_COLUMNS)
    for c in CRITERIA_COLUMNS:           # tolerate a column not yet added
        if c not in df.columns:
            df[c] = ""
    df = df.sort_values("row_id").reset_index(drop=True)
    return df[["row_id"] + CRITERIA_COLUMNS].fillna("")


def update_criterion(username: str, criterion_id: str, values: dict) -> None:
    values = {**values, "updated_at": datetime.now(timezone.utc).isoformat()}
    (get_client().table("criteria").update(values)
     .eq("username", username).eq("criterion_id", criterion_id).execute())


def add_criterion(username: str, values: dict) -> None:
    row = {"username": username, **values}
    get_client().table("criteria").insert(row).execute()


def reset_user(username: str) -> None:
    """Delete all of the user's rows and reseed from master."""
    get_client().table("criteria").delete().eq("username", username).execute()
    get_client().table("criteria").insert(_master_rows(username)).execute()


def reset_criterion(username: str, criterion_id: str) -> None:
    """Restore a single criterion to its master state (clearing the user's
    edits/answers). For user-added criteria (not in master), just clear edits."""
    cleared = {"changed_criteria": "", "changed_source": "", "reviewed": "",
               "changed": "no", "medically_necessary": "",
               "subjective_objective": ""}
    master = pd.read_csv(MASTER, dtype=str).fillna("")
    m = master[master["id"] == criterion_id]
    if len(m):
        r = m.iloc[0]
        cleared.update({"item": r["item"], "source": r["source"],
                        "quote_from_source": r["verbatim_anchor"]})
    update_criterion(username, criterion_id, cleared)
