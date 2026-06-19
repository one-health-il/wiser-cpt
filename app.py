"""WISER-CPT — Medical-Necessity Criteria Review

Streamlit app for the Clinical Compliance / RCM team to review, edit, add, and
delete the 34 skin-substitute medical-necessity criteria, cross-referencing each
one against the verbatim anchor highlighted in its source document.

Two pages: "Login" (with a Register User tab) and "Criteria Review".

Run:  streamlit run app.py
"""
import re
import sys
from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "lib"))

import criteria_io as cio       # noqa: E402
import pdf_highlight as ph      # noqa: E402
import sources as src           # noqa: E402
import users_store              # noqa: E402

st.set_page_config(page_title="WISER-CPT · Necessity Criteria", layout="wide")


def truncate_words(text: str, limit: int = 45) -> str:
    """Shorten to ~limit chars without cutting a word in half: finish the word
    the limit lands on, then add '...'."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    tail = text[limit:]
    finish = re.match(r"\S*", tail).group(0)  # complete the current word
    return (text[:limit] + finish).rstrip(" :;,.-") + "..."


def section_number(section: str) -> str:
    """'1 · Wound Type…' -> 'Section 1'; falls back to the raw section text."""
    m = re.match(r"\s*(\d+)", section or "")
    return f"Section {m.group(1)}" if m else (section or "Section")


# --------------------------------------------------------------------------- #
# Cached PDF helpers (keyed by file + anchor so re-selection is instant)
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def cached_analyze(path_str: str, anchor: str):
    return ph.analyze(path_str, anchor)


@st.cache_data(show_spinner=False)
def cached_render(path_str: str, page: int, rects: tuple, dpi: int = 140):
    return ph.render_page(path_str, page, [list(r) for r in rects], dpi=dpi)


def build_authenticator():
    cfg_path = ROOT / "config.yaml"
    if not cfg_path.exists():
        st.error("config.yaml not found. Run `python make_users.py` first.")
        st.stop()
    with open(cfg_path) as f:
        config = yaml.load(f, Loader=SafeLoader)
    return stauth.Authenticate(
        users_store.load_credentials(),
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )


# --------------------------------------------------------------------------- #
# Page: Login  (Login + Register User tabs)
# --------------------------------------------------------------------------- #
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
            st.rerun()  # jump to the Criteria Review page

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
                    ok, msg = users_store.add_user(new_user, new_pw)
                    if ok:
                        st.success(msg + " Switch to the **Login** tab to sign in.")
                    else:
                        st.error(msg)


# --------------------------------------------------------------------------- #
# Source viewer (right pane)
# --------------------------------------------------------------------------- #
def render_source_viewer(row):
    st.subheader("Source document")
    primary, secondary = src.parse_source(row["source"])

    st.caption(f"Source field: `{row['source']}`")
    if secondary:
        tags = " · ".join(f"{s['code']} ({s['label']})" for s in secondary)
        st.info(f"Context references (not opened here): {tags}", icon="🔖")

    if not primary:
        st.warning("No recognised source document for this criterion.")
        return

    # choose which primary doc to view
    labels = [f"{p['code']} — {Path(p['filename']).stem[:40]}" for p in primary]
    idx = 0
    if len(primary) > 1:
        idx = st.radio(
            "This criterion cites multiple documents — pick one:",
            range(len(primary)),
            format_func=lambda i: labels[i],
            horizontal=True,
            key=f"docpick_{row['id']}",
        )
    doc = primary[idx]
    st.markdown(f"**Open:** {doc['label']}")

    if not doc["available"]:
        st.error(
            f"`{doc['filename']}` is not in the project folder, so the anchor "
            "can't be highlighted. Drop the PDF here to enable it."
        )
        return

    info = cached_analyze(str(doc["path"]), row["verbatim_anchor"])
    hit_pages = info["pages"]
    n_pages = info["page_count"]

    # only warn in the rare case where nothing could be located
    if not hit_pages:
        st.warning(
            "Couldn't auto-locate the quote on a page — browse the document "
            "manually below.", icon="🔍",
        )

    col_a, col_b = st.columns([2, 1])
    with col_a:
        if hit_pages:
            page = st.selectbox(
                "Highlighted pages",
                hit_pages,
                format_func=lambda p: f"Page {p + 1}",
                key=f"hitpage_{row['id']}_{doc['code']}",
            )
        else:
            page = 0
    with col_b:
        page = st.number_input(
            "Go to any page",
            min_value=1, max_value=n_pages, value=page + 1,
            key=f"gotopage_{row['id']}_{doc['code']}",
        ) - 1

    rects = tuple(tuple(r) for r in info["hits"].get(str(page), []))
    png = cached_render(str(doc["path"]), int(page), rects)
    st.image(png, use_container_width=True,
             caption=f"{doc['code']} · page {page + 1} of {n_pages}")


# --------------------------------------------------------------------------- #
# Criterion editor (left pane)
# --------------------------------------------------------------------------- #
def render_add_form(username, df):
    with st.expander("➕ Add a new criterion"):
        with st.form("add_form", clear_on_submit=True):
            sections = sorted(df["section"].dropna().unique())
            section = st.selectbox("Section", [""] + sections,
                                   help="Pick the section this criterion belongs to.")
            item = st.text_area("Item", height=90)
            source = st.text_input("Source", help="e.g. L35041")
            anchor = st.text_area("Quote from Source", height=110)
            if st.form_submit_button("Add criterion", type="primary"):
                sec = section.strip()
                if not sec:
                    st.error("Please choose a Section.")
                elif not item.strip():
                    st.error("Item is required.")
                else:
                    new_id = cio.next_id_for_section(df, sec)
                    df = cio.add_row(df, {
                        "id": new_id, "section": sec, "item": item,
                        "source": source, "verbatim_anchor": anchor,
                        "changed": "yes",
                    })
                    cio.save_user(username, df)
                    st.session_state.df = df
                    st.session_state["_goto"] = new_id
                    st.toast(f"Added criterion {new_id}.")
                    st.rerun()


def render_editor(username, df, row):
    st.subheader(section_number(row["section"]))
    render_add_form(username, df)            # add form sits under the section title
    st.caption(row["section"])

    with st.form(f"edit_{row['id']}"):
        item = st.text_area(f"Criteria {row['id']}", row["item"], height=110)
        source = st.text_input("Source", row["source"],
                               help="Document code(s), e.g. L35041 or L35041 + A54117")
        anchor = st.text_area("Quote from Source", row["verbatim_anchor"], height=140)

        c1, c2 = st.columns([1, 1])
        with c1:
            reviewed = st.checkbox(
                "✅ Mark as reviewed",
                value=str(row.get("reviewed", "")).lower() == "yes",
                help="Adds a checkmark next to this criterion in the sidebar.",
            )
        with c2:
            saved = st.form_submit_button("💾 Save changes", type="primary")

        if saved:
            content_changed = (
                item != row["item"]
                or source != row["source"]
                or anchor != row["verbatim_anchor"]
            )
            already_changed = str(row.get("changed", "")).lower() == "yes"
            df = cio.update_row(df, row["id"], {
                "item": item, "source": source, "verbatim_anchor": anchor,
                "reviewed": "yes" if reviewed else "",
                "changed": "yes" if (content_changed or already_changed) else "no",
            })
            cio.save_user(username, df)
            st.session_state.df = df
            st.toast(f"Saved criterion {row['id']}.")
            st.rerun()

    # delete (outside the form), guarded by a confirm checkbox
    with st.expander("Delete this criterion"):
        confirm = st.checkbox(f"Yes, delete criterion {row['id']}",
                              key=f"delconfirm_{row['id']}")
        if st.button("Delete", disabled=not confirm, key=f"delbtn_{row['id']}"):
            df = cio.delete_row(df, row["id"])
            cio.save_user(username, df)
            st.session_state.df = df
            st.session_state.pop("_goto", None)  # let the sidebar pick a neighbor
            st.toast(f"Deleted criterion {row['id']}.")
            st.rerun()

    # medical-necessity question — no default; the user must choose Yes or No
    st.markdown(
        "**Is this criterion medically necessary for skin substitute grafts?**"
    )
    current_mn = str(row.get("medically_necessary", "")).strip()
    options = ["Yes", "No"]
    choice = st.radio(
        "medically necessary", options,
        index=options.index(current_mn) if current_mn in options else None,
        horizontal=True, key=f"mn_{row['id']}",
        label_visibility="collapsed",
    )
    if choice is not None and choice != current_mn:
        df = cio.update_row(df, row["id"], {"medically_necessary": choice})
        cio.save_user(username, df)
        st.session_state.df = df
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

    # load this user's independent working copy once per session
    if "df" not in st.session_state or st.session_state.get("user") != username:
        st.session_state.df = cio.load_user(username)
        st.session_state.user = username
    df = st.session_state.df

    n_reviewed = int((df["reviewed"].str.lower() == "yes").sum())
    total = len(df)

    # ---- sidebar: identity, progress, section picker, selection ----
    with st.sidebar:
        st.markdown(f"### 👤 {name}")
        authenticator.logout(location="sidebar")
        st.divider()

        st.markdown(f"#### Progress · {n_reviewed} / {total} reviewed")
        st.progress(n_reviewed / total if total else 0.0)
        st.divider()

        st.markdown("#### Choose a section")
        sections = sorted(df["section"].dropna().unique())
        pick_sections = st.multiselect(
            "Section", sections, default=[],
            help="Pick one or more sections to load their criteria.",
        )

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
                    done = str(r.get("reviewed", "")).lower() == "yes"
                    mark = "✅" if done else "⬜"
                    return f"{mark} {i} · {truncate_words(r['item'])}"

                # bind the radio to a per-section widget key (no `index`) so the
                # widget owns its state and a click registers on the first try
                pick_key = "pick_" + "_".join(sorted(pick_sections))
                goto = st.session_state.pop("_goto", None)  # programmatic select
                if goto in ids:
                    st.session_state[pick_key] = goto
                elif st.session_state.get(pick_key) not in ids:
                    prev = st.session_state.get("selected_id")
                    st.session_state[pick_key] = prev if prev in ids else ids[0]
                st.radio(
                    "Select a criterion", ids,
                    format_func=_label,
                    key=pick_key,
                    label_visibility="collapsed",
                )
                st.session_state.selected_id = st.session_state[pick_key]
            else:
                st.info("No criteria in this section.")
                st.session_state.selected_id = None

        st.divider()
        with st.expander("↩️ Reset my copy to master"):
            st.caption("Discards all of your edits, additions, and deletions.")
            if st.checkbox("I understand this can't be undone", key="resetconf"):
                if st.button("Reset to master", use_container_width=True):
                    st.session_state.df = cio.reset_user(username)
                    st.session_state.selected_id = None
                    st.toast("Reset to master.")
                    st.rerun()

    # ---- main area ----
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

    # ---- save / export at the bottom of the page ----
    st.divider()
    st.markdown("#### Save your work")
    st.caption(
        "Your edits are saved automatically to your own copy. Use this to "
        "download a CSV snapshot of all your changes."
    )
    st.download_button(
        "⬇️ Download my CSV",
        df.to_csv(index=False).encode(),
        file_name=f"criteria_{username}.csv",
        mime="text/csv",
    )


# --------------------------------------------------------------------------- #
# Navigation: show Login when logged out, Criteria Review when logged in
# --------------------------------------------------------------------------- #
if st.session_state.get("authentication_status") is True:
    pages = [st.Page(criteria_review_page, title="Criteria Review", icon="📋")]
else:
    pages = [st.Page(login_page, title="Login", icon="🔑")]

st.navigation(pages).run()
