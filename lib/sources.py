"""Map the free-text 'Source' column of a criterion to the actual PDF file(s)
the reviewer should open.

The Source string can be compound, e.g.:
    "L35041"
    "L35041 (detail in L35125)"
    "L35041 (seam) + NCD 270.3 (controls)"
    "L35041 + A54117"

Rules (per stakeholder):
  * L35125 and NCD 270.3 are never the document to open. They are secondary
    references always tied to L35041, so we surface them as context tags only.
  * Every other recognised code maps to one of the 5 uploaded PDFs and is
    treated as a "primary" document to open and highlight against.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# code -> PDF filename (relative to project root)
PRIMARY_DOCS = {
    "L35041": "LCD - Application of Bioengineered Skin Substitutes to Lower Extremity Chronic Non-Healing Wounds (L35041).pdf",
    "L36690": "LCD - Wound Application of Cellular and_or Tissue Based Products (CTPs), Lower Extremities (L36690).pdf",
    "A54117": "Article - Billing and Coding_ Application of Bioengineered Skin Substitutes to Lower Extremity Chronic Non-Healing Wounds (A54117).pdf",
    "A56696": "Article - Billing and Coding_ Wound Application of Cellular and_or Tissue Based Products (CTPs), Lower Extremities (A56696).pdf",
    "WISER": "wiser-providersupplieropguide_4_30_26.pdf",
}

# codes that are references/context only, never the document to open
SECONDARY_CODES = {"L35125", "NCD 270.3"}

# regex that finds any known code token in a Source string
_CODE_RE = re.compile(r"NCD\s*270\.3|L35125|L35041|L36690|A54117|A56696|WISER", re.IGNORECASE)

# friendly labels for display
LABELS = {
    "L35041": "LCD L35041 — Bioengineered Skin Substitutes",
    "L36690": "LCD L36690 — CTPs, Lower Extremities",
    "A54117": "Article A54117 — Billing & Coding (Skin Substitutes)",
    "A56696": "Article A56696 — Billing & Coding (CTPs)",
    "WISER": "WISER Provider/Supplier Operations Guide",
    "L35125": "LCD L35125 — Wound Care (conservative-care definition)",
    "NCD 270.3": "NCD 270.3 — PRP / blood-derived products",
}


def _normalise(token: str) -> str:
    t = re.sub(r"\s+", " ", token.strip().upper())
    return "NCD 270.3" if t.startswith("NCD") else t


def parse_source(source: str):
    """Return (primary, secondary) where:
      primary   = list of dicts {code, label, filename, path, available}
      secondary = list of dicts {code, label}  (context-only references)
    Order is preserved and duplicates removed.
    """
    primary, secondary = [], []
    seen = set()
    for m in _CODE_RE.finditer(source or ""):
        code = _normalise(m.group(0))
        if code in seen:
            continue
        seen.add(code)
        if code in SECONDARY_CODES:
            secondary.append({"code": code, "label": LABELS.get(code, code)})
        elif code in PRIMARY_DOCS:
            fname = PRIMARY_DOCS[code]
            path = ROOT / fname
            primary.append(
                {
                    "code": code,
                    "label": LABELS.get(code, code),
                    "filename": fname,
                    "path": path,
                    "available": path.exists(),
                }
            )
    return primary, secondary


def all_documents():
    """All primary PDFs, for a manual document picker."""
    out = []
    for code, fname in PRIMARY_DOCS.items():
        path = ROOT / fname
        out.append(
            {
                "code": code,
                "label": LABELS.get(code, code),
                "filename": fname,
                "path": path,
                "available": path.exists(),
            }
        )
    return out
