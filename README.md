# WISER-CPT — Medical-Necessity Criteria Review

A Streamlit app for the Clinical Compliance / RCM team to review the 34
skin-substitute medical-necessity criteria, **edit / add** them, mark whether
each is needed, and **cross-reference each against the highlighted quote** in its
source document. Data is stored in **Supabase**.

## How it works
- **Two pages:** *Login* (with a Register User tab) and *Criteria Review*.
- Each reviewer has an **independent copy** of the criteria in Supabase, seeded
  from the master set on first login.
- The editor shows two boxes per criterion:
  - **Locked original** — Criteria, Source, Quote from Source (reference).
  - **Editable copy** — Criteria + Source (multi-select), where edits, "Mark as
    reviewed", and Save live. Edits are stored in `changed_criteria` /
    `changed_source`; `changed` flips to `yes` when either has content.
- The **Quote from Source** is located in the mapped PDF and the page is shown
  with the quote highlighted.
- **"Is this a criteria needed…?"** → **No** keeps the row (soft-delete:
  `medically_necessary = No`) and shows it struck-through in the sidebar.

## Data model (Supabase — see `schema.sql`)
- `users` — `username`, `password` (bcrypt hash), `created_at`
- `criteria` — one row per (user, criterion): `criterion_id, section, item,
  source, quote_from_source, changed_criteria, changed_source, reviewed,
  changed, medically_necessary`

## Local setup
```bash
pip install -r requirements.txt
```
Create **`.streamlit/secrets.toml`** (gitignored) with your Supabase + cookie config:
```toml
[supabase]
url = "https://<project-ref>.supabase.co"
service_key = "<service_role key>"
anon_key = "<anon key>"

[cookie]
name = "wiser_cpt_auth"
key = "<random signing string>"
expiry_days = 7
```
One-time, in the Supabase dashboard: **SQL Editor → run `schema.sql`** (choose
"Run and enable RLS"). Then optionally migrate existing accounts/seed:
```bash
python setup_supabase.py
```
Run locally:
```bash
streamlit run app.py
```

## Deploy to Streamlit Community Cloud
1. Push to GitHub (repo: `one-health-il/wiser-cpt`).
2. On share.streamlit.io: **New app** → pick the repo/branch → main file `app.py`.
3. In **App settings → Secrets**, paste the same TOML as `.streamlit/secrets.toml`
   (`[supabase]` + `[cookie]`).
4. Deploy. The 5 source PDFs are in the repo, so highlighting works out of the box.

## Source documents (in the repo / app folder)
| Code | File |
|------|------|
| L35041 | LCD …Bioengineered Skin Substitutes… (L35041).pdf |
| L36690 | LCD …CTPs, Lower Extremities (L36690).pdf |
| A54117 | Article …Skin Substitutes… (A54117).pdf |
| A56696 | Article …CTPs… (A56696).pdf |
| WISER  | wiser-providersupplieropguide_4_30_26.pdf |

## Key files
- `app.py` — the application (login + two-pane review UI)
- `lib/db.py` — Supabase data layer (users + criteria)
- `lib/pdf_highlight.py` — quote matching + page rendering (PyMuPDF)
- `lib/sources.py` — Source-string ↔ PDF mapping; selectable source codes
- `schema.sql` — Supabase/Postgres tables
- `setup_supabase.py` — one-time account import + criteria seeding
- `build_seed.py` — rebuilds `data/criteria_master.csv` from the source `.docx`

> Legacy (pre-Supabase, unused by the app now): `lib/criteria_io.py`,
> `lib/users_store.py`, `make_users.py`, `config.yaml`, `users.csv`.
