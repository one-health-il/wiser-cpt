"""One-time builder: flatten the 9 tables in skin_graft_necessity_V1.1.docx
into a single canonical CSV (data/criteria_master.csv) of 34 criteria.

Run:  python build_seed.py
"""
from pathlib import Path

import docx
import pandas as pd
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).parent
DOCX = ROOT / "skin_graft_necessity_V1.1.docx"
OUT = ROOT / "data" / "criteria_master.csv"

COLUMNS = ["id", "section", "item", "source", "verbatim_anchor",
           "reviewed", "changed", "medically_necessary"]


def section_for_each_table(doc):
    """Walk the document body in order, tracking the most recent Heading 2
    paragraph, and return a list giving the section title for each table."""
    sections = []
    last_heading = None
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            p = Paragraph(child, doc)
            style = p.style.name if p.style else ""
            if p.text.strip() and "Heading" in style:
                last_heading = p.text.strip()
        elif isinstance(child, CT_Tbl):
            sections.append(last_heading)
    return sections


def main():
    doc = docx.Document(str(DOCX))
    sections = section_for_each_table(doc)

    rows = []
    for t_idx, table in enumerate(doc.tables):
        section = sections[t_idx] if t_idx < len(sections) else None
        # row 0 is the header (#, Item, Type, When, Source, Verbatim anchor)
        for row in table.rows[1:]:
            cells = [c.text.strip() for c in row.cells]
            if not any(cells):
                continue
            num, item, _typ, _when, source, anchor = cells[:6]
            rows.append(
                {
                    "id": num,
                    "section": section,
                    "item": item,
                    "source": source,
                    "verbatim_anchor": anchor,
                    "reviewed": "",
                    "changed": "no",
                    "medically_necessary": "",
                }
            )

    df = pd.DataFrame(rows, columns=COLUMNS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df)} criteria to {OUT}")
    print(df[["id", "section", "source"]].to_string(index=False))


if __name__ == "__main__":
    main()
