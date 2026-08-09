"""Centralised paths, CRS constants, legal thresholds and speed defaults.

Project #2 (Time-to-Help). Sibling to `actionwise.config`, which serves project #1
(the EB547 survey indices). Nothing here is recomputed elsewhere — if a number is
used in two places, it lives here.

Every data fact below was verified by reading the file itself on 2026-08-06, not
taken from portal metadata. Where portal metadata and the file disagree, the file
wins and the disagreement is recorded — see `VUGD_STATIONS_XLSX`.
"""
from pathlib import Path

from actionwise.config import DATA_RAW, ROOT  # one path convention, not two

# ---------------------------------------------------------------------------
# Coordinate reference systems
# ---------------------------------------------------------------------------
# Everything in this project works in metres. LKS-92 / Latvia TM is the national
# metric grid, and it is what the authoritative depot file and the boundaries
# GeoPackage already use — so those two overlay with no reprojection at all.
#
# The rule: reproject INTO 3059 at the edge of the pipeline, never out of it.
# Degrees are useless for distance, and a silent degree/metre mix is the single
# most likely way for this project to produce confident nonsense.
CRS_WORKING = 3059      # LKS-92 / Latvia TM — metres
CRS_WGS84 = 4326        # OSM, km markers — degrees
CRS_ETRS89_LAEA = 3035  # Eurostat census grid — metres, EU-wide

# Latvia's extent in EPSG:3059, from the boundaries GeoPackage's own header.
# Used as a cheap assertion that a frame is in the CRS it claims to be in: the
# 99-row VUGD xlsx claims 3059 in its metadata and fails this by six orders of
# magnitude, because its values are actually degrees.
LV_BBOX_3059 = (312835.0, 172932.0, 762535.0, 438866.0)

# ---------------------------------------------------------------------------
# Source files — all under RNCP/dati/, read-only
# ---------------------------------------------------------------------------

# 87 operational depots, columns: id, nosaukums, adrese, epasts,
# regiona_piederiba, telefons, x, y. Coordinates verified inside LV_BBOX_3059.
VUGD_DEPOTS_CSV = DATA_RAW / "vugd_depo_adreses.csv"
VUGD_N_DEPOTS = 87

# The other VUGD file. 99 rows, and the portal says LKS-92 — but the values are
# WGS84 degrees (x=27.67 is a longitude, not a metre easting). It also comes from
# the *property* register, so it includes administrative buildings, not only
# operational depots. Cross-check only; never a source.
VUGD_STATIONS_XLSX = DATA_RAW / "valsts_ugunsdzesibas_un_glabsanas_dienests.xlsx"

# 42 features = 7 valstspilsētas + 35 novadi, EPSG:3059, single layer.
# Columns: fid, geom (MULTIPOLYGON), nosaukums, atrib (7-digit ATVK-family code).
#
# Latvia has 36 novadi. Varakļānu nov. is ABSENT from this file — do not treat
# 42 as complete. NMPD reports Varakļāni separately, which is how the gap shows up.
BOUNDARIES_GPKG = DATA_RAW / "administrativas_teritorijas_2026.gpkg"
BOUNDARIES_LAYER = "administrativas_teritorijas_2026"
BOUNDARIES_N_FEATURES = 42
BOUNDARIES_N_CITIES = 7
BOUNDARIES_MISSING = ("Varakļānu nov.",)

# Pre-reform geometry + the 120-row crosswalk. The traffic series spans 2012-2023,
# straddling the 1 July 2021 reform, so anything aggregated across that boundary
# needs the crosswalk or it silently mismatches.
BOUNDARIES_2021_ZIP = DATA_RAW / "administrativas_teritorijas_2021.zip"
BOUNDARIES_CROSSWALK_CSV = DATA_RAW / "admin_teritoriju_parejas_tab_43_pasv.csv"

# Eurostat census grid. The 566 MB archive holds five renderings of the same data;
# only the parquet is worth touching (76 MB vs 1.3 GB for the GeoPackage), and
# zipfile handles are seekable, so it is read in place and never extracted.
POPGRID_ZIP = DATA_RAW / "Eurostat_Census-GRID_2021_V3.zip"
POPGRID_MEMBER = "Eurostat_Census-GRID_2021_V3/ESTAT_Census_2021_V3.parquet"
POPGRID_ROWS_EU = 4_595_932        # all countries; filter CNTR_ID first
POPGRID_COUNTRY = "LV"
POPGRID_CELL_M = 1000              # 1 km cells

# Columns kept. T is total population; the age bands matter because "how many
# over-65s live beyond the legal response time" is a far sharper finding than
# the same sentence about the general population.
POPGRID_COLUMNS = ("GRD_ID", "T", "Y_LT15", "Y_1564", "Y_GE65", "LAND_SURFACE",
                   "POPULATED", "CNTR_ID")

# Latvia: 64,636 cells, of which 29,587 hold population. T sums to 1,888,613 —
# 0.24% under the census figure, comfortably inside SANITY_POPULATION_TOLERANCE.
POPGRID_LV_CELLS = 64_636
POPGRID_LV_POPULATED_CELLS = 29_587
POPGRID_LV_POPULATION = 1_888_613

# `GRD_ID` encodes the cell's lower-left corner in EPSG:3035, in metres:
#   "CRS3035RES1000mN3731000E5018000" -> N=3,731,000  E=5,018,000
# The centroid is corner + 500 m. There is no coordinate column; this string IS
# the geometry.
POPGRID_GRD_ID_RE = r"^CRS(?P<crs>\d+)RES(?P<res>\d+)mN(?P<north>\d+)E(?P<east>\d+)$"

# ⚠ -9999 is a CONFIDENTIALITY SENTINEL on the three age bands, never on T.
# Summed naively, Y_GE65 totals -211,308,180 instead of a population count.
#
# It is not missing at random, and the bias runs against this project:
#   * 19,139 of 29,587 populated cells (65%) have their age bands suppressed
#   * those cells hold only 92,106 people (4.9% of the population)
#   * median population is 4 in a suppressed cell vs 22 in an unsuppressed one
#
# So suppression targets SPARSE cells — which are exactly the remote ones the
# 23-minute analysis is about. Any "share of over-65s beyond the legal threshold"
# must therefore be reported with its coverage stated, because the age detail is
# thinnest precisely where the travel times are longest.
POPGRID_SUPPRESSED = -9999
POPGRID_AGE_BANDS = ("Y_LT15", "Y_1564", "Y_GE65")
POPGRID_LV_AGE_SUPPRESSED_CELLS = 19_139
POPGRID_LV_AGE_COVERED_POPULATION_SHARE = 0.951

# The age bands are perturbed for disclosure control, so they do NOT reconcile to
# T cell by cell — they match on only 11% of usable cells, while agreeing to
# within 78 people nationally. Never assert Y_LT15 + Y_1564 + Y_GE65 == T.
POPGRID_BANDS_RECONCILE_TO_TOTAL = False

# `LAND_SURFACE` is a FRACTION of the cell that is land (0.0-1.0), not an area.
# Density is T / (LAND_SURFACE * 1 km²), not T / 1 km² — using the raw cell area
# understates density on every coastal, riverside and lakeside cell, which in
# Latvia includes most of the larger towns. No populated cell has LAND_SURFACE 0.
POPGRID_LAND_SURFACE_IS_FRACTION = True

# `POPULATED` is not the same as T > 0: 2,031 cells are flagged populated but
# carry T == 0 (rounded away). The reverse never happens. Filter on T, not on
# this flag.
POPGRID_POPULATED_FLAG_UNRELIABLE = True

# One row is not a cell at all. `LV_unallocated` carries 4,844 people who could
# not be assigned to any grid square — real population with no location.
#
# It has to be kept and flagged, not dropped, because the two denominators it
# sits between are both legitimate and must not be confused:
#   * the NATIONAL total (1,888,613) includes it, and is what reconciles to the
#     census;
#   * the MAPPABLE total (1,883,769) excludes it, and is the only correct
#     denominator for "share of people within X minutes".
# Dropping it silently makes every coverage share disagree with the census by
# 0.26% for no visible reason.
POPGRID_UNALLOCATED_SUFFIX = "_unallocated"
POPGRID_LV_UNALLOCATED_POPULATION = 4_844

# Dated OSM snapshot. Never `latvia-latest` — that URL points at a different file
# every day, and a pipeline built on it cannot be reproduced or explained.
OSM_PBF = DATA_RAW / "latvia-260804.osm.pbf"
OSM_SNAPSHOT_DATE = "2026-08-04"

# Measured on 2026-08-06 with pyrosm 0.13.1, network_type="driving": the parse
# takes ~73 s and yields 1,346,594 nodes / 1,380,480 edges in EPSG:4326.
# Loose tolerances — these guard against a truncated or swapped file, not against
# OSM's normal churn.
OSM_EXPECTED_NODES = 1_346_594
OSM_EXPECTED_EDGES = 1_380_480
OSM_COUNT_TOLERANCE = 0.05

# Tag facts, all measured on this snapshot. The first one is the important one:
#
#   * `maxspeed` is tagged on only 18.5% of drivable edges (255,109 of 1,380,480).
#     DEFAULT_SPEEDS_KMH therefore drives FOUR FIFTHS of the network, including
#     156,939 secondary and 37,463 primary edges. It is not a minor fallback, and
#     that is the main reason EMERGENCY_SPEED_FACTORS is reported as a range.
#     Untagged coverage is worst on exactly the rural roads the project is about.
#   * `maxspeed` is a STRING. 18 values are non-numeric ("RU:urban", "RU:rural" —
#     implicit-speed conventions near the eastern border). Coerce, do not cast.
#     Numeric values observed: 2, 5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 120.
#   * `oneway` is present on 8.6% of edges. Absent means two-way, per OSM
#     semantics — treating null as "unknown" and dropping it would delete 91% of
#     the network.
#   * `ref` is populated on 314,580 edges. It is the join key to the km markers
#     and the traffic workbooks, and it needs the same whitespace normalisation
#     as AC_INDEX ("V 1398" vs "V1398").
OSM_MAXSPEED_TAGGED_SHARE = 0.185
OSM_NONNUMERIC_MAXSPEED = ("RU:urban", "RU:rural")
OSM_REF_TAGGED_EDGES = 314_580

# 20,853 rows, all IS_ACTIVE=1, 1,264 distinct roads — and four traps, all of
# which produce a plausible wrong join rather than an error:
#
#   1. `KM` is a STRING, not a number, and inconsistently formatted: 11,311 plain
#      integers ("22"), 9,542 float-formatted ("9.7", "8.0"), 19 literal "***".
#      It is also ROUNDED — marker "V 1398km23.749" carries KM=24. Use SEARCH_STR
#      for chainage and KM only as a cross-check.
#   2. 45 rows are entirely null (AC_INDEX, KM and SEARCH_STR all NaN).
#      After dropping those and the 19 "***", 20,789 rows remain usable, and
#      SEARCH_STR then parses with ZERO failures.
#   3. `AC_INDEX` carries stray whitespace on 35 rows — "V 1398", "V  1376"
#      (double space). Normalise it before joining to the traffic data's
#      `Ceļa Nr.`, or those roads silently fail to match. With whitespace
#      stripped, AC_INDEX and the SEARCH_STR prefix disagree on exactly 1 row.
#   4. At least one marker belongs to SEVERAL roads at once —
#      "P36; P54; P55; V579; V580" is a junction. It cannot be joined 1:1 and
#      must be split or quarantined deliberately.
KM_MARKERS_CSV = DATA_RAW / "CSV_LVC_KM.csv"
KM_MARKERS_ROWS = 20_853
KM_MARKERS_USABLE_ROWS = 20_789
KM_MARKERS_CHAINAGE_COL = "SEARCH_STR"
KM_MARKERS_NULL_SENTINEL = "***"
KM_MARKERS_MULTI_ROAD_SEP = ";"
# "V173km22.331" -> road "V173", chainage 22.331
KM_MARKERS_CHAINAGE_RE = r"^(?P<road>.+?)km(?P<chainage>[0-9]+\.?[0-9]*)$"

# Traffic intensity. Two workbooks, three sheets each, overlapping on 2014-2021 —
# which gives a free consistency check and a 2012-2023 union.
TRAFFIC_XLSX_2014_2023 = DATA_RAW / "satiksmes-dati-2014_2023.xlsx"
TRAFFIC_XLSX_2012_2021 = (
    DATA_RAW
    / "satiksmes-intensitate-valsts-autocelos-galvenajos-regionalajos-un-vietejos-laika-no-2012.-lidz-.xlsx"
)
TRAFFIC_SHEETS = ("Galvenie", "Reģionālie", "Vietējie")
TRAFFIC_EXPECTED_ROWS = {
    TRAFFIC_XLSX_2014_2023.name: {"Galvenie": 111, "Reģionālie": 397, "Vietējie": 1427},
    TRAFFIC_XLSX_2012_2021.name: {"Galvenie": 110, "Reģionālie": 391, "Vietējie": 1413},
}
# The schemas differ per sheet and must be normalised:
#   * road name column is `posms` in Galvenie, `ceļa nosaukums` in the others
#   * first year is `2014` in one workbook, `≤2014` in the other
#   * heavy-vehicle share is `'2014\nKT%'` in Galvenie, `'2014 KT%'` elsewhere
#   * Galvenie carries ~102 junk `Unnamed:` columns from merged header cells
# And the one that silently corrupts everything if missed:
#   * `Ceļa Nr.` is null on 96 of 111 Galvenie rows. NaN means "same road as the
#     row above", so it MUST be forward-filled before any join.
TRAFFIC_ROAD_COL = "Ceļa Nr."
TRAFFIC_JUNK_COL_PREFIX = "Unnamed:"

# Header spellings actually present across the six sheets, after lowercasing and
# collapsing whitespace. Every one of these is a real variant in the files:
#   road number  "Ceļa Nr."      vs "ceļa Nr."          (case)
#   road name    "posms" vs "ceļa nosaukums" vs "Ceļa nosaukums"
#   chainage     "no km"         vs "no\nkm"            (embedded newline)
#   first year   "2014"          vs "≤2014"             (censored band)
#   heavy share  "2014\nKT%"     vs "2015 KT%"          (newline vs space)
TRAFFIC_ROAD_ALIASES = ("ceļa nr.", "ceļa nr")
TRAFFIC_NAME_ALIASES = ("posms", "ceļa nosaukums")
TRAFFIC_KM_FROM_ALIASES = ("no km",)
TRAFFIC_KM_TO_ALIASES = ("līdz km",)

# Road numbers are written "A-14" on the Galvenie sheets and "P99" / "V1487"
# elsewhere, while OSM writes "A14" and the km markers write "V 1398". Every
# join in this phase goes through the same normaliser: strip spaces and hyphens,
# uppercase. Measured match rate against OSM `ref` afterwards: 1,296 of 1,322
# roads (98.0%).
TRAFFIC_ROAD_MATCH_RATE = 0.98

# AADT is left-censored at 100 vehicles/day, written "≤100". Parsed as 100 and
# flagged, never dropped and never coerced to null: these are the quietest roads
# in the country, which is exactly where response times are longest.
TRAFFIC_CENSORED_TOKEN = "≤"
TRAFFIC_CENSORED_LOW_AADT = 100.0

# ---------------------------------------------------------------------------
# Congestion model (Phase 5)
#
# Standard BPR (Bureau of Public Roads) delay function:
#
#     t = t_free * (1 + alpha * (V/C)^beta)
#
# with the conventional alpha=0.15, beta=4. V is the peak-hour directional
# volume derived from AADT; C is capacity.
# ---------------------------------------------------------------------------
BPR_ALPHA = 0.15
BPR_BETA = 4.0

# K-factor: share of daily traffic in the peak hour. D-factor: share of that
# travelling in the busier direction. Both are standard planning values.
PEAK_HOUR_SHARE = 0.10
DIRECTIONAL_SPLIT = 0.55

# Capacity in vehicles per hour per direction, by OSM highway class.
LANE_CAPACITY_VPH = {
    "motorway": 4000, "motorway_link": 1500,
    "trunk": 1800, "trunk_link": 1200,
    "primary": 1600, "primary_link": 1000,
    "secondary": 1400, "secondary_link": 900,
    "tertiary": 1200, "tertiary_link": 800,
    "unclassified": 900, "residential": 800, "living_street": 300,
    "service": 300, "road": 900, "track": 200,
}
DEFAULT_LANE_CAPACITY_VPH = 900

# How much of the general-traffic delay an emergency vehicle actually suffers.
#
# Not a detail. Latvian law requires traffic to yield to a blue-light vehicle,
# and crews use the oncoming lane and the hard shoulder — so a fire engine does
# NOT sit in the queue that BPR describes. Applying the full delay would
# overstate rural-versus-urban differences in the direction that flatters the
# project's own thesis.
#
# 0.0 = unaffected (identical to free-flow), 1.0 = delayed exactly like a car.
# Reported across the range; the middle value is the one quoted, with the spread.
EMERGENCY_CONGESTION_DAMPING = (0.0, 0.5, 1.0)

# NMPD priority 1-2 ambulance response, 4 files x 37 rows.
NMPD_DIR = DATA_RAW / "nmpd"
NMPD_YEARS = (2022, 2023, 2024, 2025)
NMPD_PARTIAL_YEARS = (2025,)   # ~93k calls vs ~217k in a full year — never a level
NMPD_AGGREGATE_ROW = "Valstspilsēta"   # not a municipality: all 7 cities in one row
NMPD_MATCHED_NOVADI = 35               # of 37 rows; see NMPD_UNMATCHED

# ---------------------------------------------------------------------------
# The legal standard — this project's success criterion
#
# MK noteikumi Nr. 297, "Kārtība, kādā Valsts ugunsdzēsības un glābšanas dienests
# veic un vada ugunsgrēku dzēšanu un glābšanas darbus", adopted 17.05.2016, in
# force 20.05.2016 (replacing Nr. 61 of 2004).
# https://likumi.lv/ta/id/282206
#
# These are not chosen bands. The regulation expresses its thresholds as travel
# time measured from depot departure — exactly the quantity a network model
# computes — so the model is scored against Latvian law rather than against a
# number someone picked because it looked round.
# ---------------------------------------------------------------------------

# 5. punkts — "izbrauc no daļas vai posteņa garāžas 90 sekunžu laikā pēc
# nosūtīšanas uz notikuma vietu."
TURNOUT_MINUTES = 1.5

# 6.1. punkts — "pilsētā, ciemā un mazciemā, kur IR Valsts ugunsdzēsības un
# glābšanas dienesta daļa vai postenis, – astoņu minūšu laikā"
ARRIVAL_TARGET_SERVED_MIN = 8.0

# 6.2. punkts — "pilsētā, ciemā, mazciemā, kur NAV ... daļas vai posteņa, kā arī
# citā novada teritorijā – 23 minūšu laikā"
ARRIVAL_TARGET_UNSERVED_MIN = 23.0

# Note the unit of the 8-minute rule: it attaches to the *settlement* (pilsēta /
# ciems / mazciems) that contains a depot, NOT to the municipality. OSM's
# place=city|town|village|hamlet maps onto those three terms directly, which is a
# closer operationalisation than a density threshold — see SETTLEMENT_PLACE_TAGS.
SETTLEMENT_PLACE_TAGS = ("city", "town", "village", "hamlet")

# The superseded 2004-2016 standard, kept because the only published performance
# figures are measured against it: average arrival 9.2 min, and only 11% of calls
# in the largest cities met the then-5-minute target.
LEGACY_TARGETS_MIN = {"city": 5.0, "density_ge_10_per_km2": 15.0, "sparse": 25.0}
LEGACY_NATIONAL_MEAN_ARRIVAL_MIN = 9.2

# ---------------------------------------------------------------------------
# NMPD's standard — a DIFFERENT regulation, used only for validation
#
# MK noteikumi Nr. 555 (2018): 75% of life-threatening calls answered within
# 12 min in Rīga/Liepāja/Daugavpils/Rēzekne, 15 min in other cities, 25 min rural.
#
# This is why the published `no_tiem_izpild_savl_proc` must NOT be read as speed.
# The cities aggregate scores 73.1% while rural novadi reach 92.5% — because the
# urban target is 12 minutes and the rural one is 25, not because ambulances are
# slower in Rīga. Any correlation of model travel time against that column
# directly is measuring the threshold, not the geography.
# ---------------------------------------------------------------------------
NMPD_TARGET_MIN = {"major_city": 12.0, "city": 15.0, "rural": 25.0}
NMPD_MAJOR_CITIES = ("Rīga", "Liepāja", "Daugavpils", "Rēzekne")
NMPD_COMPLIANCE_STANDARD = 0.75

# ---------------------------------------------------------------------------
# Network model parameters
# ---------------------------------------------------------------------------

# Fallback speeds in km/h where OSM carries no `maxspeed` tag, by highway class.
# Legal limits, deliberately: the emergency-vehicle uplift is applied separately
# and reported as a sensitivity, never baked in here.
DEFAULT_SPEEDS_KMH = {
    "motorway": 110, "motorway_link": 70,
    "trunk": 90, "trunk_link": 60,
    "primary": 90, "primary_link": 55,
    "secondary": 80, "secondary_link": 50,
    "tertiary": 70, "tertiary_link": 45,
    "unclassified": 60, "residential": 50, "living_street": 20,
    "service": 20, "road": 50, "track": 25,
}

# Emergency vehicles lawfully exceed posted limits. Rather than pick one
# multiplier and call the result a fact, every headline number is reported at
# both — the spread IS the uncertainty statement.
EMERGENCY_SPEED_FACTORS = (1.0, 1.2)

# A 1 km grid centroid should sit close to a road. Anything further is a data
# problem (an offshore cell, a graph island), and gets flagged and counted rather
# than quietly absorbed into the results.
MAX_SNAP_DISTANCE_M = 2000.0

# ---------------------------------------------------------------------------
# Phase 2 sanity gate — nothing downstream is trusted until these reproduce.
# Same discipline as actionwise.config.PUBLISHED_MARGINALS.
# ---------------------------------------------------------------------------
POPULATION_LV_CENSUS_2021 = 1_893_223   # CSP, census of 1 January 2021
SANITY_POPULATION_TOLERANCE = 0.03      # relative

# Rīga holds about a third of the country — the "every third resident" figure CSP
# publishes. A spatial check, unlike the national total: it fails if the grid and
# the boundaries are individually fine but joined wrongly.
RIGA_POPULATION_SHARE = (0.30, 0.35)

# 100 populated cells fall outside every territory, holding 3,735 people (0.2%).
# All sit within 558 m of land (median 144 m) — 1 km centroids landing just
# offshore where the coastline cuts a cell.
#
# The distance is the whole check. Coastal rounding puts cells a few hundred
# metres out; a broken CRS puts them hundreds of kilometres out. Same symptom,
# and only the distance separates them.
SANITY_MAX_OFFSHORE_M = 1_000.0
SANITY_MAX_UNPLACED_POPULATION_SHARE = 0.01

# The depot file's own regional breakdown, used to catch a truncated read.
DEPOTS_PER_REGION = {
    "Rīgas reģiona pārvalde": 20,
    "Vidzemes reģiona pārvalde": 19,
    "Latgales reģiona pārvalde": 18,
    "Zemgales reģiona pārvalde": 17,
    "Kurzemes reģiona pārvalde": 13,
}

# Eurostat DEGURBA density thresholds (people per km²). Official definitions, so
# the urban/rural split is citable rather than invented.
DEGURBA_URBAN_CENTRE_MIN = 1500
DEGURBA_URBAN_CLUSTER_MIN = 300

# ---------------------------------------------------------------------------
# Settlements — which cells the 8-minute standard actually applies to
#
# MK 297 p. 6.1 grants 8 minutes "pilsētā, ciemā un mazciemā, kur IR ... daļa vai
# postenis" — in the *settlement* holding a unit, not the municipality. So
# settlements have to be delineated, and they are grown by contiguity on the
# census grid rather than by drawing a radius around a town centre.
#
# A density floor is unavoidable. Measured on this grid:
#
#   floor   clusters   largest cluster        share of population
#   0            679   24,039 cells                      88.5%   <- one blob
#   50           890      535 cells                      39.8%
#   100          655      363 cells                      36.4%
#   300          252      214 cells                      34.1%
#
# With no floor, rural Latvia is contiguous and "settlement" swallows the country.
#
# The floor is 50, not DEGURBA's 300, because the regulation names ciems and
# mazciems explicitly and 300 excludes them: only 66 of 87 depots sit in a cell
# that dense, so 21 rural posteņi would be denied a standard they legally have.
# Every headline figure is reported across all three floors — the spread is the
# uncertainty about where a settlement ends.
SETTLEMENT_DENSITY_FLOOR = 50
SETTLEMENT_FLOOR_SENSITIVITY = (50, 100, 300)

# 8-connectivity: cells touching at a corner are the same settlement. The
# alternative (4-connectivity) splits diagonal ribbon development along a road,
# which is the commonest settlement shape in rural Latvia.
SETTLEMENT_CONNECTIVITY = 8

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
DATA_GEO_INTERIM = ROOT / "data" / "interim" / "geo"
DATA_GEO_PROCESSED = ROOT / "data" / "processed" / "geo"

# All tables this project writes carry the geo_ prefix, so Phase 8's conditional
# dashboard registration and the removal procedure are both one-liners.
DUCKDB_TABLE_PREFIX = "geo_"
