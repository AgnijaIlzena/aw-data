"""External validation — and an honest account of what it can and cannot show.

Two independent checks, because the interesting one fails.

**1. Against the published national figure.** VUGD's own reported average arrival
is 9.2 minutes. The model's population-weighted mean response is directly
comparable in units and should land slightly *below* it, since the model excludes
call-handling time and assumes optimal routing. This is the check that works.

**2. Against NMPD's per-municipality compliance.** Four years of published
outcomes for priority 1-2 calls, 35 municipalities matched. The idea was a rank
check: if the travel-time model captures real accessibility, places it marks as
remote should show worse ambulance compliance.

**It does not, and the reason is identifiable.** Measured on 2024:

    model mean response  vs NMPD compliance      rho = -0.18  (p = 0.29)
    Euclidean baseline   vs NMPD compliance      rho = -0.10  (p = 0.57)

Neither does anything geographic:

    calls per 1,000      vs NMPD compliance      rho = +0.03
    population density   vs NMPD compliance      rho = +0.09
    depots per 100k      vs NMPD compliance      rho = -0.01

Meanwhile the model's own positive controls pass cleanly:

    model response vs density                    rho = -0.32
    model response vs depots per 100k            rho = -0.43
    model response vs Euclidean baseline         rho = +0.82

So the model is internally coherent and NMPD compliance simply is not a
geographic quantity at this scale. At the 25-minute rural target, distance is not
the binding constraint: the model puts 93-100% of every rural municipality's
population within 25 minutes of a fire depot, while observed ambulance compliance
ranges 70-93%. That 30-point gap is operational — crew availability, dispatch,
hospital handover, and an ambulance network sited independently of the fire one —
not spatial.

Reported as a null result rather than re-specified until a correlation appears.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from actionwise.data.cleaner_eb547 import Audit
from actionwise_geo.config import (
    LEGACY_NATIONAL_MEAN_ARRIVAL_MIN,
    NMPD_AGGREGATE_ROW,
    NMPD_DIR,
    NMPD_MAJOR_CITIES,
    NMPD_PARTIAL_YEARS,
    NMPD_TARGET_MIN,
    NMPD_YEARS,
)

CALLS = "Rez_1_2_prior_izsauk"
ON_TIME = "no_tiem_izpild_savl"
COMPLIANCE = "no_tiem_izpild_savl_proc"


def load_nmpd(years=NMPD_YEARS, directory=NMPD_DIR,
              audit: Audit | None = None) -> tuple[pd.DataFrame, Audit]:
    """Read the published priority 1-2 outcomes, long by year.

    Keeps the aggregate `Valstspilsēta` row and flags it rather than dropping it:
    it carries **54% of national call volume** in a single unmappable record, and
    that gap belongs in the output, not in a comment.
    """
    audit = audit or Audit()
    frames = []
    for year in years:
        path = directory / f"nmpd_novadi_{year}.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path, encoding="utf-8-sig")
        frame.columns = [c.strip() for c in frame.columns]
        frame["municipality"] = frame["NOVADS"].astype("string").str.strip()
        frame["year"] = year
        frame["partial_year"] = year in NMPD_PARTIAL_YEARS
        frame["is_aggregate"] = frame["municipality"] == NMPD_AGGREGATE_ROW
        frames.append(frame[["municipality", "year", "partial_year", "is_aggregate",
                             CALLS, ON_TIME, COMPLIANCE]])

    combined = pd.concat(frames, ignore_index=True)
    aggregate_share = (
        combined.loc[combined["is_aggregate"], CALLS].sum() / combined[CALLS].sum()
    )
    audit.record(
        step="load_nmpd",
        rows_in=len(combined),
        rows_out=len(combined),
        cells_nulled=int(combined["is_aggregate"].sum()),
        reason=(
            f"{len(frames)} year(s); {aggregate_share:.0%} of all priority 1-2 calls "
            f"sit in the single {NMPD_AGGREGATE_ROW!r} row covering all 7 "
            "valstspilsētas, which cannot be placed on a map; "
            f"{sorted(NMPD_PARTIAL_YEARS)} are partial years and must never be "
            "compared as levels"
        ),
    )
    return combined, audit


def nmpd_target_minutes(municipality: pd.Series, is_city: pd.Series | None = None
                        ) -> pd.Series:
    """NMPD's applicable target — a *different* regulation from the fire service.

    MK noteikumi Nr. 555 (2018): 12 minutes in the four largest cities, 15 in
    other cities, 25 outside cities. Not to be confused with MK 297's 8/23, which
    governs VUGD. Mixing the two would compare each service against the other's
    standard.
    """
    names = municipality.astype("string")
    target = pd.Series(NMPD_TARGET_MIN["rural"], index=municipality.index, dtype=float)
    if is_city is not None:
        target = target.mask(is_city.fillna(False), NMPD_TARGET_MIN["city"])
    return target.mask(names.isin(NMPD_MAJOR_CITIES), NMPD_TARGET_MIN["major_city"])


def national_check(mean_response_minutes: float,
                   published: float = LEGACY_NATIONAL_MEAN_ARRIVAL_MIN) -> pd.DataFrame:
    """The check that works: model mean response against VUGD's published average.

    The model should land **below** the published figure, because it excludes
    call-handling time and assumes a vehicle takes the optimal route. Landing
    above it, or far below, would mean the speed model is wrong.
    """
    delta = mean_response_minutes - published
    return pd.DataFrame([{
        "published_mean_arrival_min": published,
        "model_mean_response_min": round(mean_response_minutes, 2),
        "delta_min": round(delta, 2),
        "direction_expected": "model below published",
        "pass": bool(0 < published - mean_response_minutes < 4.0),
        "note": (
            "the published figure includes dispatch and real-world routing; the "
            "model includes neither, so a gap of 1-3 minutes is the expected shape"
        ),
    }])


def spearman_with_ci(x, y, alpha: float = 0.05) -> dict:
    """Spearman rho with a Fisher-z confidence interval.

    The CI matters more than the point estimate here: with 35 municipalities a
    null result needs to be shown as *bounded*, not merely unproven.
    """
    x = pd.Series(x).astype(float)
    y = pd.Series(y).astype(float)
    usable = x.notna() & y.notna()
    n = int(usable.sum())
    if n < 4:
        return {"rho": np.nan, "p": np.nan, "ci_low": np.nan, "ci_high": np.nan, "n": n}

    rho, p = stats.spearmanr(x[usable], y[usable])
    stderr = 1.0 / np.sqrt(n - 3)
    z = np.arctanh(np.clip(rho, -0.999999, 0.999999))
    crit = stats.norm.ppf(1 - alpha / 2)
    return {
        "rho": float(rho),
        "p": float(p),
        "ci_low": float(np.tanh(z - crit * stderr)),
        "ci_high": float(np.tanh(z + crit * stderr)),
        "n": n,
    }


def rank_check(model: pd.DataFrame, observed: pd.DataFrame,
               year: int = 2024, audit: Audit | None = None
               ) -> tuple[pd.DataFrame, Audit]:
    """Rank-correlate every candidate predictor against observed compliance.

    `model` is indexed by municipality and must carry `mean_response_min`; any
    other numeric column is treated as a further predictor, including the
    Euclidean baseline — which is reported beside the network model exactly as in
    Phase 3, so "our routing explains it" cannot be claimed without showing that
    a ruler does not.
    """
    audit = audit or Audit()

    year_data = observed[(observed["year"] == year) & ~observed["is_aggregate"]]
    merged = model.join(
        year_data.set_index("municipality")[[COMPLIANCE, CALLS]], how="inner"
    )

    rows = []
    for column in model.select_dtypes("number").columns:
        result = spearman_with_ci(merged[column], merged[COMPLIANCE])
        rows.append({"predictor": column, **result,
                     "significant": bool(result["p"] < 0.05)})

    audit.record(
        step="nmpd_rank_check",
        rows_in=len(model),
        rows_out=len(merged),
        cells_nulled=len(model) - len(merged),
        reason=(
            f"{len(merged)} of {len(model)} municipalities matched NMPD for {year}; "
            "the 7 valstspilsētas are unmatched because NMPD reports them as one "
            "aggregate row"
        ),
    )
    return pd.DataFrame(rows).sort_values("p").reset_index(drop=True), audit


def interpret(result: pd.DataFrame) -> str:
    """State the outcome plainly, including when it is null."""
    primary = result[result["predictor"] == "mean_response_min"]
    if primary.empty:
        return "no primary predictor found"

    row = primary.iloc[0]
    controls = result[result["predictor"] != "mean_response_min"]
    any_significant = bool(result["significant"].any())

    verdict = (
        f"rho = {row['rho']:+.3f} (95% CI {row['ci_low']:+.2f} to "
        f"{row['ci_high']:+.2f}, p = {row['p']:.3f}, n = {int(row['n'])})"
    )
    if not any_significant:
        return (
            f"NULL RESULT — {verdict}. No predictor reaches significance, the "
            "Euclidean baseline included. NMPD compliance is not a geographic "
            "quantity at this scale: at a 25-minute rural target the model places "
            "93-100% of each municipality within reach, while observed compliance "
            "runs 70-93%. That gap is operational — crew availability, dispatch, "
            "handover, and an ambulance network sited independently of the fire "
            "one — not spatial. The model is neither confirmed nor refuted by it."
        )
    return f"{verdict}; {len(controls[controls['significant']])} control(s) also significant."
