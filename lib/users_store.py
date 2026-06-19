"""Account store backed by users.csv (columns: username, password).

Passwords are bcrypt-hashed. This is the source of truth for who can log in;
streamlit-authenticator consumes the credentials dict we build here and manages
the login session/cookie.

On first run, if users.csv is missing, it is seeded from any credentials already
in config.yaml (so the originally-created accounts keep working).
"""
from pathlib import Path

import pandas as pd
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

ROOT = Path(__file__).resolve().parent.parent
USERS_CSV = ROOT / "users.csv"
CONFIG = ROOT / "config.yaml"

COLUMNS = ["username", "password"]


def _seed_from_config() -> pd.DataFrame:
    rows = []
    if CONFIG.exists():
        cfg = yaml.load(open(CONFIG), Loader=SafeLoader) or {}
        for username, info in cfg.get("credentials", {}).get("usernames", {}).items():
            rows.append({"username": username, "password": info.get("password", "")})
    df = pd.DataFrame(rows, columns=COLUMNS)
    df.to_csv(USERS_CSV, index=False)
    return df


def _load_df() -> pd.DataFrame:
    if not USERS_CSV.exists():
        return _seed_from_config()
    return pd.read_csv(USERS_CSV, dtype=str).fillna("")


def load_credentials() -> dict:
    """Build the credentials dict streamlit-authenticator expects.
    The display name is just the username; email is unused."""
    df = _load_df()
    usernames = {}
    for _, r in df.iterrows():
        u = str(r["username"]).strip()
        if u:
            usernames[u] = {"name": u, "email": "", "password": r["password"]}
    return {"usernames": usernames}


def user_exists(username: str) -> bool:
    df = _load_df()
    return username.strip().lower() in set(df["username"].str.strip().str.lower())


def add_user(username: str, password: str) -> tuple[bool, str]:
    """Append a new account. Returns (ok, message)."""
    username = username.strip()
    if not username:
        return False, "Username is required."
    if " " in username:
        return False, "Username cannot contain spaces."
    if not password:
        return False, "Password is required."
    if user_exists(username):
        return False, f"Username '{username}' is already taken."

    df = _load_df()
    hashed = stauth.Hasher.hash(password)
    df = pd.concat(
        [df, pd.DataFrame([{"username": username, "password": hashed}])],
        ignore_index=True,
    )
    df.to_csv(USERS_CSV, index=False)
    return True, f"Account '{username}' created."
