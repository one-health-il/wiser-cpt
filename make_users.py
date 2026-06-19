"""Create or update config.yaml with bcrypt-hashed credentials for the app.

Edit USERS below (plaintext passwords), then run:
    python make_users.py

Re-running re-hashes everyone. Share only the resulting config.yaml; never the
plaintext passwords. Users should change these after first login is set up.
"""
from copy import deepcopy
from pathlib import Path

import streamlit_authenticator as stauth
import yaml

ROOT = Path(__file__).parent
CONFIG = ROOT / "config.yaml"

# username -> (display name, email, plaintext password)
USERS = {
    "admin":   ("Admin",          "admin@one.health",   "changeme123"),
    "reviewer1": ("Reviewer One",  "rev1@one.health",   "changeme123"),
    "reviewer2": ("Reviewer Two",  "rev2@one.health",   "changeme123"),
}


def build_config():
    credentials = {"usernames": {}}
    for username, (name, email, pwd) in USERS.items():
        credentials["usernames"][username] = {
            "name": name,
            "email": email,
            "password": pwd,  # hashed below
        }
    # hash all plaintext passwords in place
    stauth.Hasher.hash_passwords(credentials)

    return {
        "credentials": credentials,
        "cookie": {
            "name": "wiser_cpt_auth",
            "key": "wiser-cpt-signing-key-change-me",
            "expiry_days": 7,
        },
    }


def main():
    config = build_config()
    with open(CONFIG, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    print(f"Wrote {CONFIG} with {len(USERS)} users: {', '.join(USERS)}")
    print("Default password for all users: change in make_users.py then re-run.")


if __name__ == "__main__":
    main()
