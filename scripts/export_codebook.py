"""Export a human-readable codebook from the binary .sav — the evidence artefact.

Usage:
    python scripts/export_codebook.py

`ZA8841_v1-0-0.sav` is a binary SPSS file: a text editor shows nothing usable, and
its answers are numeric codes whose meaning lives in a separate label dictionary
inside the file. "I ran a script and got numbers" is not evidence that anyone
looked inside it.

This produces two artefacts that are:

  * `docs/CODEBOOK-EB547.md`            — readable, checkable against GESIS's own
                                          published codebook line by line
  * `docs/codebook-eb547-variables.csv` — the full 668-variable inventory

The last section is the one that settles the question: the same respondents shown
**raw code → label → cleaned value**, so the recoding is not asserted, it is
displayed.
"""
from __future__ import annotations

import sys
from datetime import date

import pandas as pd
import pyreadstat

from actionwise import config
from actionwise.data.loader import load_za8841, value_labels_for

DOCS = config.ROOT / "docs"
MD = DOCS / "CODEBOOK-EB547.md"
CSV = DOCS / "codebook-eb547-variables.csv"

# The variables the project actually uses, grouped as the questionnaire groups them.
GROUPS = {
    "Resilience horizon (RHI)": list(config.QC7_DOMAINS),
    "Preparedness actions (PGI, PRI)": list(config.QC6_ITEMS) + [config.QC6_OTHER,
                                                                config.QC6_DK,
                                                                config.QC6_TOTAL],
    "Information & awareness": list(config.QC5_ITEMS),
    "Attitudes & barriers": list(config.QC8_ITEMS),
    "Demographics": list(config.DEMOGRAPHIC_ITEMS),
    "Weights & identifiers": [config.WEIGHT_NATIONAL, config.WEIGHT_EU,
                              config.WEIGHT_EU27_LEGACY] + config.ID_VARS,
}

# Shown with a full frequency table — the ones a jury is most likely to spot-check.
FREQUENCY_VARS = ["qc7_1", "qc6.7", "qc8_2", "d25"]

# Traced raw -> cleaned, to show the recoding rather than describe it.
TRACE_VARS = [
    ("qc7_1", "days_water", "off-scale 5/6 nulled"),
    ("qc8_2", "prep_feels_well_prepared", "off-scale nulled, then REVERSED"),
    ("qc6.7", "act_grab_bag", "nulled where the whole battery was Don't know"),
]


def header(meta, raw: pd.DataFrame) -> str:
    first = open(config.EB547_SAV, "rb").read(64)
    magic = first[:4].decode("ascii", "replace")
    product = first[4:60].decode("ascii", "replace").strip()

    return f"""# Codebook — Eurobarometer ZA8841, read from the source file

*Generated {date.today().isoformat()} by `scripts/export_codebook.py`, directly from
the binary `.sav`. Nothing here is transcribed by hand.*

## Why this document exists

`{config.EB547_SAV.name}` is a **binary SPSS file**. Opened in a text editor it shows
only this much readable text before turning to packed bytes:

```
{magic}  {product}
```

Every answer inside it is a **numeric code**. `qc7_1 = 2` means nothing until the
file's own label dictionary says that 2 is *"2 - 3 days"*. This document extracts
that dictionary so the contents can be read, checked against GESIS's published
codebook, and audited independently of any code in this project.

## File identity

| | |
|---|---|
| File | `{config.EB547_SAV.name}` |
| Study | Eurobarometer 101.1 / Special Eurobarometer 547 |
| DOI | `10.4232/1.14461` |
| Produced by | `{product}` |
| File created | {meta.creation_time} |
| Encoding | {meta.file_encoding} |
| Rows (respondents) | **{meta.number_rows:,}** |
| Columns (variables) | **{meta.number_columns}** |
| Variable labels | {len(meta.column_names_to_labels)} |
| Value-label sets | {len(meta.value_labels)} |

The row and column counts are asserted by `scripts/run_pipeline.py` before anything
runs: a different file or survey wave stops the pipeline rather than producing
plausible numbers about the wrong data.

## Coverage

{coverage_table(raw)}
"""


def coverage_table(raw: pd.DataFrame) -> str:
    counts = raw["isocntry"].value_counts().sort_index()
    rows = [f"**{len(counts)} territories, {len(raw):,} respondents.** "
            "Germany is split East/West at source and is collapsed to `DE` during "
            "cleaning.\n"]
    line = " · ".join(f"{iso} {n:,}" for iso, n in counts.items())
    rows.append(line)
    return "\n".join(rows)


def group_section(meta, raw: pd.DataFrame) -> str:
    out = ["\n## The variables this project uses\n",
           "Every one shown with the label and the code list **as stored in the file**.\n"]
    for title, names in GROUPS.items():
        out.append(f"### {title}\n")
        rows = []
        for name in names:
            if name not in meta.column_names_to_labels:
                continue
            labels = value_labels_for(meta, name)
            codes = " · ".join(f"`{int(k) if float(k).is_integer() else k}` {v}"
                               for k, v in sorted(labels.items())) if labels else "*numeric*"
            rows.append({
                "variable": f"`{name}`",
                "label in the file": meta.column_names_to_labels[name],
                "codes": codes,
            })
        out.append(pd.DataFrame(rows).to_markdown(index=False))
        out.append("")
    return "\n".join(out)


def frequency_section(meta, raw: pd.DataFrame) -> str:
    out = ["\n## Frequency checks\n",
           "Unweighted counts straight from the file. These are the numbers to "
           "spot-check against the GESIS codebook.\n"]
    for name in FREQUENCY_VARS:
        if name not in raw.columns:
            continue
        labels = value_labels_for(meta, name)
        counts = raw[name].value_counts(dropna=False).sort_index()
        frame = pd.DataFrame({
            "code": [("(missing)" if pd.isna(k) else int(k) if float(k).is_integer() else k)
                     for k in counts.index],
            "meaning": [labels.get(k, "—") if not pd.isna(k) else "not asked / no answer"
                        for k in counts.index],
            "n": counts.to_numpy(),
        })
        frame["%"] = (frame["n"] / len(raw) * 100).round(1)
        out.append(f"**`{name}`** — {meta.column_names_to_labels[name]}\n")
        out.append(frame.to_markdown(index=False))
        out.append("")
    return "\n".join(out)


def trace_section(meta, raw: pd.DataFrame) -> str:
    """Raw code -> label -> cleaned value, for real respondents."""
    interim = config.DATA_INTERIM / "eb547_clean.parquet"
    out = ["\n## Raw → cleaned, on the same respondents\n"]
    if not interim.exists():
        out.append("*Run `python scripts/run_pipeline.py` first to generate this "
                   "section.*\n")
        return "\n".join(out)

    clean = pd.read_parquet(interim)
    out.append(
        "The recoding is **shown, not asserted**. Each row is one real respondent: "
        "the code stored in the file, what the file's dictionary says that code "
        "means, and the value this project computed from it.\n"
    )

    for source, cleaned, note in TRACE_VARS:
        if source not in raw.columns or cleaned not in clean.columns:
            continue
        labels = value_labels_for(meta, source)
        merged = pd.DataFrame({
            # As an integer, not a float: pandas renders a 9-digit float as
            # "1.7e+08", which would make "one real respondent" unverifiable —
            # the whole point of this table is that the id can be looked up.
            "uniqid": raw["uniqid"].astype("int64"),
            "raw code": raw[source],
        }).merge(
            clean[["uniqid", cleaned]].assign(uniqid=clean["uniqid"].astype("int64")),
            on="uniqid", how="inner",
        )

        # One example of each distinct raw code, so every branch is visible.
        sample = merged.dropna(subset=["raw code"]).groupby("raw code").head(1)
        sample = sample.sort_values("raw code")
        sample["means (from the file)"] = sample["raw code"].map(
            lambda k: labels.get(k, "—")
        )
        sample = sample.rename(columns={cleaned: f"cleaned `{cleaned}`"})
        sample["raw code"] = sample["raw code"].map(
            lambda v: int(v) if float(v).is_integer() else v
        )

        out.append(f"**`{source}` → `{cleaned}`** — *{note}*\n")
        out.append(sample[["uniqid", "raw code", "means (from the file)",
                           f"cleaned `{cleaned}`"]].to_markdown(index=False))
        out.append("")

    out.append(
        "Read the null rows: codes 5 and 6 are *Not applicable* and *Don't know*. "
        "Left as numbers they would sort **above** \"More than 7 days\", making the "
        "least-informed respondents look like the best-prepared. That is the single "
        "most consequential thing in this file, and it is only visible because the "
        "label dictionary was read.\n"
    )
    return "\n".join(out)


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    raw, meta = load_za8841()

    inventory = pd.DataFrame({
        "variable": meta.column_names,
        "label": [meta.column_names_to_labels[c] for c in meta.column_names],
        "has_value_labels": [bool(value_labels_for(meta, c)) for c in meta.column_names],
        "used_by_project": [
            any(c in names for names in GROUPS.values()) for c in meta.column_names
        ],
    })
    inventory.to_csv(CSV, index=False, encoding="utf-8")

    document = "\n".join([
        header(meta, raw),
        group_section(meta, raw),
        frequency_section(meta, raw),
        trace_section(meta, raw),
        f"\n---\n\n*Full {meta.number_columns}-variable inventory: "
        f"`{CSV.name}`. Regenerate both with "
        "`python scripts/export_codebook.py`.*\n",
    ])
    MD.write_text(document, encoding="utf-8")

    print(f"  wrote {MD.relative_to(config.ROOT)}")
    print(f"  wrote {CSV.relative_to(config.ROOT)}  ({len(inventory)} variables, "
          f"{int(inventory['used_by_project'].sum())} used by the project)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
