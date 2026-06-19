"""Per-user criteria storage.

Each user works on an independent copy of the 34-criteria master, saved to
data/users/criteria_<user>.csv. On first access the user's file is seeded from
the canonical master so everyone starts from the same baseline; thereafter their
edits/adds/deletes never touch anyone else's copy or the master.
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data" / "criteria_master.csv"
USER_DIR = ROOT / "data" / "users"

COLUMNS = ["id", "section", "item", "source", "verbatim_anchor",
           "reviewed", "changed", "medically_necessary"]


def _safe(username: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", (username or "anon").strip().lower())


def user_path(username: str) -> Path:
    return USER_DIR / f"criteria_{_safe(username)}.csv"


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Conform to COLUMNS: add missing columns, drop legacy ones (type/when),
    and default 'changed' to 'no'."""
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df.reindex(columns=COLUMNS).fillna("")
    df.loc[df["changed"].str.strip() == "", "changed"] = "no"
    return df


def load_master() -> pd.DataFrame:
    return _ensure_columns(pd.read_csv(MASTER, dtype=str).fillna(""))


def load_user(username: str) -> pd.DataFrame:
    """Load the user's working copy, seeding it from master on first use."""
    path = user_path(username)
    if not path.exists():
        df = load_master()
        save_user(username, df)
        return df
    return _ensure_columns(pd.read_csv(path, dtype=str).fillna(""))


def save_user(username: str, df: pd.DataFrame) -> None:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    df = df.reindex(columns=COLUMNS).fillna("")
    df.to_csv(user_path(username), index=False)


def reset_user(username: str) -> pd.DataFrame:
    """Discard the user's edits and restore their copy from master."""
    df = load_master()
    save_user(username, df)
    return df


def update_row(df: pd.DataFrame, row_id: str, values: dict) -> pd.DataFrame:
    mask = df["id"] == row_id
    for col, val in values.items():
        if col in df.columns:
            df.loc[mask, col] = val
    return df


def delete_row(df: pd.DataFrame, row_id: str) -> pd.DataFrame:
    return df[df["id"] != row_id].reset_index(drop=True)


def add_row(df: pd.DataFrame, values: dict) -> pd.DataFrame:
    new = {c: values.get(c, "") for c in COLUMNS}
    return pd.concat([df, pd.DataFrame([new])], ignore_index=True)


def next_id_for_section(df: pd.DataFrame, section: str) -> str:
    """Auto-generate a unique id for a new criterion.

    If the section starts with a number (e.g. "2 · Conservative…"), continue
    that section's numbering (2.1, 2.2, … -> 2.6). Otherwise fall back to
    'new-1', 'new-2', …
    """
    existing = set(df["id"].astype(str))
    m = re.match(r"\s*(\d+)", section or "")
    if m:
        prefix = m.group(1)
        nums = []
        for i in existing:
            mm = re.match(rf"^{prefix}\.(\d+)$", str(i))
            if mm:
                nums.append(int(mm.group(1)))
        cand = f"{prefix}.{(max(nums) + 1) if nums else 1}"
        if cand not in existing:
            return cand
    n = 1
    while f"new-{n}" in existing:
        n += 1
    return f"new-{n}"
