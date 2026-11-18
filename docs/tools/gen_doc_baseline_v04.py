#!/usr/bin/env python3
"""gen_doc_baseline_v04.py - XC-FND-10 documentation baseline alignment.

Reads the v0.3 / v1.0 sources and writes new versions next to them (the sources are not
modified). Deterministic: running it twice gives identical files.

  RTM v0.3            -> 04a_REQUIREMENTS_TRACEABILITY_MATRIX_v0.4.csv
                         + FR-183..FR-193 (CN-2026-11-17, IDR-37), FR-194/FR-195 (IDR-28),
                         + IDR-35 status notes, + column v0.4_change
  Test catalogue v0.3 -> 09_TEST_CASE_CATALOGUE_v0.4.csv
                         + TC rows for FR-183..FR-195, + columns unit_test_ids (UT-<FN> from the
                         WBS function -> requirement mapping), fixture_sets (T1..T15 per kernel
                         module, DEVELOPMENT_TEST_PLAN_v1.1 §TT-V), v0.4_change
  (new)               -> 09b_TEST_FIXTURE_REGISTER_v0.4.csv (T1..T15, GTS §fixtures)
  Backlog v0.3        -> 09a_MVP_BACKLOG_v0.4.csv
                         BL-017 (IDR-01), BL-030 + BL-115 (DEC-020 / IDR-32) corrected,
                         BL-112 retired (IDR-32), + column v0.4_change
  ALGORITHM_CATALOG   -> ALGORITHM_CATALOG_v1.1.csv  + ALG-62, ALG-63 (CN-2026-11-17 §2)
  WBS v1.1 (in place) -> FR-194 added to FN-CAS-02 rows, FR-195 to FN-KMS-06 rows (IDR-28), so the
                         new requirements trace to tasks (idempotent; gen_wbs_v11.py needs FS.md,
                         which is not in the repository)

Usage: python docs/tools/gen_doc_baseline_v04.py   (from the repository root)
No requirement text here sets a clinical value, threshold or correction magnitude (DEC-029).
"""

import csv
import io
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "docs" / "design"
P = ROOT / "docs" / "plan"
WBS = P / "WORK_BREAKDOWN_STRUCTURE_v1.1.csv"

CN = "CN-2026-11-17"
CN_APPROVAL = "Approved by product owner 2026-11-17 (CN-2026-11-17 'согласна'; IDR-37 ratified 2026-11-17)"
IDR28_APPROVAL = "Approved by EL + PO 2026-11-17 (IDR-28, DECISION_RECORD_2026-11-17)"
REQ_RE = re.compile(r"\b(?:STK|UR|FR|NFR|DATA|INT|SEC|SAF|VER|AI)-\d+\b")


def read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fields})
    path.write_bytes(buf.getvalue().encode("utf-8"))
    print(f"wrote {path.relative_to(ROOT)} ({len(rows)} rows)")


def req_key(rid: str) -> tuple[int, int]:
    order = {"STK": 0, "UR": 1, "FR": 2, "NFR": 3, "DATA": 4, "INT": 5, "SEC": 6, "SAF": 7, "VER": 8, "AI": 9}
    t, n = rid.split("-")
    return order.get(t, 99), int(n)


# ---------------------------------------------------------------------------------------------
# New requirements. Text is derived from CN-2026-11-17 §1-2 (CH-01..CH-11), ALG-62/63, IDR-20,
# IDR-38 and the FN-CAS-02 / FN-KMS-06 specifications. Geometric behaviour only; every
# magnitude, level and profile value is a technician input with no default.
# ---------------------------------------------------------------------------------------------
NEW_REQS: list[dict[str, str]] = [
    dict(
        id="FR-183", title="Free-form zone contour on the surface",
        statement=(
            "The technician shall be able to define a zone by a closed contour of control points "
            "placed on the positive surface (anchored by face and barycentric coordinates), insert, "
            "delete and move control points, push the whole contour or one contour edge, and stretch "
            "the contour; circle and ellipse remain available as presets. The zone is a recorded, "
            "replayable operation."),
        rationale="CN-2026-11-17 CH-01: the clinic's current tool shapes zones freely; circle/ellipse only was a parity gap.",
        priority="Must", priority_rationale="MVP-Core per CN-2026-11-17 (CH-01)",
        dependencies="FR-050, FR-052, FR-180", capability="ODC-07", verified_by="VER-01, VER-08",
        acceptance=(
            'Contour with >= 3 anchored points defines the region and is stored in the op params; '
            'displacement inside follows the zone profile; vertices outside contour + transition are '
            'bit-identical; a self-intersecting contour is rejected with ZONE_CONTOUR_INVALID; point '
            'insert/delete/move recorded in op params; membership equals the exact winding result on '
            'fixture set T15; replay gives an identical geometry_sha'),
        functions="FN-KOP-14", alg="ALG-62", ch="CH-01"),
    dict(
        id="FR-184", title="Parametric zone transition profile",
        statement=(
            "The zone transition profile shall be an operation parameter: plateau or peak preset, or "
            "a custom monotone profile through technician-set points; the overall amplitude (mm) is a "
            "technician input with no default, and the resulting amplitude at a chosen vertex is "
            "shown. Plateau (smoothstep) is the preset offered first (IDR-20)."),
        rationale="CN-2026-11-17 CH-02; IDR-20 revised (profile is a parameter).",
        priority="Must", priority_rationale="MVP-Core per CN-2026-11-17 (CH-02)",
        dependencies="FR-050, FR-183", capability="ODC-07", verified_by="VER-01",
        acceptance=(
            'Profile evaluated monotone and C1 for the preset types; a custom curve with >= 2 points '
            'is interpolated without overshoot (T8 inputs); displacement at the plateau equals the '
            'amplitude within e = 0.011 mm (DEC-025); profile stored in op params and hashed; missing '
            'amplitude returns PARAM_NOT_SET'),
        functions="FN-KOP-15", alg="ALG-63", ch="CH-02"),
    dict(
        id="FR-185", title="Symmetric zone across the mid-sagittal plane",
        statement=(
            "The technician may link a zone to its mirror image across the mid-sagittal plane of the "
            "confirmed anatomical frame so that one edit changes both; mirroring acts on zone "
            "parameters only and never reflects stored geometry (SAF-03)."),
        rationale="CN-2026-11-17 CH-05; ALG-42 mirroring enters MVP as a design operation.",
        priority="Must", priority_rationale="MVP-Core per CN-2026-11-17 (CH-05)",
        dependencies="FR-050, FR-031, FR-183", capability="ODC-07", verified_by="VER-01",
        acceptance=(
            'Mirror zone centre/contour equals the reflection of the source within e (DEC-025); '
            'parameters linked (editing the source updates the mirror); laterality labels swap; '
            'refused without a confirmed frame (FRAME_NOT_CONFIRMED); the mirror is never applied to '
            'stored geometry as a reflection transform (every stored transform keeps det = +1)'),
        functions="FN-KOP-16", alg="ALG-42", ch="CH-05"),
    dict(
        id="FR-186", title="Live design metrics with deltas",
        statement=(
            "During design the workspace shall show, at a technician-movable level, the AP extent "
            "split into anterior and posterior parts, the ML extent, the circumference and the volume "
            "of the current positive, and CI/CVA/CVAI where a configured measurement definition "
            "exists, each with the difference (mm and %) from the prepared scan at the same level. "
            "Values are geometric measurements without interpretation (FR-045)."),
        rationale="CN-2026-11-17 CH-03: live H/AP/ML/Cir/Vol panel used during modelling.",
        priority="Must", priority_rationale="MVP-Core per CN-2026-11-17 (CH-03)",
        dependencies="FR-040, FR-045, FR-051", capability="ODC-06, ODC-07", verified_by="VER-01, VER-09",
        acceptance=(
            'Values match the kernel measurement functions (FN-KMS-01/03/05, volume ALG-12) on VER-01 '
            'phantoms within DEC-025; deltas computed against the prepared scan at the same level; '
            'refreshed after every regeneration; no thresholds or colour meaning beyond '
            'increase/decrease (VER-09 lint); definitions shown; indices only where a configured '
            'definition exists'),
        functions="FN-DES-08", alg="", ch="CH-03"),
    dict(
        id="FR-187", title="Original/modified overlay in the workspace",
        statement=(
            "The workspace shall show the prepared scan surface over the current positive with "
            "adjustable opacity and shall highlight the regions changed by the operation list."),
        rationale="CN-2026-11-17 CH-04: visual control during design, previously review-only (M5).",
        priority="Must", priority_rationale="MVP-Core per CN-2026-11-17 (CH-04)",
        dependencies="FR-070", capability="ODC-12", verified_by="VER-20",
        acceptance=(
            'Highlight equals the vertices with |deviation| > 0 from the latest regeneration; opacity '
            '0-100 %; display-only (no stored geometry from the client; hashes unchanged)'),
        functions="FN-UIX-07", alg="", ch="CH-04"),
    dict(
        id="FR-188", title="2D section comparison views",
        statement=(
            "The technician may view 2D transverse sections and silhouettes of the prepared scan and "
            "the current positive at chosen levels, side by side or overlaid."),
        rationale="CN-2026-11-17 CH-06.",
        priority="Should", priority_rationale="MVP-Should per CN-2026-11-17 (CH-06)",
        dependencies="FR-040, FR-187", capability="ODC-12", verified_by="VER-01, VER-20",
        acceptance=(
            'Contours equal the kernel sections (ALG-23) of both meshes at the same level within '
            'DEC-025; axes in mm; updated after regeneration; display-only'),
        functions="FN-UIX-08", alg="", ch="CH-06"),
    dict(
        id="FR-189", title="Elongation between two levels",
        statement=(
            'The technician may elongate or shorten the positive only between two technician-set '
            'levels along the frame axis by a technician-set delta (mm), as a recorded operation; the '
            'application zone is either the whole positive (FR-051) or the band between the two '
            'levels.'),
        rationale="CN-2026-11-17 CH-07: Elongate 2 Levels; whole-model length change exists (FR-051).",
        priority="Should", priority_rationale="MVP-Should per CN-2026-11-17 (CH-07)",
        dependencies="FR-051, FR-052", capability="ODC-08", verified_by="VER-01",
        acceptance=(
            'Extent between the two levels changes by the requested delta within 2e (DEC-025); '
            'geometry outside the band is translated rigidly, not deformed; delta = 0 is the '
            'identity; missing delta or level returns PARAM_NOT_SET'),
        functions="FN-KOP-17", alg="", ch="CH-07"),
    dict(
        id="FR-190", title="Filtering inside a zone",
        statement=(
            'The technician may enable optional filtering (smoothing) inside a zone as a zone '
            'parameter of the recorded operation; vertices outside the zone and its transition are '
            'unchanged.'),
        rationale="CN-2026-11-17 CH-08: Area filtering (Light).",
        priority="Should", priority_rationale="MVP-Should per CN-2026-11-17 (CH-08)",
        dependencies="FR-179, FR-183", capability="ODC-07", verified_by="VER-01",
        acceptance=(
            'Vertices outside zone + transition bit-identical to the input; filter level from {none, '
            'light, medium} recorded in the op params; the guard (FN-KOP-13) passes'),
        functions="FN-KOP-18", alg="", ch="CH-08"),
    dict(
        id="FR-191", title="Tape measure",
        statement=(
            'The technician may measure straight and along-section distances (mm) between two surface '
            'points snapped by the server; such ad-hoc values are labelled as ad-hoc, carry no '
            'measurement definition and are never stored as measurement records or used for approval.'),
        rationale="CN-2026-11-17 CH-09; INV-05 (no measurement value without a definition).",
        priority="Should", priority_rationale="MVP-Should per CN-2026-11-17 (CH-09)",
        dependencies="FR-041", capability="ODC-06", verified_by="VER-01, VER-20",
        acceptance=(
            'Straight distance exact on the snapped anchors; along-section length equals the contour '
            'arc within 0.032 mm (DEC-025 perimeter tolerance) on phantoms; values labelled as ad-hoc '
            '(not a measurement definition); no measurement_value row is created'),
        functions="FN-MEA-05", alg="", ch="CH-09"),
    dict(
        id="FR-192", title="Recorded orientation fine-tuning",
        statement=(
            'Before confirming the anatomical frame, the technician may adjust the computed frame by '
            'explicit shift (mm), tilt and twist (degrees); each adjustment is recorded as a '
            'transform step in the frame record, the frame stays rigid (det = +1), a reflection is '
            'refused and a reset returns to the landmark frame.'),
        rationale="CN-2026-11-17 CH-10: Shift / Balance / Twist.",
        priority="Should", priority_rationale="MVP-Should per CN-2026-11-17 (CH-10)",
        dependencies="FR-031, FR-032, FR-033, FR-046", capability="ODC-05", verified_by="VER-01, VER-20",
        acceptance=(
            'Adjustments are rigid (det = +1) and stored as transform steps in the frame record; '
            'reset returns to the landmark frame; a reflection is refused; only possible before frame '
            'confirmation'),
        functions="FN-ANA-06", alg="", ch="CH-10"),
    dict(
        id="FR-193", title="View cube and standard views",
        statement=(
            'The 3D viewer shall offer six standard views (anterior, posterior, left, right, '
            'superior, inferior) and a reset, aligned with the confirmed anatomical frame; without a '
            'confirmed frame the views use the file axes and say so.'),
        rationale="CN-2026-11-17 CH-11.",
        priority="Should", priority_rationale="MVP-Should per CN-2026-11-17 (CH-11)",
        dependencies="FR-031", capability="ODC-25", verified_by="VER-20",
        acceptance=(
            'Six standard views and reset; each view sets the camera to the frame axis direction; '
            'works on the display LOD; without a confirmed frame the label states that file axes are '
            'used'),
        functions="FN-UIX-09", alg="", ch="CH-11"),
    dict(
        id="FR-194", title="Case list and search",
        statement=(
            "Clinic admin and technician shall be able to list cases and search them by exact or "
            "prefix match on case ID or clinic reference; active cases are listed first and archived "
            "cases appear only when requested."),
        rationale="IDR-28 / OQ-FS-25: case list/search had no explicit requirement (GAP-M01).",
        priority="Must", priority_rationale="Necessary navigation for every case workflow (IDR-28)",
        dependencies="FR-001, FR-003, FR-004", capability="ODC-01", verified_by="VER-20",
        acceptance=(
            "Prefix search returns exactly the matching cases; archived cases hidden unless the "
            "archived toggle is set; the list shows only case ID, clinic reference, status and dates "
            "(DATA-10)"),
        functions="FN-CAS-02", alg="", ch=""),
    dict(
        id="FR-195", title="Warning for measurements over synthetic surface",
        statement=(
            "When a measurement contour or diagonal endpoint crosses faces marked synthetic "
            "(hole-filled, FR-021), the measurement value shall carry the synthetic_contact flag and "
            "the value shall be shown with a warning; the value is not suppressed."),
        rationale="IDR-28 / OQ-FS-27: FN-KMS-06 had no explicit requirement.",
        priority="Must", priority_rationale="Measurements over filled holes must be visible as such (IDR-28)",
        dependencies="FR-021, FR-040, FR-043", capability="ODC-06", verified_by="VER-01, VER-20",
        acceptance=(
            "On a T3 phantom whose contour crosses a filled hole, synthetic_contact = true and the "
            "warning is shown; with the contour away from the hole the flag is false"),
        functions="FN-KMS-06", alg="", ch=""),
]

# IDR-35: functions promoted to Core -> status note on their requirements (priority unchanged).
IDR35_FUNCTIONS = ["FN-AUD-03", "FN-AUD-04", "FN-AUD-05", "FN-BLB-03", "FN-OPS-03", "FN-OPS-07", "FN-DES-05"]


UNIT_TASK_RE = re.compile(r"^TSK-[A-Z]+-\d+(?:\.\d+)?-[KBAJ][A-Z]?$")  # TT-K/B/A/J carry UT-<FN>


def wbs_maps() -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]]]:
    """requirement -> functions, function -> requirements, requirement -> functions with
    unit-tested tasks (K/B/A/J; UI tasks use CT-, verification tasks GT-), from WBS v1.1."""
    _, rows = read(WBS)
    req_fns: dict[str, set[str]] = {}
    fn_reqs: dict[str, set[str]] = {}
    req_unit: dict[str, set[str]] = {}
    for w in rows:
        if w["level"] != "Task":
            continue
        fns = [f.strip() for f in w["function_id"].split(";") if f.strip().startswith("FN-")]
        for rid in REQ_RE.findall(w["requirement_ids"]):
            for fn in fns:
                req_fns.setdefault(rid, set()).add(fn)
                fn_reqs.setdefault(fn, set()).add(rid)
                if UNIT_TASK_RE.match(w["id"]):
                    req_unit.setdefault(rid, set()).add(fn)
    return req_fns, fn_reqs, req_unit


def build_rtm(fn_reqs: dict[str, set[str]]) -> list[str]:
    fields, rows = read(D / "04a_REQUIREMENTS_TRACEABILITY_MATRIX_v0.3.csv")
    fields = [*fields, "v0.4_change"]
    by_id = {r["id"]: r for r in rows}
    for r in rows:
        r["v0.4_change"] = "unchanged"

    promoted: dict[str, list[str]] = {}
    for fn in IDR35_FUNCTIONS:
        for rid in sorted(fn_reqs.get(fn, ()), key=req_key):
            promoted.setdefault(rid, []).append(fn)
    for rid, fns in promoted.items():
        if rid not in by_id:
            continue
        r = by_id[rid]
        note = (f"IDR-35: implementing function(s) {', '.join(fns)} promoted to MVP-Core; "
                "requirement priority unchanged")
        r["status_note"] = note if r["status_note"] in ("", "—") else f"{r['status_note']}; {note}"
        r["v0.4_change"] = "IDR-35: status_note"

    for n in NEW_REQS:
        approval = IDR28_APPROVAL if n["id"] in ("FR-194", "FR-195") else CN_APPROVAL
        source = ("IDR-28; OQ-FS-25/27; " + n["functions"]) if n["id"] in ("FR-194", "FR-195") else (
            f"{CN} {n['ch']}; IDR-37; {n['functions']}" + (f"; {n['alg']}" if n["alg"] else ""))
        rows.append({
            "id": n["id"], "type": "FR", "title": n["title"], "statement": n["statement"],
            "rationale": n["rationale"], "source": source,
            "evidence_tier": "Internal analysis" if n["id"] in ("FR-194", "FR-195") else "Owner decision",
            "priority": n["priority"], "priority_rationale": n["priority_rationale"],
            "release": "MVP", "actor": "Clinic admin, Technician" if n["id"] == "FR-194" else "Technician",
            "trigger": "—", "preconditions": "—", "inputs": "—", "main_behavior": "—", "outputs": "—",
            "error_behavior": "—", "dependencies": n["dependencies"], "capability": n["capability"],
            "verification_method": "T", "verified_by": n["verified_by"],
            "acceptance_criteria": n["acceptance"], "status": "Proposed", "status_note": "—",
            "owner": "Engineering lead", "v0.2_change": "—", "owner_approval": approval,
            "v0.3_change": "—", "v0.4_change": "new in v0.4 (" + ("IDR-28" if n["id"] in ("FR-194", "FR-195") else f"{CN} {n['ch']}") + ")",
        })
    rows.sort(key=lambda r: req_key(r["id"]))
    write(D / "04a_REQUIREMENTS_TRACEABILITY_MATRIX_v0.4.csv", fields, rows)
    return [r["id"] for r in rows]


# Fixture sets per kernel module (DEVELOPMENT_TEST_PLAN_v1.1, TT-V row) + FN-KOP-14 contours (T15).
MODULE_FIXTURES = {
    "KIO": ["T3", "T4"], "KVL": ["T3", "T13"], "KFR": ["T5", "T7"], "KAN": ["T1", "T14"],
    "KMS": ["T1", "T15"], "KOP": ["T1", "T2", "T6", "T8"], "KCP": ["T1", "T6"], "KRP": ["T9"],
    "KEX": ["T5", "T10"],
}
EXTRA_FIXTURES = {"FN-KOP-14": ["T15"], "FN-KOP-16": ["T14"], "XC-SHR-01": ["T13"]}


def fixture_sets(fns: set[str]) -> str:
    sets: set[str] = set()
    for fn in fns:
        m = re.match(r"FN-(K[A-Z]{2})-", fn)
        if m:
            sets.update(MODULE_FIXTURES.get(m.group(1), []))
        sets.update(EXTRA_FIXTURES.get(fn, []))
    return "; ".join(sorted(sets, key=lambda t: int(t[1:])))


def unit_tests(fns: set[str]) -> str:
    return "; ".join(f"UT-{fn}" for fn in sorted(fns))


def build_catalogue(req_fns: dict[str, set[str]], req_unit: dict[str, set[str]]) -> None:
    fields, rows = read(D / "09_TEST_CASE_CATALOGUE_v0.3.csv")
    fields = [*fields, "unit_test_ids", "fixture_sets", "v0.4_change"]
    for r in rows:
        rids = REQ_RE.findall(r["requirement"])
        fns = set().union(*(req_fns.get(rid, set()) for rid in rids))
        r["unit_test_ids"] = unit_tests(set().union(*(req_unit.get(rid, set()) for rid in rids))) or "—"
        r["fixture_sets"] = fixture_sets(fns) or "—"
        r["v0.4_change"] = "unit_test_ids, fixture_sets added"
    for n in NEW_REQS:
        fns = req_fns.get(n["id"], set()) | {n["functions"]}
        unit = req_unit.get(n["id"], set())
        geometric = "VER-01" in n["verified_by"]
        rows.append({
            "tc_id": f"TC-{n['id']}", "requirement": n["id"], "priority": n["priority"],
            "level": "Automated test (unit/API)", "suite": n["verified_by"],
            "fixture": "Synthetic analytic phantoms; fixture sets per fixture_sets" if geometric else "Seeded case fixture",
            "oracle_and_pass_criterion": n["acceptance"], "backlog_story": "—", "status": "Planned",
            "unit_test_ids": unit_tests(unit) or "—", "fixture_sets": fixture_sets(fns) or "—",
            "v0.4_change": "new in v0.4",
        })
    rows.sort(key=lambda r: (req_key(REQ_RE.findall(r["requirement"])[0]), r["tc_id"]))
    write(D / "09_TEST_CASE_CATALOGUE_v0.4.csv", fields, rows)


FIXTURES = [  # GEOMETRY_TESTING_STRATEGY_v1.0 fixture table (T13-T15 new)
    ("T1", "Analytic phantoms: icospheres R = 75 mm (s = 4…8), ellipsoids with known CI, asymmetric ellipsoid with known diagonal difference, torus", "Analytic + exact-on-mesh oracle", "Synthetic"),
    ("T2", "Open head-like surfaces with varied boundaries for closure", "Plane position, watertightness", "Synthetic"),
    ("T3", "Defect catalogue: holes of set perimeter, duplicates, flipped faces, non-manifold edge/vertex, self-intersections, ghost layer, extra component, degenerate faces, corrupt/empty/oversize/face-bomb files", "Seeded counts", "Synthetic"),
    ("T4", "Format set: same object in binary/ASCII STL, OBJ (quads, negative indices, textures), PLY ASCII/LE/BE", "Equal V/F after import", "Synthetic"),
    ("T5", "Laterality object", "Known side", "Synthetic"),
    ("T6", "Sign-convention sphere", "+m -> +m", "Synthetic"),
    ("T7", "Metamorphic rigid transforms (exact permutations/power-of-two scalings) and unit scalings", "Equality", "Synthetic"),
    ("T8", "Property-based random zones/magnitudes/offsets (hypothesis, fixed seed database)", "Valid or explicit rejection", "Synthetic"),
    ("T9", "Ten reference designs (incl. a ~20-operation history, CN-2026-11-17 CH-15)", "One hash each", "Synthetic"),
    ("T10", "Export round-trip with corruption injection", "Detection", "Synthetic"),
    ("T11", "Physical phantom", "Calliper/CMM", "Physical object"),
    ("T12", "Real clinic scans >= 3 (only after VER-22)", "Stable reports", "Real data - gated by VER-22 / SEC-17"),
    ("T13", "Adversarial predicate set: near-coplanar triangles, 1-ulp offsets, collinear contours, huge/small magnitudes", "Rational-arithmetic oracle (Python fractions)", "Synthetic"),
    ("T14", "Tie fixtures: equidistant faces, planes through vertices/edges", "Documented tie rules", "Synthetic"),
    ("T15", "Contour set: convex, concave, comb, spiral, near-touching necks", "Exact polygon area/simplicity", "Synthetic"),
]


def build_fixture_register() -> None:
    owner_task = {"T13": "XC-SHR-03", "T14": "XC-SHR-03", "T15": "XC-SHR-03"}
    rows = [{"fixture_set": t, "content": c, "oracle": o, "data_class": d,
             "built_by": owner_task.get(t, "see DEVELOPMENT_TEST_PLAN_v1.1"),
             "v0.4_change": "new in v0.4" if t in ("T13", "T14", "T15") else "registered in v0.4"}
            for t, c, o, d in FIXTURES]
    write(D / "09b_TEST_FIXTURE_REGISTER_v0.4.csv",
          ["fixture_set", "content", "oracle", "data_class", "built_by", "v0.4_change"], rows)


BACKLOG_FIXES = {
    "BL-017": dict(
        story=("As a technician, I want a design whose positive closure (base defined by explicit "
               "parameters) is a pinned terminal operation, always evaluated last and not movable, "
               "regenerated on the server and saved as an immutable version."),
        acceptance=("New design has 0 ops; closure is recorded as the pinned terminal op and evaluated "
                    "last, its position not editable; closure on open phantoms yields a watertight solid; "
                    "zero displacement above base plane; saved version immutable"),
        change="IDR-01: story, acceptance (closure = pinned terminal op, not the first op)"),
    "BL-030": dict(
        story=("As a technician or clinic admin, I want to draft and publish clinic configuration "
               "versions; a change to a controlled section follows FR-141 (new version with stored "
               "diff and audit event; designs approved under the earlier version need re-approval "
               "before export); an optional second-person approval of controlled changes can be "
               "switched on in configuration (off by default, DEC-020); nothing ships with production values."),
        acceptance=("Publish creates version n+1 + audit event; controlled change stores diff hash and "
                    "marks earlier approvals REAPPROVAL_REQUIRED; with the optional switch on, a "
                    "self-approved controlled change stays inactive; objects reference config version; "
                    "production DB refuses test_only config; NOT_SET keys produce CONFIG_NOT_SET"),
        change="DEC-020 / IDR-32: story, acceptance aligned with RTM FR-141 (second approver optional, off by default)"),
    "BL-115": dict(
        story=("As the product owner, I want uploads refused while real_patient_data_enabled is false, "
               "and the flag set to true only by a controlled configuration change (FR-141) that cites "
               "the approved privacy decision record and the VER-22 inspection record."),
        acceptance=("REAL_DATA_DISABLED returned while false; enabling without decision record ID and "
                    "VER-22 record ID refused; enabling logged"),
        change="DEC-020 / IDR-32: story, acceptance aligned with RTM SEC-17 (no mandatory second approver)"),
}


def build_backlog() -> None:
    fields, rows = read(D / "09a_MVP_BACKLOG_v0.3.csv")
    fields = [*fields, "v0.4_change"]
    for r in rows:
        r["v0.4_change"] = "unchanged"
        fix = BACKLOG_FIXES.get(r["id"])
        if fix:
            r["story"], r["acceptance"], r["v0.4_change"] = fix["story"], fix["acceptance"], fix["change"]
        if r["id"] == "BL-112":
            r["moscow"] = "Won't (retired)"
            r["release"] = "Retired"
            r["v0.4_change"] = ("IDR-32: retired - prescription attachment is MVP via FR-182 / FN-CAS-06 "
                                "(BL-112 'reference attachment, post-MVP' superseded)")
    write(D / "09a_MVP_BACKLOG_v0.4.csv", fields, rows)


NEW_ALGS = [
    dict(
        algorithm_id="ALG-62", name="Surface contour region", domain="Regions and zones",
        brief_topic="correction and relief regions", function_ids="FN-KOP-14; FN-KOP-16; FN-KOP-18",
        release="MVP", status="Proposed",
        mathematical_principle=(
            "Closed polyline of anchors (face_id, bary) on the positive; edges traced as plane-section "
            "paths between consecutive anchors; simplicity tested with exact predicates in a local "
            "projection; membership = vertices enclosed (winding number in the local chart) plus "
            "Euclidean distance to the contour for the transition band; resolved on the full-resolution mesh."),
        operation_sequence=("1 resolve anchors; 2 trace edges as plane-section paths; 3 test simplicity "
                            "(orient2d, exact); 4 winding membership; 5 distance-to-contour band for the transition"),
        inputs="Positive DS-01; anchors DS-07 (>= 3); transition width (mm, technician input)",
        outputs="Vertex membership mask + distance field for the transition band; or rejected with reason",
        computational_complexity="O(k · path length + n log n) with the shared BVH",
        numerical_limits="Exact predicates for simplicity; float64 distances; DEC-025 tolerances",
        known_errors_and_edge_cases="Self-intersecting or degenerate contours (rejected); contours crossing the base or closure faces; near-touching necks",
        libraries="Own (shared predicates XC-SHR-01, shared BVH)",
        alternatives="Geodesic polygon on the surface (heavier; not needed for helmet-scale zones)",
        test_unit="Membership on T15 contours equals exact polygon winding; self-intersection rejected",
        test_synthetic_geometry="T1 sphere with known contour; T15 contour set",
        test_edge_cases="Comb, spiral, near-touching necks (T15); contour through a vertex/edge (T14)",
        test_regression="Golden geometry_sha on T9 designs that use contour zones",
        test_numerical_stability="Metamorphic rigid transforms (T7) leave membership unchanged",
        test_geometric_invariants="Membership independent of control-point start index and orientation",
        test_performance="BM-01 series at subdivisions 4…8",
        sources=f"{CN} §2 (ALG-62)", open_items="—"),
    dict(
        algorithm_id="ALG-63", name="Parametric transition profile", domain="Regions and zones",
        brief_topic="correction and relief regions", function_ids="FN-KOP-15",
        release="MVP", status="Proposed",
        mathematical_principle=(
            "w(u) on u in [0, 1] across the transition; presets plateau (smoothstep) and peak (cosine); "
            "custom = monotone cubic Hermite (Fritsch–Carlson) through technician points; amplitude at "
            "vertex = m · w at the contour vertex; C1 for presets; no overshoot by construction."),
        operation_sequence="1 validate profile points (monotone, in [0,1]); 2 build Hermite slopes (Fritsch–Carlson); 3 evaluate w(u) per vertex; 4 displacement = m · w(u) along the vertex normal",
        inputs="Profile type or points; amplitude m (mm, technician input, no default); per-vertex u from ALG-62",
        outputs="Per-vertex weights w in [0, 1]",
        computational_complexity="O(n)",
        numerical_limits="float64; w clamped to [0, 1] only by construction (no post-hoc clamp)",
        known_errors_and_edge_cases="Non-monotone custom points (rejected); u exactly 0 or 1; flat segments",
        libraries="Own",
        alternatives="Fixed smoothstep only (IDR-20 before CN-2026-11-17)",
        test_unit="Presets equal analytic smoothstep/cosine; custom profile monotone",
        test_synthetic_geometry="T6 sign-convention sphere: +m -> +m at plateau",
        test_edge_cases="Two-point custom profile; repeated u values (rejected)",
        test_regression="Golden weights for each preset at fixed u samples",
        test_numerical_stability="No overshoot for T8 random monotone inputs",
        test_geometric_invariants="w(0) and w(1) at the profile ends; monotone in u",
        test_performance="Linear; covered by BM-01",
        sources=f"{CN} §2 (ALG-63); IDR-20 revised", open_items="—"),
]


def build_algorithms() -> None:
    fields, rows = read(D / "ALGORITHM_CATALOG_v1.0.csv")
    rows += [{k: a.get(k, "") for k in fields} for a in NEW_ALGS]
    write(D / "ALGORITHM_CATALOG_v1.1.csv", fields, rows)


WBS_LINKS = {"FN-CAS-02": "FR-194", "FN-KMS-06": "FR-195"}


def link_wbs() -> None:
    fields, rows = read(WBS)
    changed = 0
    for w in rows:
        fns = {f.strip() for f in w["function_id"].split(";")}
        for fn, rid in WBS_LINKS.items():
            if fn in fns and rid not in REQ_RE.findall(w["requirement_ids"]):
                w["requirement_ids"] = f"{w['requirement_ids']}; {rid}" if w["requirement_ids"] else rid
                changed += 1
    if changed:
        write(WBS, fields, rows)
    print(f"WBS links added: {changed}")


def main() -> None:
    link_wbs()
    req_fns, fn_reqs, req_unit = wbs_maps()
    for n in NEW_REQS:  # new functions are in the WBS already; make the mapping explicit anyway
        req_fns.setdefault(n["id"], set()).add(n["functions"])
    build_rtm(fn_reqs)
    build_catalogue(req_fns, req_unit)
    build_fixture_register()
    build_backlog()
    build_algorithms()


if __name__ == "__main__":
    main()
