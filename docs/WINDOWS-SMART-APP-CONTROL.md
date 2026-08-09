# Windows Smart App Control and this project

**Symptom.** Anything from *"Permission denied"* running `streamlit`, to this on a
plain `import pandas`:

```
ImportError: DLL load failed while importing indexing:
Une stratégie de contrôle d'application a bloqué ce fichier.
```

Windows also pops a notification: *"Une partie de cette application a été bloquée —
nous ne pouvons pas confirmer **qui a publié** jupyter.exe"*.

**Cause.** Smart App Control (SAC), a Windows 11 feature that blocks executables and
DLLs it cannot attribute to a known publisher. Check its state:

```powershell
(Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy").VerifiedAndReputablePolicyState
# 0 = Off   1 = Enforced   2 = Evaluation
```

A Python virtual environment is full of exactly what SAC distrusts: pip-generated
`.exe` launchers and unsigned compiled `.pyd` extension modules.

---

## The two things that make this confusing

**It judges by reputation, so the same file can be fine one day and blocked the next.**
The full test suite passed on 2026-08-07 and `import pandas` failed on 2026-08-08 with
no change to the code or the environment. The verdict comes from a cloud service and can
move, and the policy itself can switch from Evaluation to Enforced on its own.

**There is no allowlist.** SAC has no exclusions, no per-file exception, no "allow
anyway", and no user-supplementable policy. This is deliberate in its design. The
Properties → **Unblock** checkbox does not apply either: that is for mark-of-the-web on
downloaded files, and these binaries do not carry one.

So the usual instincts — add an exception, unblock the file, allow the folder — all
lead nowhere.

---

## What was actually blocked here

Measured on 2026-08-08, in a venv where nothing had changed:

| Blocked | Loads fine |
|---|---|
| `pandas` 3.0.5 | numpy · scipy · pyarrow · duckdb · pyreadstat |
| `geopandas` · `shap` · `statsmodels` | shapely · pyproj · pyogrio · pyrosm · cykhash |
| `streamlit.exe` · `jupyter.exe` | lightgbm · sklearn · streamlit · plotly · matplotlib |

**Only pandas was genuinely blocked.** geopandas, shap and statsmodels failed because
they import it. `pytest.exe` ran while `streamlit.exe` and `jupyter.exe` did not, though
all three are near-identical 108 KB pip launchers — which is what reputation-based
blocking looks like from the inside.

---

## The fix used: pin pandas below 3.0

`pandas 3.0.5` was days old and had no reputation. `pandas 2.3.3` is widely deployed and
loads without complaint — it was already running under the *system* Python on the same
machine while the venv copy was blocked, which is what identified the cause.

```bash
python -m pip install "pandas>=2.2,<3.0"
```

`requirements.txt` carries the bound and the reason. **300 tests pass on 2.3.3**, so
nothing in either project depends on pandas 3 behaviour. Two places were already written
to tolerate both, and stayed correct:

- `fema/aci.py::_binary` tests `is_numeric_dtype` rather than `dtype == object`, so it
  handles pandas 3's inferred `str` dtype *and* pandas 2's `object`
- `groupby(...).apply(..., include_groups=False)` needs pandas ≥ 2.2, which the lower
  bound guarantees

One pandas-2-only deprecation surfaced and was fixed rather than silenced: an
`aadt_censored` column relied on `fillna` silently downcasting object → bool, and now
casts explicitly (`network/congestion.py`).

**Revisit the pin** once pandas 3.x has been in the wild long enough to earn reputation,
or on any machine with SAC off.

---

## If a pin stops being enough

SAC can block a different package tomorrow. In rough order of how much they cost:

1. **Pin the offender to an older, widely-deployed version.** What was done here. Cheap,
   reversible, keeps SAC on.
2. **Run through `python -m`.** Sidesteps blocked `.exe` launchers — `python -m streamlit
   run dashboard/app.py`, `python -m jupyter lab`, `python -m pytest`. Does *not* help
   when the block is on a `.pyd`, because Python itself is loading it.
3. **WSL2.** SAC does not apply to Linux binaries. Windows security stays fully intact.
   Costs a toolchain reinstall and re-pointing `DATA_RAW` at
   `/mnt/c/Users/.../RNCP/dati`; no code changes, since all paths come from `config.py`.
4. **Turn Smart App Control off.** Windows Security → App & browser control → Smart App
   Control → Off. Fixes everything permanently — and **cannot be undone** without
   resetting Windows. Defender antivirus, firewall and SmartScreen all remain; SAC is a
   layer above them. Standard on developer machines, but a one-way door.

---

*Recorded 2026-08-08, after the whole test suite went from 300 green to unrunnable
overnight with no code change.*
