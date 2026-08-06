"""Phase 2 gate — reproduce DG ECHO's published figures from our own pipeline.

This is the single most important check in the project. If our numbers do not
match the ones the European Commission published from the same file, then our
recoding or our weighting is wrong, and every index built on top would be wrong
in a way that still looks plausible.

`virality-code` never did this. Its model reported 33.6% accuracy against a 34.0%
baseline and nobody noticed, because there was no external number to check
against. Here there is.

Written as a module rather than notebook cells so it can also run under pytest.
"""
from __future__ import annotations

import pandas as pd

from actionwise.config import PUBLISHED_MARGINALS, SANITY_TOLERANCE
from actionwise.weighting import weighted_share as _weighted_share


def weighted_share(df: pd.DataFrame, flag: str, weight: str = "w_eu") -> float:
    """Published-topline convention: nulls count as false and stay in the denominator."""
    return _weighted_share(df, flag, weight, fillna=True)


def horizon_over_7_days(df: pd.DataFrame, domain: str, weight: str = "w_eu",
                        include_dk_in_denominator: bool = True) -> float:
    """Share answering 'More than 7 days' (code 4) for one qc7 domain."""
    col = f"days_{domain}"
    sub = df if include_dk_in_denominator else df[df[col].notna()]
    sub = sub[sub[weight].notna()]
    flag = (sub[col] == 4).fillna(False).astype(float)
    return float((flag * sub[weight]).sum() / sub[weight].sum())


def run_gate(df: pd.DataFrame) -> pd.DataFrame:
    """Compare our computed marginals with the published ones.

    Returns a table with one row per published figure and a pass/fail column.
    """
    checks: list[dict] = []

    def add(name: str, published: float, computed: float, note: str = "") -> None:
        delta = computed - published
        checks.append(
            {
                "check": name,
                "published": published,
                "computed": round(computed, 4),
                "delta": round(delta, 4),
                "pass": abs(delta) <= SANITY_TOLERANCE,
                "note": note,
            }
        )

    # ── Agreement toplines, EU-wide, DK left in the denominator ─────────────
    add(
        "qc8_2 'feel well prepared' (EU)",
        PUBLISHED_MARGINALS["qc8_2_agree_eu27"],
        weighted_share(df, "prep_feels_well_prepared_agree_topline", "w_eu"),
        "fewer than 4 in 10",
    )
    add(
        "qc8_5 'need more information' (EU)",
        PUBLISHED_MARGINALS["qc8_5_agree_eu27"],
        weighted_share(df, "prep_needs_more_info_agree_topline", "w_eu"),
        "almost 2 in 3",
    )

    # ── Resilience horizon: share who could last more than 7 days ──────────
    for domain, key in (
        ("medication", "qc7_5_over_7d_eu27"),
        ("food", "qc7_4_over_7d_eu27"),
        ("gas_heating", "qc7_3_over_7d_eu27"),
    ):
        add(
            f"qc7 {domain}: >7 days (EU)",
            PUBLISHED_MARGINALS[key],
            horizon_over_7_days(df, domain, "w_eu"),
        )

    # ── Country spread — the widest published contrast ──────────────────────
    for iso, key, label in (
        ("SI", "qc8_2_agree_SI", "Slovenia (highest)"),
        ("MT", "qc8_2_agree_MT", "Malta (lowest)"),
    ):
        sub = df[df["country_grouped"] == iso]
        add(
            f"qc8_2 'feel well prepared' — {label}",
            PUBLISHED_MARGINALS[key],
            weighted_share(sub, "prep_feels_well_prepared_agree_topline", "w_national"),
            "national weight",
        )

    return pd.DataFrame(checks)


def format_gate(result: pd.DataFrame) -> str:
    """Render the gate result for a terminal or a notebook cell."""
    passed = int(result["pass"].sum())
    total = len(result)
    body = result.assign(
        published=lambda d: (d["published"] * 100).map("{:.1f}%".format),
        computed=lambda d: (d["computed"] * 100).map("{:.1f}%".format),
        delta=lambda d: (d["delta"] * 100).map("{:+.1f}pp".format),
        **{"pass": lambda d: d["pass"].map({True: "PASS", False: "FAIL"})},
    )
    with pd.option_context("display.width", 160, "display.max_colwidth", 40):
        table = body.to_string(index=False)
    verdict = (
        f"GATE PASSED — {passed}/{total} published figures reproduced within "
        f"{SANITY_TOLERANCE:.0%}. The pipeline can be trusted downstream."
        if passed == total
        else f"GATE FAILED — {passed}/{total} reproduced. STOP: fix recoding or "
        "weighting before building any index on this."
    )
    return f"{table}\n\n{verdict}"
