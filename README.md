# WISER-CPT — Medical-Necessity Criteria Review

A Streamlit app for the Clinical Compliance / RCM team to review the 34
skin-substitute medical-necessity criteria, **edit / add / delete** them, and
**cross-reference each one against the highlighted verbatim anchor** in its
source document.

## How it works
- Each criterion's **Source** field is mapped to the actual PDF(s) to open.
  `L35125` and `NCD 270.3` are shown as *context tags* only (they're always
  tied to `L35041`, which is the document opened and highlighted).
- The **Verbatim anchor** is located in the PDF (best-effort, multi-fragment
  matching) and the relevant page is rendered as an image with the text
  highlighted. A page picker lets you jump between hits or browse manually.
- Every reviewer logs in and works on their **own independent copy** of the
  criteria (`data/users/criteria_<username>.csv`). Edits never affect other
  users or the master. "Reset to master" restores the baseline.

## Setup
```bash
pip install -r requirements.txt
python build_seed.py     # build data/criteria_master.csv from the .docx (already done)
python make_users.py     # create config.yaml with hashed logins
```

### Users / passwords
Edit `USERS` in `make_users.py`, then re-run `python make_users.py`.
Defaults: `admin`, `reviewer1`, `reviewer2` — all with password `changeme123`
(**change these before real use**). Also change the `cookie.key` in
`make_users.py`.

## Run
```bash
streamlit run app.py
```

## Source documents (keep in this folder)
| Code | File |
|------|------|
| L35041 | LCD - …Bioengineered Skin Substitutes… (L35041).pdf |
| L36690 | LCD - …CTPs, Lower Extremities (L36690).pdf |
| A54117 | Article - …Skin Substitutes… (A54117).pdf |
| A56696 | Article - …CTPs… (A56696).pdf |
| WISER  | wiser-providersupplieropguide_4_30_26.pdf |

If a referenced PDF is missing, the app says so and disables highlighting for
that criterion until the file is added.

## Files
- `app.py` — the application (login + two-pane review UI)
- `build_seed.py` — flattens the `.docx` tables into `data/criteria_master.csv`
- `make_users.py` — generates `config.yaml` with bcrypt-hashed credentials
- `lib/sources.py` — Source-string → PDF mapping
- `lib/pdf_highlight.py` — anchor matching + page rendering (PyMuPDF)
- `lib/criteria_io.py` — per-user CSV load/save/edit/add/delete/reset
