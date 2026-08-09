"""Phase 0 smoke tests — the environment and the raw source are what we think.

These are deliberately about *facts*, not code behaviour. `virality-code` shipped a
model trained on Faker text because nobody asserted anything about the input.
"""
import pytest

from actionwise import config


def test_raw_store_is_outside_the_repo():
    """Raw data lives in RNCP/dati/ and is never written to by this project."""
    assert config.DATA_RAW.name == "dati"
    assert config.DATA_RAW.exists(), f"raw store missing: {config.DATA_RAW}"
    assert config.ROOT not in config.DATA_RAW.parents


def test_eb547_source_present():
    assert config.EB547_SAV.exists(), (
        f"{config.EB547_SAV} not found. Download ZA8841 from GESIS "
        "(access.gesis.org/dbk/78792) into the dati/ folder."
    )


def test_eb547_shape_is_as_verified():
    """The file is the one this project was designed against, not a different wave."""
    pyreadstat = pytest.importorskip("pyreadstat")
    _, meta = pyreadstat.read_sav(str(config.EB547_SAV), metadataonly=True)
    assert (meta.number_rows, meta.number_columns) == config.EB547_EXPECTED_SHAPE


def test_every_variable_the_design_depends_on_exists():
    """Fail loudly now rather than producing a silently empty column later."""
    pyreadstat = pytest.importorskip("pyreadstat")
    _, meta = pyreadstat.read_sav(str(config.EB547_SAV), metadataonly=True)
    present = set(meta.column_names)

    required = (
        set(config.QC6_ITEMS)
        | set(config.QC7_DOMAINS)
        | set(config.QC5_ITEMS)
        | set(config.QC8_ITEMS)
        | set(config.DEMOGRAPHIC_ITEMS)
        | set(config.ID_VARS)
        | {
            config.QC6_OTHER,
            config.QC6_DK,
            config.QC6_TOTAL,
            config.WEIGHT_NATIONAL,
            config.WEIGHT_EU,
            config.WEIGHT_EU27_LEGACY,
        }
    )
    missing = sorted(required - present)
    assert not missing, f"variables named in config are absent from the .sav: {missing}"


def test_duckdb_client_importable():
    from actionwise.db.duckdb_client import get_connection  # noqa: F401


# ── the config names must mean what the file says they mean ────────────────

# Where the project's English handle and the file's own wording legitimately
# differ. Declared here rather than glossed over, because each one is a
# judgement someone may want to challenge.
SEMANTIC_ALIASES = {
    # The file says "EMERGENCY PHARMACY" — a translation artefact of the source
    # questionnaire (FR "pharmacie de secours", DE "Hausapotheke"). The item is a
    # domestic first-aid kit, which is what ActionWise calls it.
    "first_aid_kit": ("pharmacy",),
}


def test_config_names_match_the_labels_stored_in_the_file():
    """Every semantic name in config must be supported by the file's own label.

    `test_every_variable_the_design_depends_on_exists` checks only that the
    columns are present — it would pass just as happily if `qc7_1` had been
    named `power` instead of `water`, and every downstream figure would then be
    confidently wrong about which lifeline binds.

    This asserts the *meaning*: at least one distinguishing word of the name the
    project uses must appear in the variable label the survey itself stores. It
    is what makes the mapping in config.py verifiable rather than merely asserted.
    """
    pyreadstat = pytest.importorskip("pyreadstat")
    _, meta = pyreadstat.read_sav(str(config.EB547_SAV), metadataonly=True)
    labels = meta.column_names_to_labels

    mappings = {}
    for group in (config.QC6_ITEMS, config.QC7_DOMAINS, config.QC5_ITEMS,
                  config.QC8_ITEMS, config.DEMOGRAPHIC_ITEMS):
        mappings.update(group)

    unsupported = []
    for variable, name in mappings.items():
        label = labels.get(variable, "").lower()
        tokens = [t for t in name.split("_") if len(t) > 2]
        tokens += list(SEMANTIC_ALIASES.get(name, ()))
        if not any(token.lower() in label for token in tokens):
            unsupported.append(f"{variable} -> '{name}' but the file says '{labels.get(variable)}'")

    assert not unsupported, (
        "config names that the source file does not support:\n  "
        + "\n  ".join(unsupported)
        + "\n\nEither the name is wrong, or it is a defensible rendering that "
          "belongs in SEMANTIC_ALIASES with the reason."
    )


def test_the_horizon_domains_are_not_transposed():
    """The specific mix-up that would invert the flagship finding.

    RHI reports water as the binding lifeline for 58% of households. If qc7_1 and
    qc7_2 were swapped in config, that sentence would name the wrong utility and
    nothing else in the pipeline would notice.
    """
    pyreadstat = pytest.importorskip("pyreadstat")
    _, meta = pyreadstat.read_sav(str(config.EB547_SAV), metadataonly=True)
    labels = meta.column_names_to_labels

    expected_keyword = {
        "qc7_1": "water", "qc7_2": "elec", "qc7_3": "gas",
        "qc7_4": "food", "qc7_5": "medication",
    }
    for variable, keyword in expected_keyword.items():
        assert keyword in labels[variable].lower(), (
            f"{variable} is '{labels[variable]}', which does not mention {keyword!r} — "
            "the qc7 domains may have been renumbered in this file version"
        )
