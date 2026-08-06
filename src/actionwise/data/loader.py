"""Load raw survey files into DataFrames.

No transformation happens here — callers get the file as stored, so that any
surprise in the data is attributable to the source rather than to us. All
recoding lives in cleaner_eb547.py.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyreadstat

from actionwise.config import EB547_SAV


def load_za8841(path: Path | None = None, metadata_only: bool = False):
    """Return the Eurobarometer ZA8841 (EB 101.1 / Special EB 547) file.

    Args:
        path: override the default location (RNCP/dati/ZA8841_v1-0-0.sav).
        metadata_only: read the header without materialising 26k x 668 values —
            useful for listing variables or checking value labels cheaply.

    Returns:
        (df, meta). `meta` carries `column_names_to_labels`, `variable_to_label`
        and `value_labels`, which the cleaner uses to resolve coded answers and
        which the notebooks use to render human-readable item text.
    """
    sav = path or EB547_SAV
    if not sav.exists():
        raise FileNotFoundError(
            f"{sav} not found. Download ZA8841 from GESIS (access.gesis.org/dbk/78792) "
            "and place it in the dati/ folder."
        )
    df, meta = pyreadstat.read_sav(str(sav), metadataonly=metadata_only)
    return df, meta


def value_labels_for(meta, variable: str) -> dict:
    """Resolve the value-label dictionary for one variable, or {} if unlabelled.

    pyreadstat stores labels in a two-step lookup (variable -> label set name ->
    codes), which is easy to get wrong at the call site.
    """
    label_set = meta.variable_to_label.get(variable)
    if label_set is None:
        return {}
    return meta.value_labels.get(label_set, {})
