"""WISER-CPT — Medical-Necessity Criteria Review

Streamlit app for the Clinical Compliance / RCM team to review, edit, add, and
confirm the 34 skin-substitute medical-necessity criteria, cross-referencing
each against the verbatim quote highlighted in its source document.

Backend: Supabase (lib/db.py). Two pages: "Login" and "Criteria Review".

Run:  streamlit run app.py
"""
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit_authenticator as stauth

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "lib"))

import db                       # noqa: E402
import pdf_highlight as ph      # noqa: E402
import sources as src           # noqa: E402

st.set_page_config(page_title="WISER-CPT · Necessity Criteria", layout="wide")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def truncate_words(text: str, limit: int = 45) -> str:
    """Shorten without cutting a word: finish the word, then add '...'."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    finish = re.match(r"\S*", text[limit:]).group(0)
    return (text[:limit] + finish).rstrip(" :;,.-") + "..."


def section_title(section: str) -> str:
    """'1 · Wound Type…' -> 'Section 1 · Wound Type…'."""
    m = re.match(r"\s*(\d+)\s*[·\-:.]?\s*(.*)$", section or "")
    if m:
        rest = m.group(2).strip()
        return f"Section {m.group(1)} · {rest}" if rest else f"Section {m.group(1)}"
    return section or "Section"


def strike(text: str) -> str:
    """Render plain text with a strikethrough (combining overlay per char)."""
    return "".join(ch + "̶" for ch in text)


def next_id(df: pd.DataFrame, section: str) -> str:
    """Continue a section's numbering (e.g. 2.x -> 2.6); else 'new-N'."""
    existing = set(df["id"].astype(str))
    m = re.match(r"\s*(\d+)", section or "")
    if m:
        prefix = m.group(1)
        nums = [int(mm.group(1)) for i in existing
                if (mm := re.match(rf"^{prefix}\.(\d+)$", str(i)))]
        cand = f"{prefix}.{(max(nums) + 1) if nums else 1}"
        if cand not in existing:
            return cand
    n = 1
    while f"new-{n}" in existing:
        n += 1
    return f"new-{n}"


@st.cache_data(show_spinner=False)
def cached_analyze(path_str: str, anchor: str):
    return ph.analyze(path_str, anchor)


@st.cache_data(show_spinner=False)
def cached_render(path_str: str, page: int, rects: tuple, dpi: int = 140):
    return ph.render_page(path_str, page, [list(r) for r in rects], dpi=dpi)


def refresh_df(username):
    st.session_state.df = db.load_user(username)


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def build_authenticator():
    cookie = st.secrets["cookie"]
    return stauth.Authenticate(
        db.load_credentials(),
        cookie["name"], cookie["key"], int(cookie["expiry_days"]),
    )


def login_page():
    authenticator = build_authenticator()
    st.title("Medical Necessity Criteria - Skin Substitute Grafts")
    tab_login, tab_register = st.tabs(["Login", "Register User"])

    with tab_login:
        authenticator.login(location="main")
        status = st.session_state.get("authentication_status")
        if status is False:
            st.error("Username or password is incorrect.")
        elif status is None:
            st.info("Log in, or create an account on the Register User tab.")
        elif status is True:
            st.rerun()

    with tab_register:
        with st.form("register_form", clear_on_submit=True):
            st.markdown("**Create your account**")
            new_user = st.text_input("Username")
            new_pw = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm password", type="password")
            if st.form_submit_button("Register", type="primary"):
                if new_pw != confirm:
                    st.error("Passwords do not match.")
                else:
                    ok, msg = db.add_user(new_user, new_pw)
                    st.success(msg + " Switch to the **Login** tab to sign in.") \
                        if ok else st.error(msg)


# --------------------------------------------------------------------------- #
# Source viewer (right pane) — cross-reference the ORIGINAL quote/source
# --------------------------------------------------------------------------- #
def render_source_viewer(row):
    st.subheader("Source document")
    primary, secondary = src.parse_source(row["source"])

    if secondary:
        tags = " · ".join(f"{s['code']} ({s['label']})" for s in secondary)
        st.info(f"Context references (not opened here): {tags}", icon="🔖")

    if not primary:
        st.warning("No recognised source document for this criterion.")
        return

    labels = [f"{p['code']} — {Path(p['filename']).stem[:40]}" for p in primary]
    idx = 0
    if len(primary) > 1:
        idx = st.radio(
            "This criterion cites multiple documents — pick one:",
            range(len(primary)), format_func=lambda i: labels[i],
            horizontal=True, key=f"docpick_{row['id']}",
        )
    doc = primary[idx]
    st.markdown(f"**Open:** {doc['label']}")

    if not doc["available"]:
        st.error(
            f"`{doc['filename']}` is not in the project folder, so the quote "
            "can't be highlighted. Add the PDF to enable it."
        )
        return

    info = cached_analyze(str(doc["path"]), row["quote_from_source"])
    hit_pages, n_pages = info["pages"], info["page_count"]

    if not hit_pages:
        st.warning("Couldn't auto-locate the quote — browse the document below.",
                   icon="🔍")

    col_a, col_b = st.columns([2, 1])
    with col_a:
        page = st.selectbox(
            "Highlighted pages", hit_pages,
            format_func=lambda p: f"Page {p + 1}",
            key=f"hitpage_{row['id']}_{doc['code']}",
        ) if hit_pages else 0
    with col_b:
        page = st.number_input(
            "Go to any page", min_value=1, max_value=n_pages, value=page + 1,
            key=f"gotopage_{row['id']}_{doc['code']}",
        ) - 1

    rects = tuple(tuple(r) for r in info["hits"].get(str(page), []))
    png = cached_render(str(doc["path"]), int(page), rects)
    st.image(png, width="stretch",
             caption=f"{doc['code']} · page {page + 1} of {n_pages}")


# --------------------------------------------------------------------------- #
# Editor (left pane)
# --------------------------------------------------------------------------- #
def render_add_form(username, df):
    with st.expander("➕ Add a new criterion"):
        with st.form("add_form", clear_on_submit=True):
            sections = sorted(df["section"].dropna().unique())
            section = st.selectbox("Section", [""] + list(sections))
            item = st.text_area("Criteria", height=90)
            chosen = st.multiselect("Source", src.SELECTABLE_SOURCES)
            custom = st.text_input("Add another source (optional)")
            if st.form_submit_button("Add criterion", type="secondary"):
                if not section.strip():
                    st.error("Please choose a Section.")
                elif not item.strip():
                    st.error("Criteria text is required.")
                else:
                    codes = list(chosen) + (
                        [c.strip() for c in re.split(r"[+,]", custom) if c.strip()])
                    nid = next_id(df, section)
                    db.add_criterion(username, {
                        "criterion_id": nid, "section": section, "item": item,
                        "source": " + ".join(codes), "quote_from_source": "",
                        "changed_criteria": "", "changed_source": "",
                        "reviewed": "", "changed": "no", "medically_necessary": "",
                    })
                    refresh_df(username)
                    st.session_state["_goto"] = nid
                    st.toast(f"Added criterion {nid}.")
                    st.rerun()


def render_editor(username, df, row):
    st.subheader(section_title(row["section"]))
    render_add_form(username, df)

    # ---- Box 1: locked original (reference) ----
    with st.container(border=True):
        st.caption("Original — for reference (locked)")
        st.text_area(f"Criteria {row['id']}", row["item"], height=110,
                     disabled=True, key=f"lock_item_{row['id']}")
        st.text_input("Source", row["source"], disabled=True,
                      key=f"lock_src_{row['id']}")
        st.text_area("Quote from Source", row["quote_from_source"], height=140,
                     disabled=True, key=f"lock_q_{row['id']}")

    # ---- Box 2: editable copy ----
    with st.container(border=True):
        st.caption("Your review — edit as needed")
        with st.form(f"edit_{row['id']}"):
            cur_item = row["changed_criteria"] or row["item"]
            new_item = st.text_area(f"Criteria {row['id']}", cur_item, height=110)

            cur_src = row["changed_source"] or row["source"]
            tokens = src.split_sources(cur_src)
            preselect = [t for t in tokens if t in src.SELECTABLE_SOURCES]
            custom_default = " + ".join(
                t for t in tokens if t not in src.SELECTABLE_SOURCES)
            chosen = st.multiselect("Source", src.SELECTABLE_SOURCES,
                                    default=preselect)
            custom = st.text_input("Add another source (optional)",
                                   value=custom_default)

            c1, c2 = st.columns([1, 1])
            with c1:
                reviewed = st.checkbox(
                    "✅ Mark as reviewed",
                    value=str(row["reviewed"]).lower() == "yes")
            with c2:
                saved = st.form_submit_button("💾 Save changes", type="secondary")

            if saved:
                codes = list(chosen) + (
                    [c.strip() for c in re.split(r"[+,]", custom) if c.strip()])
                new_src = " + ".join(codes)

                changed_crit = "" if new_item.strip() == row["item"].strip() \
                    else new_item
                orig_codes = set(src.extract_codes(row["source"]))
                changed_src = "" if set(codes) == orig_codes else new_src
                changed_flag = "yes" if (changed_crit or changed_src) else "no"

                db.update_criterion(username, row["id"], {
                    "changed_criteria": changed_crit,
                    "changed_source": changed_src,
                    "reviewed": "yes" if reviewed else "",
                    "changed": changed_flag,
                })
                refresh_df(username)
                st.toast(f"Saved criterion {row['id']}.")
                st.rerun()

    # ---- medical-necessity question (soft delete) ----
    st.markdown(
        "**Is this a criteria needed to determine medical necessity for skin "
        "substitute grafts? If no, it will be deleted.**"
    )
    current_mn = str(row.get("medically_necessary", "")).strip()
    options = ["Yes", "No"]
    choice = st.radio(
        "medical necessity", options,
        index=options.index(current_mn) if current_mn in options else None,
        horizontal=True, key=f"mn_{row['id']}", label_visibility="collapsed",
    )
    if choice is not None and choice != current_mn:
        db.update_criterion(username, row["id"], {"medically_necessary": choice})
        refresh_df(username)
        st.rerun()

    st.warning("SAVE YOUR COMPLETE CSV FILE DOWN BELOW")


# --------------------------------------------------------------------------- #
# Page: Criteria Review
# --------------------------------------------------------------------------- #
def criteria_review_page():
    authenticator = build_authenticator()
    if st.session_state.get("authentication_status") is not True:
        st.stop()

    username = st.session_state["username"]
    name = st.session_state["name"]

    if "df" not in st.session_state or st.session_state.get("user") != username:
        st.session_state.df = db.load_user(username)
        st.session_state.user = username
    df = st.session_state.df

    n_reviewed = int((df["reviewed"].str.lower() == "yes").sum())
    total = len(df)

    with st.sidebar:
        st.markdown(f"### 👤 {name}")
        authenticator.logout(location="sidebar")
        st.divider()

        st.markdown(f"#### Progress · {n_reviewed} / {total} reviewed")
        st.progress(n_reviewed / total if total else 0.0)
        st.divider()

        st.markdown("#### Choose a section")
        sections = sorted(df["section"].dropna().unique())
        pick_sections = st.multiselect("Section", sections, default=[])

        if not pick_sections:
            st.info("Pick a section above to see its criteria.")
            st.session_state.selected_id = None
        else:
            view = df[df["section"].isin(pick_sections)]
            st.markdown(f"#### Criteria ({len(view)})")
            ids = list(view["id"])

            if ids:
                def _label(i):
                    r = view[view["id"] == i].iloc[0]
                    done = str(r["reviewed"]).lower() == "yes"
                    text = r["changed_criteria"] or r["item"]
                    base = f"{'✅' if done else '⬜'} {i} · {truncate_words(text)}"
                    return strike(base) if str(
                        r["medically_necessary"]).lower() == "no" else base

                pick_key = "pick_" + "_".join(sorted(pick_sections))
                goto = st.session_state.pop("_goto", None)
                if goto in ids:
                    st.session_state[pick_key] = goto
                elif st.session_state.get(pick_key) not in ids:
                    prev = st.session_state.get("selected_id")
                    st.session_state[pick_key] = prev if prev in ids else ids[0]
                st.radio("Select a criterion", ids, format_func=_label,
                         key=pick_key, label_visibility="collapsed")
                st.session_state.selected_id = st.session_state[pick_key]
            else:
                st.info("No criteria in this section.")
                st.session_state.selected_id = None

        st.divider()
        with st.expander("↩️ Reset my copy to master"):
            st.caption("Discards all of your edits, additions, and answers.")
            if st.checkbox("I understand this can't be undone", key="resetconf"):
                if st.button("Reset to master", width="stretch"):
                    db.reset_user(username)
                    refresh_df(username)
                    st.session_state.selected_id = None
                    st.toast("Reset to master.")
                    st.rerun()

    st.title("Medical-Necessity Criteria — Skin Substitute Grafts")

    selected_id = st.session_state.get("selected_id")
    if not selected_id:
        st.info("👈 Pick a section in the sidebar, then choose a criterion to begin.")
        return

    row = df[df["id"] == selected_id].iloc[0]
    left, right = st.columns([1, 1.05], gap="large")
    with left:
        render_editor(username, df, row)
    with right:
        render_source_viewer(row)

    st.divider()
    st.markdown("#### Save your work")
    st.caption("Your changes save automatically to the database. Download a CSV "
               "snapshot of all your criteria below.")
    st.download_button(
        "⬇️ Download my CSV",
        df.drop(columns=["row_id"], errors="ignore").to_csv(index=False).encode(),
        file_name=f"criteria_{username}.csv", mime="text/csv",
    )


# --------------------------------------------------------------------------- #
# Navigation
# --------------------------------------------------------------------------- #
if st.session_state.get("authentication_status") is True:
    pages = [st.Page(criteria_review_page, title="Criteria Review", icon="📋")]
else:
    pages = [st.Page(login_page, title="Login", icon="🔑")]

st.navigation(pages).run()
