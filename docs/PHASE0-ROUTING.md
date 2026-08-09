# Phase 0 — routing stack decision

**Decision: `pyrosm` (primary path). Verified working end to end on 2026-08-06.**
The `osmium` fallback is not needed and stays unused, but the `[geo-osmium]` extra
remains in `pyproject.toml` in case a future machine has no compiler.

---

## The problem, and the one-line fix

`pyrosm` ships a cp311 Windows wheel, but its dependency **`cykhash` ships no wheels
for any platform** — source tarball only, so it must compile.

The first attempt failed:

```
building 'cykhash.khashsets' extension
error: Unable to find a compatible Visual Studio installation.
ERROR: Failed building wheel for cykhash
```

This is **not** a missing compiler. MSVC Build Tools 14.44 and Windows SDK
10.0.26100 are installed, `vswhere` reports the `VC.Tools.x86.x64` component, and
`vcvarsall.bat x64` initialises cleanly. The problem is that pip's **build
isolation** starts a fresh subprocess whose setuptools does not locate the
toolchain.

**The fix: run pip from inside an initialised MSVC environment.**

```powershell
$vc = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
$py = "C:\Users\agnia\YNOV\RNCP\actionwise-data\.venv\Scripts\python.exe"
cmd /c "`"$vc`" x64 >nul && `"$py`" -m pip install -e `".[geo]`""
```

`cykhash` then builds a wheel in a few seconds and is cached, so this is a
**one-time** step — ordinary `pip install` works from then on.

Installed: `geopandas` 1.1.4 · `pyrosm` 0.13.1 · `shapely` 2.1.2 · `pyproj` 3.7.2 ·
`pyogrio` 0.13.0 · `networkx` 3.6.1 · `cykhash` 2.0.1 (locally built).

## Verified parse

```
pyrosm.OSM("latvia-260804.osm.pbf").get_network(nodes=True, network_type="driving")
→ 1,346,594 nodes · 1,380,480 edges · 73.2 s · EPSG:4326
```

Tag parsing spot-checked against roads whose class is known independently:

| ref | OSM class | maxspeed |
|---|---|---|
| A1 | `trunk` (1,262) + `trunk_link` (274) | 90 / 80 / 70 / 50 |
| A2 | `trunk` (2,692) + `trunk_link` (215) | 90 / 70 / 50 / 30 |
| P1 | `primary` (828) | 90 / 70 / 50 / 40 |
| V173 | `secondary` (345) | **none tagged** |

That last row is the pattern, not an exception — see below.

## Four measured facts that shape Phase 3

1. **`maxspeed` is tagged on only 18.5% of drivable edges** (255,109 of 1,380,480).
   `DEFAULT_SPEEDS_KMH` therefore drives **four fifths** of the network — including
   156,939 secondary and 37,463 primary edges. Coverage is worst on exactly the
   rural roads this project is about. This is why `EMERGENCY_SPEED_FACTORS` is
   reported as a range rather than a chosen number: the speed model, not the
   routing, is the dominant source of uncertainty.

2. **`maxspeed` is a string.** 18 edges carry `RU:urban` / `RU:rural` — implicit-speed
   conventions near the eastern border. Coerce with `errors="coerce"`; a plain cast
   raises. Numeric values observed: 2, 5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 120.

3. **`oneway` is present on 8.6% of edges.** Absent means two-way in OSM semantics.
   Treating null as "unknown" and dropping it would delete 91% of the network.

4. **`ref` is populated on 314,580 edges** — the join key to the km markers and the
   traffic workbooks. It needs the same whitespace normalisation as `AC_INDEX`
   (`"V 1398"` vs `"V1398"`).

## Reproducing on another machine

If `cykhash` cannot be built at all (no MSVC), switch to the fallback:

```bash
pip install -e ".[geo-osmium]"
```

and assemble the graph from `osmium`'s way→node references instead. `osmium` 4.3.1
ships a cp311 wheel and needs no compiler. Cost: roughly 150 lines of graph
assembly that `pyrosm` otherwise provides. Nothing else in the project changes —
only `network/graph.py` would differ.
