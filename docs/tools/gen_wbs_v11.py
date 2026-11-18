#!/usr/bin/env python3
"""Generate WORK_BREAKDOWN_STRUCTURE_v1.1.csv and TASK_DEPENDENCY_MATRIX_v1.1.csv
from the approved v1.0 functional/technical baseline, then schedule and simulate.

Inputs (read-only copies in SRC): FUNCTION_CATALOG_v1.0.csv, FUNCTION_COMPONENT_MAPPING_v1.0.csv,
04a_REQUIREMENTS_TRACEABILITY_MATRIX_v0.3.csv, 09a_MVP_BACKLOG_v0.3.csv, FS.md (Functional Spec v1.0).
"""
import csv, json, re, random, math, statistics, sys
from collections import defaultdict, OrderedDict

SRC = sys.argv[1]
OUT = sys.argv[2]

def rd(name):
    return list(csv.DictReader(open(f"{SRC}/{name}", encoding="utf-8-sig")))

fc = rd("FUNCTION_CATALOG_v1.0.csv")
fmap = {r["function_id"]: r for r in rd("FUNCTION_COMPONENT_MAPPING_v1.0.csv")}
rtm = {r["id"]: r for r in rd("04a_REQUIREMENTS_TRACEABILITY_MATRIX_v0.3.csv")}
backlog = rd("09a_MVP_BACKLOG_v0.3.csv")
FN = {r["function_id"]: r for r in fc}
FUNCS = [r for r in fc if r["level"] == "Function"]
# ---- Change notice CN-2026-11-17 (Rodin4D observation, CH-01...CH-16): proposed functions and requirements
PROPOSED_REQS = {
    "FR-183": "Free-form zone boundary: closed contour of anchored control points on the surface (insert/delete/move, stretch); circle/ellipse kept as presets",
    "FR-184": "Parametric transition profile per zone (plateau, peak, custom curve), overall amplitude and amplitude at vertex",
    "FR-185": "Symmetric zone: linked mirrored copy across the mid-sagittal plane of the confirmed anatomical frame",
    "FR-186": "Live design metrics at a movable level (AP with anterior/posterior split, ML, circumference, positive volume; CI/CVA/CVAI where defined) with deltas in mm and % versus the prepared scan",
    "FR-187": "Original/modified overlay in the design workspace with opacity control and highlight of modified regions",
    "FR-188": "2D comparison views: transverse section contour and silhouette, original versus modified",
    "FR-189": "Elongation between two levels (application zone: total or two levels)",
    "FR-190": "Optional filtering (smoothing) inside a zone as a zone parameter",
    "FR-191": "Tape measure: straight and along-section distance between surface points",
    "FR-192": "Manual orientation fine-tuning (shift, tilt, twist) before frame confirmation, recorded as transform steps",
    "FR-193": "Standard view controls (view cube: anterior, posterior, left, right, superior, inferior)",
}
NEW_FUNCS = [
    # id, name, module, kind, priority, complexity, reqs, deps, purpose, AC, algs
    ("FN-KOP-14", "Free-form zone contour on surface", "KOP", "Kernel operation (pure function)", "Must", "L", "FR-183; FR-050", "FN-KOP-10; FN-KAN-01",
     "Define a zone by a closed contour of anchored control points on the positive instead of only circle/ellipse",
     "Contour with >= 3 anchored points defines the region; displacement inside follows the zone profile; vertices outside contour+transition bit-identical; self-intersecting contour rejected with ZONE_CONTOUR_INVALID; point insert/delete/move recorded in op params", "ALG-62; ALG-43; ALG-46; ALG-33"),
    ("FN-KOP-15", "Parametric transition profile", "KOP", "Kernel operation (pure function)", "Must", "M", "FR-184; FR-050", "FN-KOP-10",
     "Zone fall-off defined by a profile curve (plateau, peak or custom control points) with overall amplitude and amplitude at vertex",
     "Profile evaluated monotone and C1 for preset types; custom curve with >= 2 points interpolated without overshoot; displacement at plateau equals amplitude within e = 0.011 mm; profile stored in op params and hashed", "ALG-63; ALG-46"),
    ("FN-KOP-16", "Symmetric (mirrored) zone", "KOP", "Kernel operation (pure function)", "Must", "M", "FR-185; FR-050; SAF-03", "FN-KOP-10; FN-KOP-14; FN-KFR-02",
     "Create a linked mirror of a zone across the mid-sagittal plane of the confirmed frame",
     "Mirror zone centre/contour equals reflection of source within e; parameters linked (edit source updates mirror); laterality labels swap; refused without confirmed frame (FRAME_NOT_CONFIRMED); mirror never applied to stored geometry as a reflection transform", "ALG-31; ALG-32; ALG-46"),
    ("FN-KOP-17", "Elongation between two levels", "KOP", "Kernel operation (pure function)", "Should", "S", "FR-189; FR-051", "FN-KOP-08",
     "Elongate the positive only between two configured heights", "Extent between levels changes by delta within 2e; geometry outside the band translated rigidly; delta = 0 is identity", "ALG-48"),
    ("FN-KOP-18", "In-zone filtering", "KOP", "Kernel operation (pure function)", "Should", "S", "FR-190; FR-179", "FN-KOP-10; FN-KOP-12",
     "Optional smoothing restricted to a zone and its transition", "Vertices outside zone+transition bit-identical; filter level from {none, light, medium} recorded; guard passes", "ALG-18"),
    ("FN-DES-08", "Live design metrics panel", "DES", "User interaction", "Must", "M", "FR-186; FR-041; FR-045", "FN-DES-03; FN-KMS-01; FN-KMS-03; FN-KMS-05; FN-KVL-06",
     "Show AP (anterior/posterior), ML, circumference and volume at a movable level, with deltas versus the prepared scan, after every regeneration",
     "Values match kernel measurement functions on VER-01 phantoms within DEC-025; deltas computed against the prepared scan at the same level; no thresholds or colour meaning beyond increase/decrease; definitions shown", "ALG-23; ALG-36; ALG-38; ALG-12"),
    ("FN-UIX-07", "Original/modified overlay in workspace", "UIX", "User interaction", "Must", "M", "FR-187; FR-070", "FN-DES-06; FN-KCP-01; FN-UIX-02; FN-UIX-04",
     "Overlay the prepared scan on the current positive with opacity control and highlight of modified regions during design",
     "Highlight equals vertices with |deviation| > 0 from the latest regeneration; opacity slider 0-100 %; display-only (no stored geometry from the client)", "ALG-40; ALG-57"),
    ("FN-UIX-08", "2D section comparison views", "UIX", "User interaction", "Should", "M", "FR-188", "FN-KMS-01; FN-UIX-02; FN-DES-03",
     "Show transverse contour and silhouette of original versus modified at the selected level", "Contours equal kernel sections (ALG-23) at the same level; axes in mm; updates after regeneration", "ALG-23"),
    ("FN-UIX-09", "Standard view controls (view cube)", "UIX", "UI only", "Should", "S", "FR-193; NFR-02", "FN-UIX-02",
     "Six standard views and reset in the 3D viewer", "Each view button sets the camera to the frame axis direction; works on display LOD", ""),
    ("FN-MEA-05", "Tape measure", "MEA", "User interaction", "Should", "S", "FR-191", "FN-KAN-01; FN-UIX-02",
     "Measure straight and along-section distances between snapped surface points", "Straight distance exact on snapped anchors; along-section length equals contour arc within 0.032 mm on phantoms; values labelled as ad-hoc (not a measurement definition)", "ALG-33; ALG-23"),
    ("FN-ANA-06", "Manual orientation fine-tuning", "ANA", "User interaction", "Should", "M", "FR-192; FR-032; SAF-03", "FN-ANA-03; FN-KFR-03",
     "Adjust the computed frame by small shift/tilt/twist before confirmation; each adjustment recorded", "Adjustments are rigid (det +1); stored as transform steps in the frame record; reset returns to landmark frame; reflection refused", "ALG-32"),
    ("FN-PMV-13", "Reference image underlay", "PMV", "User interaction", "Could", "M", "", "FN-UIX-02",
     "Show a calibrated reference photo behind the model (Rodin4D shows X-ray underlay for TLSO)", "Outline only", ""),
]
for (fid, name, mod, kind, prio, cxs, reqs, deps, purp, ac, algs) in NEW_FUNCS:
    r = {k: "" for k in fc[0].keys()}
    r.update(function_id=fid, level="Function", name=name, module_code=mod, module=next(x["module"] for x in fc if x["module_code"] == mod),
             kind=kind, priority=prio, release="MVP" if fid != "FN-PMV-13" else "post-MVP", implementation_complexity=cxs,
             requirement_ids=reqs, depends_on=deps, purpose=purp, spec_status="Ready (CN-2026-11-17)", open_questions="")
    fc.append(r)
    fmap[fid] = {"algorithms": algs, "technical_decisions": "", "interfaces": "IF-01; IF-02; IF-03" if mod != "PMV" else "", "open_items": ""}
NEW_AC = {f[0]: f[9] for f in NEW_FUNCS}
for q, t in PROPOSED_REQS.items():
    rtm[q] = {"id": q, "title": t, "release": "MVP", "priority": "Proposed (RTM v0.4, CN-2026-11-17)"}
FN = {r["function_id"]: r for r in fc}
FUNCS = [r for r in fc if r["level"] == "Function"]
SUBS = defaultdict(list)
for r in fc:
    if r["level"] == "Subfunction":
        SUBS[r["parent_function_id"]].append(r)

# ---- Functional Spec acceptance criteria and test IDs per function
fs = open(f"{SRC}/FS.md", encoding="utf-8").read()
parts = re.split(r"\n#{5} (FN-[A-Z]{3}-\d{2}(?:\.\d)?) — ", fs)
FS_AC, FS_TC = {}, {}
for i in range(1, len(parts), 2):
    fid, body = parts[i], parts[i + 1]
    m = re.search(r"\| Acceptance Criteria \| (.*?) \|\n", body)
    t = re.search(r"\| Test Case IDs \| (.*?) \|\n", body)
    FS_AC[fid] = re.sub(r"<br>", " ", m.group(1)).replace("•", "").strip() if m else ""
    FS_TC[fid] = t.group(1).strip() if t else ""

def split_ids(s):
    return [x.strip() for x in re.split(r"[;,]", s or "") if x.strip() and x.strip() not in ("—", "-")]

# ---- Implementation decision record mapping (open question -> IDR)
OQ2IDR = {
    "OQ-FS-01": "IDR-01", "OQ-FS-02": "IDR-02", "OQ-FS-03": "IDR-03", "TQ-18": "IDR-03",
    "OQ-FS-04": "IDR-04", "OQ-FS-06": "IDR-05", "OQ-FS-07": "IDR-06", "OQ-FS-08": "IDR-07",
    "TQ-02": "IDR-07", "TQ-03": "IDR-07", "TQ-20": "IDR-07", "TQ-04": "IDR-08", "TQ-09": "IDR-09",
    "TQ-05": "IDR-10", "TQ-11": "IDR-10", "TQ-06": "IDR-11", "TQ-07": "IDR-12", "TQ-08": "IDR-13",
    "TQ-10": "IDR-14", "OQ-FS-24": "IDR-14", "TQ-25": "IDR-15", "TQ-21": "IDR-16", "TQ-23": "IDR-16",
    "TQ-17": "IDR-17", "TQ-26": "IDR-18", "TQ-19": "IDR-18", "TQ-15": "IDR-19", "TQ-16": "IDR-19",
    "OQ-FS-09": "IDR-20", "OQ-FS-10": "IDR-20", "OQ-FS-11": "IDR-20", "OQ-FS-19": "IDR-20",
    "OQ-FS-20": "IDR-20", "OQ-FS-12": "IDR-21", "OQ-FS-13": "IDR-22", "OQ-FS-14": "IDR-23",
    "OQ-FS-15": "IDR-24", "OQ-FS-21": "IDR-24", "OQ-FS-22": "IDR-24", "OQ-FS-16": "IDR-25",
    "OQ-FS-17": "IDR-25", "OQ-FS-28": "IDR-25", "TQ-12": "IDR-25", "OQ-FS-18": "IDR-26",
    "OQ-FS-23": "IDR-27", "OQ-FS-25": "IDR-28", "OQ-FS-27": "IDR-28", "OQ-FS-26": "IDR-29",
    "OQ-FS-37": "IDR-30", "OQ-FS-38": "IDR-31", "OQ-FS-33": "IDR-32", "OQ-FS-35": "IDR-32",
    "OQ-FS-36": "IDR-32", "OQ-FS-05": "IDR-32", "OQ-FS-30": "IDR-33", "TQ-01": "IDR-33",
    "OQ-FS-29": "EXT-03", "TQ-13": "EXT-03", "TQ-14": "EXT-02", "OQ-FS-31": "EXT-05",
    "OQ-FS-32": "EXT-06", "TQ-24": "EXT-07", "TQ-22": "X-02",
}

# ---- Scope classification
PROMOTED = {  # Should -> MVP-Core, with reason
    "FN-AUD-03": "SEC-03 tamper evidence is only meaningful if verified; restore drill re-verifies the chain (TC-SEC-08)",
    "FN-AUD-04": "Dependency of FN-AUD-05 -> FN-OPS-09 (Must, STK-07 pilot analytics)",
    "FN-AUD-05": "Dependency of FN-OPS-09 (Must, STK-07 / VER-10 / VER-23)",
    "FN-BLB-03": "Restore drill (SEC-08, FN-OPS-05 Must) re-verifies blob SHAs",
    "FN-OPS-03": "SD-04: CVSS >= 7.0 blocks a release - the gate needs the scan",
    "FN-OPS-07": "IDR-10: own kernel algorithms are accepted only against independent oracles",
    "FN-DES-05": "SAF-07 out-of-range confirmation is a safety control on technician input",
}
CUT_ORDER = [  # MVP-Should, ordered by value (1 = keep longest; last = cut first)
    "FN-UIX-09", "FN-KOP-17", "FN-SCN-08", "FN-KOP-07", "FN-KOP-12", "FN-UIX-08", "FN-KCP-03", "FN-MEA-05", "FN-KAN-03", "FN-KOP-18", "FN-ANA-06", "FN-SCN-09", "FN-REV-05", "FN-UIX-06",
    "FN-RPT-02", "FN-RPT-01", "FN-RPT-03", "FN-KOP-02", "FN-KMS-06", "FN-KOP-03",
    "FN-CAS-05", "FN-SCN-10", "FN-IAM-06", "FN-CFG-03", "FN-DES-07",
]
NEXT = {"FN-PMV-13", "FN-PMV-01", "FN-PMV-02", "FN-PMV-03", "FN-PMV-04", "FN-PMV-05", "FN-PMV-08", "FN-PMV-09", "FN-PMV-11"}
DEFERRED = {"FN-PMV-06", "FN-PMV-07", "FN-PMV-10", "FN-PMV-12", "FN-CAS-09"}

def scope_of(fid):
    r = FN[fid]
    if fid in DEFERRED: return "Deferred"
    if fid in NEXT: return "Next (v1.1)"
    if r["priority"] == "Must" or fid in PROMOTED: return "MVP-Core"
    if r["priority"] == "Should": return "MVP-Should"
    return "Next (v1.1)"

PRIO = {"MVP-Core": "P1", "MVP-Should": "P2", "Next (v1.1)": "P3", "Deferred": "P4"}

# ---- Milestones per function
MS = {}
def setm(m, ids):
    for x in ids.split():
        MS["FN-" + x] = m
setm("M0", "API-01 API-02 AUD-01 AUD-06 JOB-01 JOB-02 JOB-03 JOB-04 BLB-01 IAM-01 IAM-02 IAM-03 IAM-04 "
           "KIO-01 KIO-06 KFR-03 KRP-02 KRP-03 KRP-04 REV-06 OPS-01 OPS-02 OPS-03 OPS-06")
setm("M1", "KIO-02 KIO-05 KIO-07 KVL-01 KVL-02 KVL-03 KVL-04 KVL-05 KVL-06 KVL-07 KFR-01 "
           "KMS-01 KOP-04 KOP-06 KRP-01 KEX-01 KEX-02 AUD-02 BLB-02 UIX-02 UIX-03 OPS-04 OPS-07")
setm("M2", "KIO-03 KIO-04 KAN-01 KAN-02 KCP-04 KOP-01 KOP-05 KOP-13 ANA-05 IAM-05 IAM-06 AUD-03 AUD-04 AUD-05 CFG-01 CFG-02 CFG-03 CFG-04 CFG-07 CFG-08 BLB-03 BLB-04 "
           "CAS-01 CAS-02 CAS-03 CAS-04 CAS-05 CAS-06 CAS-07 CAS-08 SCN-01 SCN-02 SCN-03 SCN-04 SCN-05 "
           "SCN-06 SCN-07 SCN-08 SCN-09 SCN-10 SCN-11 SCN-12 KOP-02 KOP-03 UIX-01 UIX-05 UIX-06 OPS-05 OPS-10")
setm("M3", "CFG-05 CFG-06 KFR-02 KAN-03 KMS-02 KMS-03 KMS-04 KMS-05 KMS-06 ANA-01 ANA-02 ANA-03 ANA-04 "
           "MEA-01 MEA-02 MEA-03 MEA-04 MEA-05 ANA-06")
setm("M4a", "KOP-07 KOP-08 KOP-09 KOP-10 KOP-11 KOP-12 KOP-14 KOP-15 KOP-16 KOP-17 KOP-18 DES-01 DES-02 DES-03 DES-04 DES-05")
setm("M4b", "DES-06 DES-07 DES-08 KCP-01 KCP-02 UIX-04 UIX-07 UIX-08 UIX-09")
setm("M5", "KCP-03 KFR-04 REV-01 REV-02 REV-03 REV-04 REV-05 EXP-01 EXP-02 EXP-03")
setm("M6", "RPT-01 RPT-02 RPT-03 OPS-08 OPS-09 OPS-12")
setm("M7", "OPS-11")
MS_LIST = ["M0", "M1", "M2", "M3", "M4a", "M4b", "M5", "M6", "M7"]
MORD = {m: i for i, m in enumerate(MS_LIST)}

EPIC_OF_MOD = {
    "IAM": "EP-02", "API": "EP-02", "AUD": "EP-02", "JOB": "EP-02", "BLB": "EP-02",
    "CFG": "EP-03", "CAS": "EP-04",
    "KIO": "EP-05", "KVL": "EP-05", "KFR": "EP-05", "KRP": "EP-05", "KEX": "EP-05", "XSHR": "EP-05",
    "KAN": "EP-06", "KMS": "EP-06", "KOP": "EP-06", "KCP": "EP-06",
    "SCN": "EP-07", "ANA": "EP-08", "MEA": "EP-08", "DES": "EP-09", "REV": "EP-10", "EXP": "EP-10",
    "UIX": "EP-11", "RPT": "EP-11", "OPS": "EP-12", "XFND": "EP-01", "XEXP": "EP-13", "XPLT": "EP-14",
    "XSTB": "EP-12", "PMV": "EP-15",
}
EPICS = OrderedDict([
    ("EP-01", "Engineering foundation, decisions and environments"),
    ("EP-02", "Platform services (identity, API conventions, audit, jobs, blob store)"),
    ("EP-03", "Clinic configuration"),
    ("EP-04", "Case and data governance"),
    ("EP-05", "Geometry kernel - I/O, validation, frames, replay, export, shared primitives"),
    ("EP-06", "Geometry kernel - anchors, measurement, design operations, comparison"),
    ("EP-07", "Scan intake and quality"),
    ("EP-08", "Anatomy and measurement"),
    ("EP-09", "Design workspace and regeneration"),
    ("EP-10", "Review, approval and export"),
    ("EP-11", "UI shell, 3D viewer and reporting"),
    ("EP-12", "Quality engineering, security and operations"),
    ("EP-13", "Technology experiments and benchmarks"),
    ("EP-14", "Pilot readiness and external verification"),
    ("EP-15", "Next version (post-MVP) and deferred items - not scheduled"),
])
MODNAME = {r["module_code"]: r["module"] for r in fc}
MODNAME.update({"XFND": "Foundation (repository, CI, data platform, deployment, decisions)",
                "XSHR": "Kernel shared primitives (exact predicates, BVH, fixtures)",
                "XEXP": "Experiments X-01...X-08 and benchmarks BM-01...BM-07",
                "XPLT": "Pilot readiness (inspection, clinic inputs, physical verification, deployment)",
                "XSTB": "Milestone stabilisation and defect fixing"})

PKG = {"KIO": "k01_io", "KVL": "k02_validate", "KFR": "k03_frames", "KAN": "k04_anchors",
       "KMS": "k05_measure", "KOP": "k06_ops", "KCP": "k07_compare", "KRP": "k08_replay", "KEX": "k09_export"}
FIXT = {"KIO": "T3, T4", "KVL": "T3, T13", "KFR": "T5, T7", "KAN": "T1, T14", "KMS": "T1, T15",
        "KOP": "T1, T2, T6, T8", "KCP": "T1, T6", "KRP": "T9", "KEX": "T5, T10"}

# ---- Effort model (ideal person-days: optimistic, most likely, pessimistic)
E = {
    "K": {"S": (0.5, 1, 2), "M": (2, 4, 7), "L": (5, 8, 13)},
    "V": {"S": (0.5, 0.5, 1), "M": (1, 2, 4), "L": (2, 4, 6)},
    "B": {"S": (0.5, 1, 2), "M": (2, 3, 5), "L": (3, 6, 9)},
    "U": {"S": (0.5, 1, 2), "M": (2, 3, 5), "L": (4, 6, 10)},
    "J": {"S": (0.5, 1, 2), "M": (1.5, 2.5, 4), "L": (3, 5, 8)},
    "A": {"S": (0.5, 1, 2), "M": (1.5, 2.5, 4), "L": (3, 5, 8)},
    "O": {"S": (0.5, 1, 2), "M": (1.5, 3, 5), "L": (3, 5, 8)},
    "C": {"S": (0.5, 1, 1.5), "M": (1.5, 2.5, 4), "L": (3, 4, 7)},
}
OVR = {  # (function, task type) -> effort override
    ("FN-KOP-14", "K"): (6, 10, 16), ("FN-KOP-14", "V"): (2, 4, 6), ("FN-KOP-14", "U"): (4, 6, 10),
    ("FN-KOP-15", "K"): (2, 3, 5), ("FN-KOP-15", "V"): (1, 1.5, 3), ("FN-KOP-15", "U"): (2, 4, 6),
    ("FN-KOP-16", "K"): (2, 4, 6), ("FN-KOP-16", "V"): (1, 1.5, 3), ("FN-KOP-16", "U"): (1, 2, 3),
    ("FN-KOP-17", "K"): (1, 2, 3), ("FN-KOP-17", "V"): (0.5, 1, 2), ("FN-KOP-18", "K"): (1, 2, 3), ("FN-KOP-18", "V"): (0.5, 1, 2),
    ("FN-DES-08", "B"): (3, 5, 8), ("FN-DES-08", "U"): (3, 5, 8), ("FN-UIX-07", "B"): (0.5, 1, 2), ("FN-UIX-07", "U"): (2, 3, 5),
    ("FN-UIX-08", "B"): (1, 1.5, 3), ("FN-UIX-08", "U"): (3, 5, 8), ("FN-UIX-09", "U"): (0.5, 1, 2),
    ("FN-MEA-05", "B"): (1, 2, 4), ("FN-MEA-05", "U"): (1, 1.5, 3), ("FN-ANA-06", "B"): (1.5, 2.5, 4), ("FN-ANA-06", "U"): (1, 1.5, 3),
    ("FN-KVL-05", "K"): (8, 12, 20), ("FN-KVL-05", "V"): (3, 5, 8),
    ("FN-KRP-01", "K"): (6, 9, 15), ("FN-KOP-06", "K"): (6, 9, 15), ("FN-KOP-06", "V"): (3, 5, 8),
    ("FN-KOP-10", "K"): (5, 8, 13), ("FN-KOP-02", "K"): (6, 10, 16), ("FN-UIX-02", "U"): (6, 10, 16),
    ("FN-DES-02", "B"): (4, 6, 10), ("FN-DES-02", "U"): (6, 9, 15), ("FN-UIX-05", "U"): (4, 6, 10),
    ("FN-ANA-02", "U"): (3, 5, 8), ("FN-CFG-01", "U"): (5, 8, 12), ("FN-CFG-01", "B"): (3, 5, 8),
    ("FN-AUD-01", "A"): (3, 4, 7), ("FN-OPS-08", "C"): (5, 8, 12), ("FN-OPS-12", "C"): (4, 6, 10),
    ("FN-OPS-05", "O"): (3, 5, 8), ("FN-CAS-08", "O"): (4, 6, 10), ("FN-OPS-06", "C"): (3, 5, 8),
    ("FN-OPS-07", "C"): (3, 5, 8), ("FN-REV-04", "B"): (4, 6, 10), ("FN-REV-04", "U"): (2, 4, 6),
    ("FN-MEA-01", "B"): (3, 5, 8), ("FN-MEA-01", "U"): (2, 3, 5), ("FN-EXP-02", "J"): (3, 5, 8),
    ("FN-DES-03", "J"): (3, 5, 8), ("FN-SCN-05", "U"): (2, 3, 5), ("FN-SCN-11", "U"): (3, 5, 8),
    ("FN-KAN-01", "K"): (2, 3, 5), ("FN-UIX-02", "B"): (0.5, 1, 2), ("FN-UIX-05", "B"): (1.5, 2.5, 4),
    ("FN-UIX-01", "B"): (0.5, 1, 2), ("FN-UIX-03", "B"): (0.5, 1, 1.5), ("FN-UIX-04", "B"): (0.5, 1, 1.5), ("FN-UIX-06", "B"): (0.5, 0.5, 1), ("FN-KCP-01", "K"): (3, 5, 8), ("FN-KMS-04", "K"): (3, 5, 8),
}
NO_UI = {"FN-SCN-07"}
DROP_EDGES = {
    ("FN-KOP-04", "FN-KOP-03"): "IDR-12: display LOD uses the library decimator chosen by X-01; recorded op cleanup.decimate (Should) is independent",
    ("FN-SCN-11", "FN-KOP-02"): "Should op integrates through the op registry (FN-KRP-04) when merged; SCN-11 ships with registered ops only",
    ("FN-SCN-11", "FN-KOP-03"): "as above",
    ("FN-MEA-01", "FN-KMS-06"): "synthetic-contact flag added to the measurement set when FN-KMS-06 merges (only relevant once hole filling exists)",
    ("FN-REV-02", "FN-KCP-03"): "point query is an optional panel of the deviation view",
    ("FN-ANA-04", "FN-KAN-03"): "coverage step shown when FN-KAN-03 merges; frame confirmation does not wait for it",
    ("FN-KIO-05", "FN-KIO-03"): "indexed-mesh builder consumes any parser output; OBJ/PLY parsers (M2) feed it later",
    ("FN-KIO-05", "FN-KIO-04"): "as above",
    ("FN-OPS-07", "FN-KCP-04"): "oracle comparisons for KCP-04 are added when KCP-04 exists (M2); the CGAL/trimesh oracle container is needed in M1 for X-02",
}
EXTRA_UI = {"FN-SCN-05": "Integrity report panel (W02)", "FN-KOP-14": "Contour editor (points, push contour/edge, stretch)",
            "FN-KOP-15": "Transition profile editor", "FN-KOP-16": "Symmetric zone controls"}
KERNEL_UI = {"FN-KOP-14", "FN-KOP-15", "FN-KOP-16"}

POOL = {"K": "KERNEL", "V": "QA_OPS", "B": "BACKEND", "A": "BACKEND", "J": "BACKEND", "U": "FRONTEND",
        "O": "QA_OPS", "C": "QA_OPS"}
OPS_POOL = {"FN-OPS-06": "KERNEL", "FN-OPS-09": "BACKEND", "FN-OPS-10": "BACKEND", "FN-OPS-11": "BACKEND",
            "FN-CAS-08": "BACKEND", "FN-BLB-04": "BACKEND", "FN-IAM-06": "BACKEND", "FN-AUD-06": "BACKEND",
            "FN-OPS-04": "KERNEL"}
SKILLS = {
    "QA_GEO": "pytest/hypothesis, geometry fixtures, numerical tolerances, oracle tools (CGAL/trimesh in CI container)",
    "KERNEL": "Python 3.12, numpy/scipy, computational geometry, floating-point robustness",
    "BACKEND": "Python, FastAPI, PostgreSQL/SQLAlchemy/Alembic, transactional design, AppSec basics",
    "FRONTEND": "TypeScript, React/Next.js, accessibility, Russian UI copy",
    "QA_OPS": "pytest/hypothesis/Playwright, GitHub Actions, Docker, Linux hardening",
    "EXT": "Domain role (engineering lead / privacy specialist / clinic technician / product owner)",
}
ROLE = {"KERNEL": "Kernel engineer", "BACKEND": "Backend engineer", "FRONTEND": "Frontend engineer",
        "QA_OPS": "QA / DevOps engineer", "EXT": "See name"}
EXTRA_SKILL = {
    "FN-KVL-05": "exact predicates (Shewchuk), BVH, numba", "FN-KOP-06": "polygon triangulation, exact orient2d",
    "FN-KOP-02": "minimum-weight triangulation, sparse linear algebra", "FN-UIX-02": "three.js, WebGL, Web Workers, three-mesh-bvh",
    "FN-UIX-05": "three.js picking, BVH raycast", "FN-KAN-01": "BVH closest point, tie rules", "FN-KCP-01": "signed distance, pseudonormals",
    "FN-AUD-01": "hash chains, RFC 8785 JCS, Postgres locking", "FN-KRP-01": "content-addressed caching, determinism",
    "FN-RPT-01": "WeasyPrint, HTML/CSS print layout", "FN-RPT-02": "software rasterisation", "FN-OPS-12": "threat modelling, OWASP ASVS",
    "FN-OPS-05": "Supabase, S3-compatible storage, restic", "FN-OPS-08": "Playwright, cross-browser testing",
    "FN-CAS-08": "privacy engineering, erasure procedures", "FN-OPS-10": "privacy inspection (VER-22) evidence",
}

def cx(ml):
    return "S" if ml <= 2 else "M" if ml <= 5 else "L" if ml <= 10 else "XL"

def pert(o, m, p):
    return round((o + 4 * m + p) / 6, 2)

def bl_refs(reqs):
    rs = set(reqs)
    scored = []
    for b in backlog:
        br = set(split_ids(b["requirements"].replace("…", "")))
        ov = len(rs & br)
        if ov and b["release"] == "MVP":
            scored.append((-ov, b["id"]))
    return [x[1] for x in sorted(scored)[:3]]

tasks = OrderedDict()   # id -> dict
def add_task(t):
    assert t["id"] not in tasks, t["id"]
    tasks[t["id"]] = t

def idr_of(fid):
    ids = split_ids(FN[fid]["open_questions"]) + split_ids(fmap.get(fid, {}).get("open_items", ""))
    out = []
    for q in ids:
        v = OQ2IDR.get(q)
        if v and v not in out: out.append(v)
    return out

def status_of(fid, idrs):
    s = FN[fid]["spec_status"]
    ext = [x for x in idrs if x.startswith("EXT")]
    if s.startswith("Blocked"):
        st = "Ready after IDR ratification (XC-FND-01); was blocked by " + FN[fid]["open_questions"].replace("; ", ", ")
    elif s.startswith("Ready with open items"):
        st = "Ready (open items closed by " + ", ".join([x for x in idrs if x.startswith("IDR")] or ["non-blocking defaults"]) + ")"
    else:
        st = "Ready"
    if ext:
        st += "; final values gated by " + ", ".join(ext)
    return st

# ---------------- Function-derived tasks
TT_NAME = {"K": "Implement kernel operation", "V": "Geometric verification (fixtures, invariants, oracle, golden)",
           "B": "Implement domain service + API endpoint", "U": "Implement UI", "J": "Implement background job",
           "A": "Implement synchronous service", "O": "Implement procedure tooling + runbook", "C": "Implement CI/test tooling"}

def task_types(r):
    k = r["kind"]
    fid = r["function_id"]
    if k.startswith("Kernel"): return ["K", "V"] + (["U"] if fid in KERNEL_UI else [])
    if k == "UI only": return ["U"]
    if k == "User interaction": return ["B"] + ([] if fid in NO_UI else ["U"])
    if k == "Background job": return ["J"] + (["U"] if fid in EXTRA_UI else [])
    if k.startswith("API service"): return ["A"]
    if k.startswith("Operational"): return ["O"]
    if k.startswith("Build"): return ["C"]
    return ["X"]  # outline

primary = {}  # fid -> primary task id
uitask = {}
for r in FUNCS:
    fid = r["function_id"]; mod = r["module_code"]
    sc = scope_of(fid)
    reqs = split_ids(r["requirement_ids"])
    mp = fmap.get(fid, {})
    algs = split_ids(mp.get("algorithms", ""))
    tds = split_ids(mp.get("technical_decisions", ""))
    ifs = split_ids(mp.get("interfaces", ""))
    idrs = idr_of(fid)
    num = fid.split("-")[-1]
    if sc in ("Next (v1.1)", "Deferred"):
        tid = f"TSK-{mod}-{num}-X" if mod != "PMV" else f"TSK-PMV-{num}-X"
        if fid == "FN-CAS-09": tid = "TSK-CAS-09-X"
        eff = (8, 15, 25) if sc.startswith("Next") else (0, 0, 0)
        add_task(dict(id=tid, ttype="X", fid=fid, mod=mod, name=f"{r['name']} - outline only, plan in {sc}",
                      description=f"Not implemented in MVP. Scope decision IDR-32/IDR-35. {r['purpose']}",
                      reqs=reqs or ["(no approved requirement - " + ("GAP-M15" if fid == "FN-PMV-11" else "GAP-M05/M06") + ")"],
                      refs=algs + tds, scope=sc, prio=PRIO[sc], ms="post-MVP", pool="KERNEL",
                      eff=eff, deps=[], deliverables="Requirement + design update when scheduled",
                      result="Item stays out of MVP build; traceability retained",
                      completion="Re-planned in the v1.1 planning cycle with approved requirements",
                      tests="To be designed when scoped", levels="—", dod="Not applicable (not scheduled)",
                      gate="IDR-32; IDR-35", status="Not scheduled (" + sc + ")", owner="Product owner",
                      subtasks=[], skills="—"))
        primary[fid] = tid
        continue
    for tt in task_types(r):
        tid = f"TSK-{mod}-{num}-{tt}"
        pool = OPS_POOL.get(fid, POOL[tt]) if tt in ("O", "C", "A") else POOL[tt]
        size = r["implementation_complexity"] or "S"
        eff = OVR.get((fid, tt), E[tt][size])
        if tt == "K":
            desc = (f"Implement {fid} '{r['name']}' as a pure function in jude_kernel.{PKG[mod]} "
                    f"(no I/O/clock/randomness; float64; OpResult contract IF-03)"
                    + (f" following {', '.join(algs)}" if algs else "") + (f"; decisions {', '.join(tds)}" if tds else "")
                    + ". Unit + property tests in the same change.")
            deliv = f"packages/kernel/src/jude_kernel/{PKG[mod]}/ module + registry entry (if op) + tests/unit"
            tests = f"UT-{fid}; PT-{fid} (hypothesis, seeded); " + FS_TC.get(fid, "")
            levels = "UT, PT"; dod = "DoD-STD + DoD-K"
        elif tt == "V":
            desc = (f"Verify {fid} on fixtures {FIXT[mod]} against analytic truth and DEC-025 tolerances; "
                    f"invariants and edge cases from GEOMETRY_TESTING_STRATEGY §6"
                    + (f" for {', '.join(algs)}" if algs else "") + "; golden hashes; oracle comparison where defined.")
            deliv = f"tests/geometry/{PKG[mod]}/ suites + golden files + oracle comparison report (CI artefact)"
            tests = f"GT-{fid} ({FIXT[mod]}); RT-{fid} (golden); " + "; ".join(f"ORC-{a}" for a in algs[:3])
            levels = "GT, RT, ORC"; dod = "DoD-STD + DoD-V"
        elif tt == "B":
            desc = (f"Domain service, persistence (migration if needed), /api/v1 endpoint(s), permission-table rows, "
                    f"audit events and DS-24 error codes for {fid} '{r['name']}'.")
            deliv = f"services/api/src/jude_api/domain/{mod.lower()}/ + routers + migration + permissions.yaml rows + tests"
            tests = f"UT-{fid}; IT-{fid} (API+Postgres+storage fake); VER-12 rows; VER-13 events; " + FS_TC.get(fid, "")
            levels = "UT, IT"; dod = "DoD-STD + DoD-B"
        elif tt == "U":
            nm = EXTRA_UI.get(fid, r["name"])
            desc = (f"Russian-language UI for {fid} '{nm}' using the generated OpenAPI client; gate lists via FN-UIX-03; "
                    f"no client-side geometry decisions; wording lint clean.")
            deliv = f"apps/web/src/features/{mod.lower()}/ components + route + i18n strings (ru) + component tests"
            tests = f"CT-{fid} (vitest/RTL); E2E step in FN-OPS-08 scenario; VER-09 lint"
            levels = "CT, E2E"; dod = "DoD-STD + DoD-U"
        elif tt == "J":
            desc = (f"Worker job handler for {fid} '{r['name']}' (job/1 payload, idempotency rule, kernel calls via IF-03, "
                    f"completion handler commits result + domain change + audit atomically; EH-JOB).")
            deliv = f"services/worker/src/jude_worker/jobs/{mod.lower()}_{num}.py + completion handler + tests"
            tests = f"UT-{fid}; IT-{fid} (job runner + Postgres + storage fake; failure/retry paths); " + FS_TC.get(fid, "")
            levels = "UT, IT"; dod = "DoD-STD + DoD-J"
        elif tt == "A":
            desc = f"Synchronous service {fid} '{r['name']}' (dependency/middleware or service function) with error mapping EH-API."
            deliv = f"services/api/src/jude_api/{'platform' if mod in ('IAM','API','AUD','JOB','BLB') else 'domain/'+mod.lower()}/ + tests"
            tests = f"UT-{fid}; IT-{fid}; " + FS_TC.get(fid, "")
            levels = "UT, IT"; dod = "DoD-STD + DoD-A"
        elif tt == "O":
            desc = f"Software support + runbook for procedure {fid} '{r['name']}'; every step leaves an audit/record entry (EH-PROC)."
            deliv = f"scripts/ops/ tooling + docs/runbooks/{fid}.md + record template"
            tests = f"OT-{fid} (dry run on staging, record produced); IT-{fid}; " + FS_TC.get(fid, "")
            levels = "OT, IT"; dod = "DoD-STD + DoD-O"
        else:  # C
            desc = f"CI/test tooling {fid} '{r['name']}' wired into the pipeline stage defined in GEOMETRY_TESTING_STRATEGY §7 (EH-CI)."
            deliv = f".github/workflows + tools/ or tests/ harness for {fid}"
            tests = f"CI-{fid} (seeded violation makes the stage fail; clean tree passes); " + FS_TC.get(fid, "")
            levels = "CI"; dod = "DoD-STD + DoD-C"
        sk = SKILLS["QA_GEO" if tt == "V" else pool] + ("; " + EXTRA_SKILL[fid] if fid in EXTRA_SKILL and tt != "V" else "")
        if tt == "U" and fid in EXTRA_SKILL: sk = SKILLS["FRONTEND"] + "; " + EXTRA_SKILL[fid]
        subs = []
        if tt in ("K", "B", "J", "A", "O", "C") and tt == task_types(r)[0]:
            subs = [(s["function_id"], s["name"], s["purpose"]) for s in SUBS.get(fid, [])]
        add_task(dict(id=tid, ttype=tt, fid=fid, mod=mod, name=f"{TT_NAME[tt]}: {EXTRA_UI.get(fid, r['name']) if tt=='U' else r['name']}",
                      description=desc, reqs=reqs, refs=algs + tds + ifs + bl_refs(reqs), scope=sc, prio=PRIO[sc],
                      ms=MS[fid], pool=pool, eff=eff, deps=[], deliverables=deliv,
                      result=r["purpose"], completion=FS_AC.get(fid, "") or NEW_AC.get(fid, ""), tests=tests.strip("; "), levels=levels,
                      dod=dod, gate="; ".join(idrs), status=status_of(fid, idrs),
                      owner=("QA engineer (geometry) - not the author of the K task" if tt == "V" else ROLE[pool]), subtasks=subs, skills=sk))
        if tt == task_types(r)[0]: primary[fid] = tid
        if tt == "U": uitask[fid] = tid

add_task(dict(id="TSK-KOP-12-KG", ttype="KG", fid="FN-KOP-12", mod="KOP", name="Global smoothing mode (Complete Smoothing) [kernel]",
              description="Add region = whole scan-origin surface to smooth.windowed_sinc (CH-12; IDR-38 closes OD-09 and amends DEC-028): explicit recorded op, no default parameters, closure faces excluded, deviation report max/RMS, measurements refuse smoothed artifacts (FR-179)",
              reqs=["FR-179"], refs=["ALG-18", "DEC-028", "OD-09", "CH-12"], scope="MVP-Should", prio="P2", ms="M4a", pool="KERNEL",
              eff=(1, 2, 3), deps=[], deliverables="kernel/k06_ops + tests", result="Whole-surface smoothing available as an explicit, recorded option",
              completion="Whole-surface mode recorded as op parameter; closure faces excluded; guard passes; deviation report produced", tests="UT-FN-KOP-12-G; GT-FN-KOP-12-G (noisy sphere)",
              levels="UT, GT", dod="DoD-STD + DoD-K", gate="IDR-38", status="Ready (OD-09 closed by IDR-38)", owner="Kernel engineer",
              subtasks=[], skills=SKILLS["KERNEL"]))

# ---------------- Cross-cutting tasks
XC = []
def xc(id, mod, name, desc, reqs, fids, refs, ms, pool, eff, deps, deliv, result, comp, tests, levels, dod, gate="", status="Ready", owner=None, skills=None, scope="MVP-Core"):
    XC.append(dict(id=id, ttype="XC", fid="; ".join(fids) if fids else "—", mod=mod, name=name, description=desc,
                   reqs=reqs, refs=refs, scope=scope, prio=PRIO[scope], ms=ms, pool=pool, eff=eff, deps=deps,
                   deliverables=deliv, result=result, completion=comp, tests=tests, levels=levels, dod=dod,
                   gate=gate, status=status, owner=owner or ROLE[pool], subtasks=[], skills=skills or SKILLS[pool]))

xc("XC-FND-01", "XFND", "Ratify Implementation Decision Record IDR-01...IDR-38",
   "Publish DECISION_RECORD_2026-11-17 from IMPLEMENTATION_PLAN §6; engineering lead + product owner countersign; mark TD-01...TD-26 Approved/Conditional; close OQ-FS-01...08.",
   ["FR-173", "DATA-02", "FR-040", "FR-090", "SEC-11", "SEC-08", "NFR-05"], [], ["TD-01..TD-26", "OQ-FS-01..08"],
   "M0", "EXT", (0.5, 1, 2), [], "DECISION_RECORD_2026-11-17.md in project", "Blocked functions released for implementation",
   "Record signed (date, role); every IDR has status Approved or Approved-provisional", "DOC-CHK (check_docs script: every OQ-FS blocking item mapped)", "Inspection", "DoD-D",
   owner="Engineering lead + product owner", skills=SKILLS["EXT"], status="Done 2026-11-17 (ratified by EL + PO; DECISION_RECORD_2026-11-17.md)")
xc("XC-FND-02", "XFND", "Monorepo scaffold and local development environment",
   "Create repository per REPOSITORY_STRUCTURE_v1.0 (apps/web, services/api, services/worker, packages/kernel, packages/contracts); docker compose with proxy, web, api, worker, postgres, storage fake; health endpoints.",
   ["VER-20", "NFR-07"], [], ["BL-001", "IF-01", "IF-04"], "M0", "QA_OPS", (2, 3, 5), ["XC-FND-01"],
   "Repository skeleton + compose file + README", "Every later task lands in a fixed structure",
   "`docker compose up` starts all services; health endpoints return 200; make/just targets documented", "CI smoke job", "CI", "DoD-STD + DoD-C",
   status="Done 2026-11-17 (commit 8176603 on main; CI smoke green)")
xc("XC-FND-03", "XFND", "CI pipeline with staged quality gates",
   "GitHub Actions stages lint, unit, determinism, integration, oracle, security, e2e, performance (GEOMETRY_TESTING_STRATEGY §7); branch protection; required checks; artefact retention.",
   ["VER-20", "VER-07", "SEC-09"], ["FN-OPS-01", "FN-OPS-02"], ["BL-002"], "M0", "QA_OPS", (2, 4, 6), ["XC-FND-02"],
   ".github/workflows/*.yml + branch protection settings record", "Merges blocked on failing gates",
   "A seeded failing test in each stage blocks merge; pipeline time recorded", "CI self-test", "CI", "DoD-STD + DoD-C")
xc("XC-FND-04", "XFND", "Coding-standard tooling and architecture lint",
   "ruff (lint+format), mypy --strict for kernel/api, eslint+prettier+tsc strict for web, import-linter layer contracts (kernel has no I/O imports; UI never imports kernel), commitlint, pre-commit.",
   ["VER-20", "NFR-06"], [], ["DEVELOPMENT_STANDARDS §2-4"], "M0", "QA_OPS", (1, 2, 3), ["XC-FND-02"],
   "Config files + pre-commit hooks", "Uniform code and enforced layering", "Violations of each rule fail CI (seeded examples)", "CI-lint", "CI", "DoD-STD + DoD-C",
   status="Done 2026-11-19 (PR #2 merged; CI green)")
xc("XC-FND-05", "XFND", "Database schema baseline, roles and forward-only migrations",
   "Five schemas (clinical, geometry, governance, audit, ops), roles app_rw / worker_rw / audit_append (INSERT-only) / admin_ro, Alembic baseline, CHECK constraints (det, enums), migration test on empty DB.",
   ["DATA-01", "DATA-04", "DATA-05", "DATA-09", "DATA-10", "FR-002", "FR-121"], ["FN-AUD-06", "FN-CAS-01", "FN-JOB-01"],
   ["BL-008", "DS-01..DS-25", "TD-13"], "M0", "BACKEND", (3, 5, 8), ["XC-FND-02"],
   "services/api/migrations/ + schema docs", "Persistent model ready for all services", "Migration up on empty DB passes; audit role cannot UPDATE/DELETE (test)", "TC-DATA-*; IT-schema", "IT", "DoD-STD + DoD-B",
   status="Done 2026-11-19 (PR #6 merged; CI green)")
xc("XC-FND-06", "XFND", "API contract pipeline (OpenAPI 3.1 -> TypeScript client)",
   "/api/v1 prefix, OpenAPI generated from FastAPI as contract of record, openapi-typescript client generation, contract diff check in CI (additive-only within v1).",
   ["NFR-05", "FR-015"], ["FN-API-02"], ["IF-01", "TD-22"], "M0", "BACKEND", (1.5, 2.5, 4), ["XC-FND-02"],
   "packages/contracts/openapi.json + generated client package", "UI and API share one typed contract", "Breaking change in a PR fails CI; client regenerates deterministically", "CI-contract", "CI, IT", "DoD-STD + DoD-B")
xc("XC-FND-07", "XFND", "Environments and deployment topology (dev / staging / pilot)",
   "Single Linux x86-64 container host in the Supabase project's region (IDR-07); C0 reverse proxy with TLS >= 1.2 and size cap; secrets management; deployment record (region, image digests, adapter versions).",
   ["SEC-04", "SEC-10", "SEC-13"], ["FN-OPS-05"], ["TD-13", "TD-26", "OQ-FS-08", "TQ-02"], "M1", "QA_OPS", (3, 5, 8), ["XC-FND-03", "XC-EXP-08"],
   "infra/ compose + proxy config + docs/deployment/DEPLOYMENT_RECORD.md", "Staging reachable over HTTPS with same-origin /api routing",
   "TLS scan passes (no < 1.2); upload over cap rejected at proxy; deployment record complete", "IT-deploy; SEC TLS check", "IT, SEC", "DoD-STD + DoD-O", gate="IDR-07")
xc("XC-FND-08", "XFND", "Supabase project wiring: Postgres roles, Storage buckets, IF-04 adapter",
   "Buckets scans/artifacts/prescriptions/exports/reports; service credentials; BlobStore Supabase adapter (put/get/exists, no overwrite, no delete for app credential) using X-07 results.",
   ["FR-011", "SEC-13", "SEC-08"], ["FN-BLB-01"], ["IF-04", "TD-13", "X-07"], "M1", "BACKEND", (2, 4, 6), ["XC-EXP-07", "TSK-BLB-01-A"],
   "services/api/src/jude_api/platform/blobstore/supabase.py + config", "Production blob store behind IF-04", "Adapter passes the same contract tests as the filesystem adapter; overwrite/delete attempts fail", "IT-IF04-contract", "IT", "DoD-STD + DoD-B", gate="IDR-07")
xc("XC-FND-09", "XFND", "Worker sandbox for untrusted parsing",
   "Parse/import in a child process with rlimits (CPU, address space), read-only filesystem, no network, non-root, Docker default seccomp (IDR-07/TQ-20).",
   ["SEC-07"], ["FN-SCN-02"], ["TD-16", "TQ-20"], "M1", "QA_OPS", (2, 4, 7), ["TSK-JOB-02-J"],
   "services/worker sandbox launcher + container hardening config", "Malformed files cannot crash worker or API", "Face-bomb, zip-bomb-like and truncated fixtures terminate the child only; worker stays healthy", "SEC-upload-abuse fixtures (T3)", "IT, SEC", "DoD-STD + DoD-O", gate="IDR-07")
xc("XC-FND-10", "XFND", "Documentation baseline alignment",
   "Regenerate SRS v0.3 from RTM v0.3 (OQ-FS-34); RTM v0.4 rows for case list/search and synthetic-surface warning (IDR-28); test catalogue v0.4 with T13-T15 and UT IDs; retire BL-112; backlog text fix BL-030/BL-115 (OQ-FS-05).",
   ["FR-004", "FR-021", "VER-20"], [], ["OQ-FS-34", "OQ-FS-05", "OQ-FS-35", "IDR-28"], "M0", "EXT", (2, 3, 5), ["XC-FND-01"],
   "SRS v0.3, RTM v0.4, test catalogue v0.4 in project", "Docs and code share one requirement baseline", "check_docs passes: every MVP requirement has >= 1 task and >= 1 test ID", "DOC-CHK", "Inspection", "DoD-D",
   owner="Requirements owner + engineering lead", skills=SKILLS["EXT"])
xc("XC-FND-11", "XFND", "Structured logging, correlation IDs and error middleware",
   "JSON logs (no personal data, no mesh data), correlation_id propagated UI->API->job->kernel report, EH-API mapping to DS-24, health/readiness endpoints, basic metrics.",
   ["NFR-07", "NFR-08", "SEC-18"], ["FN-API-02"], ["DS-24", "DEVELOPMENT_STANDARDS §8-9"], "M0", "BACKEND", (1.5, 2.5, 4), ["XC-FND-02"],
   "platform/logging + middleware + log schema", "Every request and job traceable by correlation_id", "Log-scrubbing test: seeded identifiers never appear in logs", "UT-logging; IT-correlation", "UT, IT", "DoD-STD + DoD-B")
xc("XC-FND-12", "XSHR", "Kernel contracts: MeshArrays, jude-arr/1, OpResult, kernel runner",
   "DS-01 MeshArrays value type, jude-arr/1 canonical container (own header, no pickle/zip timestamps - IDR-15), DS-05 OpResult, IF-03 runner stamping op_version/kernel_version/image digest.",
   ["FR-052", "VER-07", "FR-011"], ["FN-KRP-04", "FN-BLB-01"], ["DS-01", "DS-05", "IF-03", "TQ-25", "TD-19", "TD-21"], "M0", "KERNEL", (2, 3, 5), ["XC-FND-02"],
   "packages/kernel/src/jude_kernel/core/", "Every kernel op shares one typed contract", "Round-trip of jude-arr/1 bit-exact; −0.0 canonicalised; runner rejects I/O imports (import-linter)", "UT-core; PT-jude-arr", "UT, PT", "DoD-STD + DoD-K", gate="IDR-15")
xc("XC-SHR-01", "XSHR", "Exact geometric predicates (orient2d/orient3d) port",
   "Port of public-domain Shewchuk adaptive predicates (TD-04) with float filter + exact fallback; tested against Python fractions on adversarial set T13.",
   ["FR-171", "FR-080", "FR-173"], ["FN-KVL-05", "FN-KOP-06", "FN-KMS-04"], ["TD-04", "ALG-11", "ALG-25", "LIB-PREDICATES"], "M0", "KERNEL", (3, 5, 8), ["XC-FND-12", "XC-EXP-06"],
   "jude_kernel/shared/predicates.py (+ numba kernels)", "Sign-exact orientation tests for all robustness-critical code", "100 % agreement with rational oracle on T13 (>= 10^5 cases); determinism 100 runs", "UT-predicates; PT-predicates vs fractions (T13)", "UT, PT, GT", "DoD-STD + DoD-K", gate="IDR-10")
xc("XC-SHR-02", "XSHR", "Deterministic AABB BVH (closest point, ray, box-pair traversal)",
   "Median-split BVH shared by ALG-11/33/34/40; Ericson closest-point regions; tie rule = smallest face_id (T14); incremental refit for guard; numba inner loops (IDR-10).",
   ["FR-030", "FR-171", "FR-070", "FR-172"], ["FN-KAN-01", "FN-KVL-05", "FN-KCP-01", "FN-KAN-03"], ["ALG-33", "ALG-11", "TD-03", "TQ-05"], "M1", "KERNEL", (5, 8, 13), ["XC-FND-12", "XC-EXP-06"],
   "jude_kernel/shared/bvh.py", "One spatial index for all queries", "Equals brute-force oracle on 10^4 random queries incl. ties; 100-run determinism; build/query times recorded (BM-01)", "UT-bvh; GT-bvh vs brute force (T1, T14)", "UT, PT, GT", "DoD-STD + DoD-K", gate="IDR-10")
xc("XC-SHR-03", "XSHR", "Fixture sets T13-T15 (adversarial predicates, ties, contours)",
   "Generators and frozen files for T13 (near-coplanar, 1-ulp), T14 (equidistant faces, planes through vertices), T15 (convex/concave/comb/spiral contours).",
   ["VER-01", "VER-08"], ["FN-OPS-06"], ["GEOMETRY_TESTING_STRATEGY §2"], "M0", "KERNEL", (1.5, 2.5, 4), ["TSK-OPS-06-C"],
   "tests/fixtures/T13..T15 + generator scripts", "Robustness fixtures available to all kernel tests", "Fixture hashes frozen; generator reproducible", "CI-fixtures", "CI", "DoD-STD + DoD-C")
xc("XC-WSK-01", "XFND", "Walking skeleton: phantom STL -> closed positive -> export through every layer",
   "Dev-only route (test_only flag, IDR-31): upload phantom -> parse job -> mm -> test-only frame fixture -> closure -> validity -> hash-bound minimal approval -> STL export + re-import -> download; viewer shows LOD.",
   ["STK-01", "VER-15", "VER-06", "VER-07"], ["FN-SCN-02", "FN-KOP-06", "FN-KVL-07", "FN-KRP-01", "FN-KIO-07"], ["BL-017", "BL-018", "BL-019", "BL-020", "OQ-FS-38"], "M1", "BACKEND", (3, 5, 8),
   ["TSK-KOP-06-K", "TSK-KVL-07-K", "TSK-KRP-01-K", "TSK-KIO-07-K", "TSK-KEX-02-K", "TSK-JOB-04-J", "TSK-UIX-02-U", "TSK-KIO-05-K", "TSK-KOP-04-K"],
   "Integration route + E2E smoke test + demo script", "Architecture proven end to end before features widen", "Phantom T2 goes through in CI; exported STL re-reads within 1e-4 mm; test_only artefacts cannot be promoted (FN-CFG-07 check stub)", "ST-WSK-01 (system smoke)", "ST", "DoD-STD + DoD-B", gate="IDR-01; IDR-31")

# Experiments
def xe(id, name, desc, reqs, decides, ms, pool, eff, deps, gate="", status="Ready", scope="MVP-Core"):
    xc(id, "XEXP", name, desc, reqs, [], decides, ms, pool, eff, deps,
       f"docs/experiments/{id}.md + raw results (CSV) + decision proposal", f"Evidence for {', '.join(decides[:3])}",
       "Report states hardware, image digest, versions, runs, median/p95; recommendation signed by engineering lead", f"{id} protocol (TECHNICAL_OPEN_QUESTIONS §3 / PERFORMANCE_REQUIREMENTS §4)", "PERF/EXP", "DoD-X", gate=gate, status=status, scope=scope)
xe("XC-EXP-06", "X-06 numba determinism and warm-up on two hosts", "Bit-equality of numba kernels (fastmath off, parallel off) across 100 runs x 2 hosts; JIT warm-up time at worker start.", ["VER-07"], ["TD-02", "TQ-11"], "M0", "KERNEL", (1.5, 2.5, 4), ["XC-FND-12"])
xe("XC-EXP-08", "X-08 container image build matrix", "Build worker image for Python 3.12 linux/amd64 with all candidate wheels (numpy, scipy, numba, fast-simplification, WeasyPrint system libs); record SOUP list.", ["SEC-09"], ["TQ-09"], "M0", "QA_OPS", (1, 2, 3), ["XC-FND-02"])
xe("XC-EXP-01", "X-01 determinism and tie handling of candidate libraries", "Own BVH vs libigl vs Open3D (closest point); fast-simplification vs meshoptimizer (display LOD); own windowed-sinc only (VTK excluded by IDR-11).", ["VER-07", "NFR-03"], ["TD-03", "TD-11", "TQ-05", "TQ-07"], "M1", "KERNEL", (2, 4, 6), ["XC-SHR-02", "XC-EXP-08"])
xe("XC-EXP-02", "X-02 self-intersection detector vs CGAL oracle (synthetic part)", "Counts vs CGAL on VER-08 + ghost layers; time vs m; incremental mode; real-scan part runs in XC-EXP-02R after VER-22.", ["FR-171", "VER-08"], ["TD-05", "TQ-22"], "M1", "KERNEL", (2, 3, 5), ["TSK-KVL-05-K", "TSK-OPS-07-C"])
xe("XC-EXP-07", "X-07 Supabase Storage immutability and backup/restore verification", "Scratch project: attempt overwrite/delete with app credential; separate encrypted restic backup; restore drill re-verifies SHAs.", ["SEC-08", "FR-011", "SEC-11"], ["TD-13", "TQ-03", "MA-05"], "M1", "QA_OPS", (1.5, 2.5, 4), ["XC-FND-02"], gate="IDR-07")
xe("XC-EXP-BM01", "BM-01 synthetic scaling series harness and first run", "Icosphere/ellipsoid s = 4...8 + T3 defects through parse, integrity, BVH; time and RSS; reporting rule of PERFORMANCE_REQUIREMENTS §4.", ["NFR-03"], ["PM-04", "PM-05", "PM-11"], "M1", "QA_OPS", (2, 3, 5), ["TSK-KVL-05-K", "TSK-KIO-05-K", "XC-EXP-08"])
xe("XC-EXP-LOCK", "Library lock-in sign-off (TD-02/03/05/11, ADR-002)", "Engineering lead signs library choices using X-01, X-02, X-06, X-08 evidence; SOUP list frozen for MVP; fallbacks recorded.", ["SEC-09"], ["TD-02", "TD-03", "TD-05", "TD-11", "OQ-FS-30"], "M1", "EXT", (0.5, 1, 1.5), ["XC-EXP-01", "XC-EXP-02", "XC-EXP-06", "XC-EXP-08"], gate="IDR-33")
xe("XC-EXP-02R", "X-02 real-scan part + BM-02 real clinic scan statistics", "After VER-22: >= 3 anonymised clinic exports per format; face counts, sizes, holes, ghost layers, base-contour sizes; self-intersection timing on real scans.", ["NFR-03", "SEC-17", "INT-08"], ["PM-01", "PM-02", "PM-03", "TQ-12", "TQ-13"], "M3", "KERNEL", (2, 3, 5), ["XC-PLT-01", "TSK-SCN-05-J"], gate="EXT-01 (VER-22)", status="Gated: VER-22 record")
xe("XC-EXP-03", "X-03 closure option A on real open scans", "Frequency of holes above base plane and non-simple base contours; drives IDR-01 confirmation and OQ-FS-37 handling.", ["FR-173", "VER-15"], ["OQ-FS-01", "TD-07"], "M3", "KERNEL", (1, 2, 3), ["XC-EXP-02R", "TSK-KOP-06-V"], gate="EXT-01 (VER-22)", status="Gated: VER-22 record")
xe("XC-EXP-05", "X-05 hole-filling quality and cost on clinic scans", "Patch deviation and time vs loop size on real holes; proposes n_max (TQ-12).", ["FR-021"], ["TD-06", "TQ-12"], "M3", "KERNEL", (1, 2, 3), ["XC-EXP-02R", "TSK-KOP-02-V"], gate="EXT-01 (VER-22)", status="Gated: VER-22 record", scope="MVP-Should")
xe("XC-EXP-04", "X-04 regeneration latency with per-op cache (BM-07 part)", "Edit-to-preview latency on synthetic designs with 1...20 ops; feeds NFR-04 proposal.", ["NFR-04"], ["TD-01", "PM-06"], "M4", "KERNEL", (1, 2, 3), ["TSK-DES-03-J"])
xe("XC-EXP-BM03", "BM-03 cross-host determinism", "T9 reference designs x 100 regenerations on host A and host B with the same image.", ["VER-07"], ["TD-19", "TQ-16"], "M6", "QA_OPS", (1, 2, 3), ["TSK-OPS-04-C", "TSK-DES-03-J"])
xe("XC-EXP-BM04", "BM-04 viewer performance on clinic PCs and browsers", "LOD budgets 50k...1M faces on each supported browser and min-spec PC; first render, fps, BVH build.", ["NFR-01", "NFR-02", "NFR-03"], ["PM-09", "PM-10"], "M6", "FRONTEND", (1.5, 2.5, 4), ["TSK-UIX-02-U", "XC-PLT-02"], gate="EXT-02", status="Gated: clinic IT inventory")
xe("XC-EXP-BM05", "BM-05/06/07 platform latency, memory profile, end-to-end job latency", "Job claim latency, audit append overhead, blob throughput, peak RSS per job type, p95 of regenerate/review/export/report on staging.", ["NFR-04", "NFR-07"], ["PM-06", "PM-07", "PM-08", "PM-11", "PM-18", "PM-19"], "M6", "QA_OPS", (2, 3, 5), ["TSK-EXP-02-J", "TSK-REV-01-J", "XC-FND-07"])

# Pilot readiness
def xp(id, name, desc, reqs, fids, refs, ms, pool, eff, deps, deliv, comp, gate="", status="Ready", owner=None, tests="Inspection record", levels="Inspection"):
    xc(id, "XPLT", name, desc, reqs, fids, refs, ms, pool, eff, deps, deliv, name, comp, tests, levels, "DoD-P", gate=gate, status=status, owner=owner, skills=SKILLS["EXT"] if pool == "EXT" else None)
xp("XC-PLT-02", "Clinic IT inventory (browsers, PCs, network)", "Collect browser versions, PC specs and upload bandwidth at Saigak Orto for NFR-01/02, TQ-14.", ["NFR-01", "NFR-02"], [], ["OQ-A2", "TQ-14"], "M2", "EXT", (0.5, 1, 2), [], "Inventory record", "Inventory signed by clinic IT", gate="EXT-02", status="Gated: clinic availability", owner="Clinic IT + engineering lead")
xp("XC-PLT-01", "VER-22 privacy controls inspection performed and recorded", "Privacy specialist inspects SEC-10...SEC-18 controls on staging; record ID opens the real-patient-data gate (SEC-17).", ["VER-22", "SEC-17", "STK-06"], ["FN-OPS-10", "FN-CFG-08"], ["BL-132"], "M2", "EXT", (2, 3, 5),
   ["TSK-OPS-10-O", "TSK-CFG-08-B", "TSK-OPS-05-O", "TSK-CAS-08-O", "XC-FND-07", "XC-FND-08", "TSK-AUD-02-A", "TSK-CAS-06-B"], "VER-22 inspection record (ID)", "Record exists and is referenced by the gate; open findings = 0 high", gate="EXT-01", status="Gated: privacy specialist", owner="Privacy specialist")
xp("XC-PLT-03", "Set pilot-entry engineering values (N, S, face cap, LOD budget, n_max, time budgets)", "Decision record from BM-02/BM-04/BM-05 evidence; values entered in configuration/constants; NFR-01...04 rows updated.", ["NFR-01", "NFR-02", "NFR-03", "NFR-04", "SEC-07"], [], ["OQ-FS-29", "TQ-12", "TQ-13", "PM-01..PM-10"], "M6", "EXT", (1, 1.5, 2), ["XC-EXP-02R", "XC-EXP-BM04", "XC-EXP-BM05"], "Decision record + RTM update", "All PM marked TBD in PERFORMANCE_REQUIREMENTS have a value or an explicit waiver", gate="EXT-03", status="Gated: BM evidence", owner="Engineering lead + clinic IT")
xp("XC-PLT-10", "Legal review of licence allow-list and SOUP list", "External review of ADR-011 allow-list and the MVP SOUP list (TQ-24, OQ-G6).", ["SEC-09"], ["FN-OPS-02"], ["TD-23", "TQ-24"], "M6", "EXT", (1, 2, 4), ["XC-EXP-LOCK", "TSK-OPS-02-C"], "Legal review memo", "No unresolved licence finding", gate="EXT-07", status="Gated: external reviewer", owner="Product owner")
xp("XC-PLT-04", "Enter clinic configuration on site", "Clinic technician enters landmark set, measurement definitions, gate thresholds, sectors, base convention, export frame, checklist, ranges (DEC-027/DEC-029); production safety check passes.", ["FR-140", "DATA-07", "DATA-02", "FR-014", "FR-172"], ["FN-CFG-01", "FN-CFG-07"], ["BL-065", "DEC-029"], "M7", "EXT", (2, 3, 5), ["TSK-CFG-07-J", "TSK-CFG-05-B", "TSK-CFG-06-B", "XC-PLT-05"], "Published configuration version (non test_only)", "FN-CFG-07 safety check passes on pilot", gate="EXT-04", status="Gated: clinic technician", owner="Clinic technician + engineering lead")
xp("XC-PLT-05", "Pilot environment deployment and runbook", "Deploy pilot stack from tagged release; restore drill; monitoring; operator runbook; deployment record.", ["SEC-04", "SEC-08", "NFR-01"], ["FN-OPS-05"], ["BL-071", "BL-129"], "M7", "QA_OPS", (2, 3, 5), ["XC-FND-07", "TSK-OPS-05-O", "TSK-OPS-12-C"], "Pilot deployment record + runbook", "Restore drill meets RPO/RTO 24 h (SD-03); TLS check passes", owner="QA / DevOps engineer", tests="OT-restore; SEC TLS check", levels="OT, SEC")
xp("XC-PLT-06", "Clinic file coverage (INT-08)", ">= 3 real Artec exports per supported format import, pass integrity and are recorded.", ["INT-08", "FR-010"], ["FN-SCN-02"], ["BL-066", "OQ-FS-31"], "M7", "QA_OPS", (1, 1.5, 3), ["XC-EXP-02R", "TSK-SCN-02-J"], "Coverage record", "All clinic formats in use import without error", gate="EXT-05", status="Gated: clinic files", tests="TC-INT-08", levels="ST")
xp("XC-PLT-07", "Physical verification: VER-02 phantom, VER-06 Rodin4D Neo round-trip, VER-16 physical positive", "Execute physical checks with clinic production; results recorded via FN-OPS-11 against clinic values.", ["VER-02", "VER-06", "VER-16", "INT-04", "VER-04"], ["FN-OPS-11"], ["BL-067", "BL-068", "BL-069", "OQ-FS-32"], "M7", "EXT", (3, 5, 9), ["TSK-OPS-11-O", "TSK-EXP-03-B"], "Verification records", "Each record pass/fail against clinic values; failures triaged", gate="EXT-06", status="Gated: clinic production + Rodin4D access", owner="QA lead + clinic production")
xp("XC-PLT-08", "VER-10 technician usability test and VER-23 agreement with manual measurements", "Timed design sessions vs current process; paired measurements Jude vs manual (Bland-Altman, ALG-59); clinic sets thresholds (DEC-030).", ["VER-10", "VER-23", "STK-07", "UR-01"], ["FN-OPS-09"], ["BL-070", "BL-136", "DEC-030"], "M7", "EXT", (3, 5, 8), ["TSK-OPS-09-O", "XC-PLT-04", "XC-PLT-12"], "Pilot evaluation report", "Both measures computed with n, CI; compared with clinic thresholds", gate="EXT-04", status="Gated: clinic sessions", owner="Product owner + clinical lead")
xp("XC-PLT-12", "User guide (Russian), training session and intended-use materials", "Short task-based guide for technician and clinic admin; intended-use statement placements checked; training record.", ["UR-09", "SAF-01", "STK-05"], ["FN-UIX-01"], ["BL-059"], "M7", "FRONTEND", (2, 3, 5), ["TSK-EXP-03-U"], "docs/user/ru/ guide + training record", "Guide reviewed by clinical lead; wording lint clean", owner="Frontend engineer + product owner", tests="VER-09 lint; review record", levels="Inspection")
xp("XC-PLT-11", "Pilot go/no-go review and release v1.0.0", "Exit review of M7 against pilot-entry criteria; release tag; SOUP list; release notes; known-issues list.", ["STK-01", "STK-04", "STK-06", "STK-07"], [], ["IMPLEMENTATION_PLAN §10"], "M7", "EXT", (0.5, 1, 2), ["XC-PLT-04", "XC-PLT-05", "XC-PLT-06", "XC-PLT-07", "XC-PLT-08", "XC-PLT-03", "XC-PLT-10"], "Go/no-go record + release tag", "All pilot-entry criteria met or waived in writing", owner="Product owner + engineering lead")

xp("XC-PLT-13", "Observe a cranial-helmet modelling session in Rodin4D / Pi.Cas.So. (CH-16)",
   "Technician demonstrates a real helmet design; record which tools are used (zones, symmetric zones, profiles, elongation, smoothing, live metrics, sections), typical op count and values range (no patient data recorded); confirms or trims CH-01...CH-13.",
   ["UR-01", "STK-07"], [], ["CN-2026-11-17", "CH-16"], "M0", "EXT", (1, 2, 3), [], "Observation note (tool inventory, op count)",
   "Tool inventory signed by the clinic technician; CN-2026-11-17 items confirmed, changed or dropped", gate="", status="Done 2026-11-17 (session observed by the product owner; Rodin4D photos; case observed was TLSO - helmet-specific use confirmed informally at next clinic contact, non-blocking)", owner="Product owner + clinic technician")
for t in XC: add_task(t)
for t in tasks.values():
    if t["id"] == "XC-PLT-02":
        t["description"] += " Include the remote-desktop setup observed with Rodin4D (Chrome Remote Desktop from laptops on battery): network latency and client devices (CH-14)."
    if t["id"] == "XC-EXP-BM04":
        t["description"] += " Run on the actual technician devices and over the clinic network/remote setup (CH-14)."
    if t["id"] == "XC-EXP-04":
        t["description"] += " Reference history of ~20 operations (zones, symmetric zones, radius, smoothing, elongation) mirroring an observed Rodin4D design (CH-15)."
        t["ms"] = "M4a"

# ---------------- Dependencies
FTASKS = defaultdict(list)
for t in tasks.values():
    if t["ttype"] not in ("XC",):
        FTASKS[t["fid"]].append(t["id"])

def ptask(fid):
    return primary.get(fid)

for t in list(tasks.values()):
    if t["ttype"] in ("XC", "X", "KG"): continue
    fid = t["fid"]; r = FN[fid]
    deps = []
    fdeps = split_ids(r["depends_on"])
    if t["ttype"] in ("K", "B", "J", "A", "O", "C"):
        for d in fdeps:
            if (fid, d) in DROP_EDGES: continue
            if d in primary and scope_of(d) in ("MVP-Core", "MVP-Should"): deps.append(primary[d])
        if t["ttype"] == "K":
            deps.append("XC-FND-12")
            if fid in ("FN-KVL-05",): deps += ["XC-SHR-01", "XC-SHR-02"]
            if fid in ("FN-KAN-01", "FN-KCP-01", "FN-KAN-03"): deps.append("XC-SHR-02")
            if fid in ("FN-KMS-02", "FN-KMS-04", "FN-KOP-06", "FN-KIO-03", "FN-KVL-02", "FN-KOP-14"): deps.append("XC-SHR-01")
            if fid == "FN-KOP-14": deps.append("XC-SHR-02")
            if fid == "FN-KOP-04": deps.append("XC-EXP-01")
        if t["ttype"] in ("B", "A", "J", "O"):
            deps += ["XC-FND-05", "XC-FND-11"]
            if t["ttype"] == "B": deps.append("XC-FND-06")
        if t["ttype"] == "C": deps.append("XC-FND-03")
        if t["ttype"] == "J" and fid not in ("FN-JOB-02", "FN-JOB-04"): deps.append("TSK-JOB-02-J")
        if fid == "FN-SCN-02": deps.append("XC-FND-09")
        if fid in ("FN-BLB-03", "FN-OPS-05", "FN-BLB-04"): deps.append("XC-FND-08")
        if t["status"].startswith("Ready after IDR"): deps.append("XC-FND-01")
        if fid in NEW_AC and fid != "FN-PMV-13": deps.append("XC-PLT-13")
    elif t["ttype"] == "V":
        deps = [f"TSK-{t['mod']}-{fid.split('-')[-1]}-K", "TSK-OPS-06-C", "XC-SHR-03"]
    elif t["ttype"] == "U":
        own = [x for x in FTASKS[fid] if x.endswith(("-B", "-J", "-K"))]
        deps = own[:1] + ["XC-FND-06"]
        for d in fdeps:
            if d in uitask: deps.append(uitask[d])
        if MORD[t["ms"]] >= 2 and fid != "FN-UIX-01": deps.append("TSK-UIX-01-U")
        if fid == "FN-UIX-02": deps.append("TSK-KOP-04-K")
        if fid == "FN-KOP-14": deps.append("TSK-UIX-05-U")
        if fid in NEW_AC and fid not in ("FN-KOP-14",) and t["ttype"] == "U" and not own: deps.append("TSK-UIX-02-U")
    t["deps"] = list(OrderedDict.fromkeys([d for d in deps if d != t["id"]]))

tasks["TSK-KOP-12-KG"]["deps"] = ["TSK-KOP-12-K"]

# milestone stabilisation tasks (10 % of ML effort of the pool in the milestone)
for m in MS_LIST[1:]:
    for pool in ("KERNEL", "BACKEND", "FRONTEND", "QA_OPS"):
        mem = [t for t in tasks.values() if t["ms"] == m and t["pool"] == pool and t["ttype"] != "X" and not t["id"].startswith("XC-STB") and t["scope"] == "MVP-Core"]
        ml = sum(t["eff"][1] for t in mem)
        if ml < 4: continue
        e = (round(ml * 0.05, 1), round(ml * 0.10, 1), round(ml * 0.20, 1))
        add_task(dict(id=f"XC-STB-{m}-{pool}", ttype="XC", fid="—", mod="XSTB", name=f"Stabilisation {m} - {pool.lower()} (defects, refactoring, review findings)",
                      description=f"Reserved capacity = 10 % (5-20 %) of {pool} effort in {m} for defect fixing and review findings before milestone exit.",
                      reqs=["VER-20"], refs=[f"{m} exit criteria"], scope="MVP-Core", prio="P1", ms=m, pool=pool, eff=e,
                      deps=[t["id"] for t in mem], deliverables="Closed defects; updated tests", result=f"{m} exit criteria met",
                      completion=f"No open P1 defect in {m} scope; all {m} CI gates green", tests="Regression suite of the milestone",
                      levels="RT", dod="DoD-STD", gate="", status="Ready", owner=ROLE[pool], subtasks=[], skills=SKILLS[pool]))

# release-candidate gate: feature freeze of MVP-Core (M0-M5) before system verification and pilot work
stb = [t["id"] for t in tasks.values() if t["id"].startswith("XC-STB-") and MORD[t["ms"]] <= MORD["M5"]]
covered_by_stb = set()
for sid in stb: covered_by_stb.update(tasks[sid]["deps"])
rc_deps = stb + [t["id"] for t in tasks.values() if t["scope"] == "MVP-Core" and t["ttype"] != "X" and MORD.get(t["ms"], 99) <= MORD["M5"]
                 and t["id"] not in covered_by_stb and not t["id"].startswith("XC-STB")]
add_task(dict(id="XC-REL-01", ttype="XC", fid="—", mod="XSTB", name="Release candidate RC1: MVP-Core feature freeze (M0-M5 complete)",
              description="Tag RC1 when every MVP-Core task of M0-M5 is done and all merge-blocking CI stages are green; MVP-Should items not finished by then move to v1.1 per the cut line (MVP_SCOPE §4).",
              reqs=["VER-20", "STK-01"], refs=["MVP_SCOPE §4", "DEVELOPMENT_ROADMAP §3"], scope="MVP-Core", prio="P1", ms="M6", pool="EXT", eff=(0.5, 1, 2),
              deps=rc_deps, deliverables="Git tag v1.0.0-rc.1 + release notes + SOUP list", result="Stable baseline for system verification and pilot preparation",
              completion="All MVP-Core tasks of M0-M5 closed; CI green on tag; cut-line decision recorded for unfinished MVP-Should items",
              tests="Full CI on tag (lint, unit, determinism, integration, oracle, security)", levels="RT, CI", dod="DoD-STD",
              gate="", status="Ready", owner="Engineering lead", subtasks=[], skills=SKILLS["EXT"]))
for tid in ("TSK-OPS-08-C", "TSK-OPS-12-C", "XC-EXP-BM03", "XC-EXP-BM04", "XC-EXP-BM05", "XC-PLT-05", "XC-PLT-04", "XC-PLT-06", "XC-PLT-07", "XC-PLT-08", "XC-PLT-12", "XC-PLT-03"):
    if "XC-REL-01" not in tasks[tid]["deps"]: tasks[tid]["deps"].append("XC-REL-01")

# ---------------- Milestone consistency: task cannot depend on a later milestone
def mnum(t):
    return MORD.get(t["ms"], 99)
viol = []
changed = True
while changed:
    changed = False
    for t in tasks.values():
        if t["ttype"] == "X": continue
        for d in t["deps"]:
            dt = tasks[d]
            if mnum(dt) > mnum(t):
                viol.append((t["id"], t["ms"], d, dt["ms"]))
                t["ms"] = dt["ms"]; changed = True

# ---------------- Critical path (unlimited resources; duration = ML / focus)
FOCUS = 0.7
order = []
seen = set()
def visit(n, stack=()):
    if n in seen: return
    if n in stack: raise SystemExit("cycle at " + n)
    for d in tasks[n]["deps"]: visit(d, stack + (n,))
    seen.add(n); order.append(n)
sched_ids = [t["id"] for t in tasks.values() if t["ttype"] != "X"]
for n in sched_ids: visit(n)
EF, prevp = {}, {}
for n in order:
    t = tasks[n]; dur = t["eff"][1] / FOCUS
    es = 0; pp = None
    for d in t["deps"]:
        if EF[d] > es: es = EF[d]; pp = d
    EF[n] = es + dur; prevp[n] = pp
core_ids = [n for n in EF if tasks[n]["scope"] == "MVP-Core"]
end = max(core_ids, key=EF.get)
CORE_TO_SHOULD = [(n, d) for n in sched_ids if tasks[n]["scope"] == "MVP-Core" for d in tasks[n]["deps"] if tasks[d]["scope"] == "MVP-Should"]
cp = []
n = end
while n: cp.append(n); n = prevp[n]
cp = cp[::-1]
CPSET = set(cp)
# tail length for priority
succ = defaultdict(list)
for n in sched_ids:
    for d in tasks[n]["deps"]: succ[d].append(n)
TAIL = {}
for n in reversed(order):
    TAIL[n] = tasks[n]["eff"][1] / FOCUS + max([TAIL[s] for s in succ[n]] or [0])

# ---------------- Resource-constrained schedule (serial SGS)
SCEN = {
    "S1-Lean (2.5 FTE)": {"KERNEL": [1.0], "FULLSTACK": [1.0], "QA_OPS": [0.5], "EXT": [0.5, 0.5]},
    "S2-Reference (4 FTE)": {"KERNEL": [1.0], "BACKEND": [1.0], "FRONTEND": [1.0], "QA_OPS": [1.0], "EXT": [0.5, 0.5]},
    "S3-Balanced (6 FTE)": {"KERNEL": [1.0, 1.0], "BACKEND": [1.0, 1.0], "FRONTEND": [1.0], "QA_OPS": [1.0], "EXT": [0.5, 0.5]},
}
def pool_in(scen, pool):
    if pool in SCEN[scen]: return pool
    if pool in ("BACKEND", "FRONTEND"): return "FULLSTACK"
    return pool

def schedule(scen, effort):
    """Parallel schedule generation: whenever a worker is idle it takes the highest-priority ready task of its pool."""
    workers = []  # [free_at, speed, pool]
    for p, lst in SCEN[scen].items():
        for sp in lst: workers.append([0.0, sp, p])
    fin, start = {}, {}
    remaining = set(sched_ids)
    npool = {n: pool_in(scen, tasks[n]["pool"]) for n in sched_ids}
    prio = {n: (mnum(tasks[n]), -TAIL[n], n) for n in sched_ids}
    t = 0.0
    while remaining:
        progressed = True
        while progressed:
            progressed = False
            for w in sorted(workers, key=lambda w: -w[1]):
                if w[0] > t + 1e-9: continue
                ready = [n for n in remaining if npool[n] == w[2] and all(d in fin and fin[d] <= t + 1e-9 for d in tasks[n]["deps"])]
                if not ready: continue
                n = min(ready, key=lambda n: prio[n])
                start[n] = t; fin[n] = t + effort[n] / (FOCUS * w[1]); w[0] = fin[n]
                remaining.discard(n); progressed = True
        future = [w[0] for w in workers if w[0] > t + 1e-9] + [fin[n] for n in fin if fin[n] > t + 1e-9]
        if not future:
            raise SystemExit("deadlock: " + str(sorted(remaining)[:5]))
        t = min(future)
    return start, fin

ML = {n: tasks[n]["eff"][1] for n in sched_ids}
results = {}
for sc in SCEN:
    st, fi = schedule(sc, ML)
    results[sc] = (st, fi)

# Monte Carlo (triangular), effort and finish
random.seed(20261115)
MC = {}
RUNS = 200
for sc in SCEN:
    fins, effs = [], []
    msfin = defaultdict(list)
    for _ in range(RUNS):
        eff = {}
        bias = random.triangular(0.9, 1.4, 1.0)  # correlated estimation bias shared by all tasks
        for n in sched_ids:
            o, m, p = tasks[n]["eff"]
            eff[n] = bias * (random.triangular(o, p, m) if p > o else m)
        _, fi = schedule(sc, eff)
        fins.append(max(fi.values())); effs.append(sum(eff.values()))
        for m in range(len(MS_LIST)):
            ms = [fi[n] for n in sched_ids if mnum(tasks[n]) == m]
            if ms: msfin[m].append(max(ms))
    q = lambda xs, p: sorted(xs)[int(p * (len(xs) - 1))]
    MC[sc] = dict(fin={p: round(q(fins, p), 1) for p in (0.1, 0.5, 0.8, 0.9)},
                  eff={p: round(q(effs, p), 1) for p in (0.1, 0.5, 0.8, 0.9)},
                  ms={m: {p: round(q(v, p), 1) for p in (0.5, 0.8)} for m, v in msfin.items()})

REF = "S2-Reference (4 FTE)"
ref_st, ref_fi = results[REF]
for n in sched_ids:
    tasks[n]["sprint"] = f"S{int(ref_st[n] // 10) + 1:02d}"
    tasks[n]["cp"] = "Y" if n in CPSET else "N"
for t in tasks.values():
    t.setdefault("sprint", "—"); t.setdefault("cp", "N")

# ---------------- WBS rows (Epic > Module > Feature > Task > Subtask)
epic_mods = defaultdict(list)
for t in tasks.values():
    e = EPIC_OF_MOD.get(t["mod"], "EP-12")
    if t["mod"] not in epic_mods[e]: epic_mods[e].append(t["mod"])
rows = []
COLS = ["wbs_code", "level", "id", "parent_id", "epic_id", "module_code", "function_id", "name", "description",
        "requirement_ids", "design_refs", "release_scope", "priority", "milestone", "ref_sprint_S2", "dependencies",
        "complexity", "effort_opt_pd", "effort_ml_pd", "effort_pess_pd", "effort_pert_pd", "required_skills",
        "owner_role", "deliverables", "expected_result", "completion_criteria", "tests", "test_levels",
        "definition_of_done", "blocking_decisions_or_gates", "status", "critical_path"]

def blank(**kw):
    r = {c: "" for c in COLS}; r.update(kw); return r

def roll(ts):
    ts = [t for t in ts if t["scope"] in ("MVP-Core", "MVP-Should") and t["ttype"] != "X"]
    o = sum(t["eff"][0] for t in ts); m = sum(t["eff"][1] for t in ts); p = sum(t["eff"][2] for t in ts)
    return round(o, 1), round(m, 1), round(p, 1), round(sum(pert(*t["eff"]) for t in ts), 1)

for ei, (eid, ename) in enumerate(EPICS.items(), 1):
    ets = [t for t in tasks.values() if EPIC_OF_MOD.get(t["mod"], "EP-12") == eid]
    o, m, p, pe = roll(ets)
    rows.append(blank(wbs_code=f"{ei}", level="Epic", id=eid, name=ename, epic_id=eid,
                      effort_opt_pd=o, effort_ml_pd=m, effort_pess_pd=p, effort_pert_pd=pe,
                      release_scope="mixed" if eid != "EP-15" else "Next/Deferred"))
    for mi, mod in enumerate(epic_mods[eid], 1):
        mts = [t for t in ets if t["mod"] == mod]
        o, m, p, pe = roll(mts)
        rows.append(blank(wbs_code=f"{ei}.{mi}", level="Module", id=f"MOD-{mod}", parent_id=eid, epic_id=eid,
                          module_code=mod, name=MODNAME.get(mod, mod), effort_opt_pd=o, effort_ml_pd=m,
                          effort_pess_pd=p, effort_pert_pd=pe))
        feats = OrderedDict()
        for t in mts:
            key = t["fid"] if t["ttype"] != "XC" else f"XF-{mod}"
            feats.setdefault(key, []).append(t)
        for fi_, (fk, fts) in enumerate(feats.items(), 1):
            o, m, p, pe = roll(fts)
            if fk.startswith("XF-"):
                fname = MODNAME.get(mod, mod) + " - enabler tasks"; frq = ""; fsc = "MVP-Core"
            else:
                fname = FN[fk]["name"]; frq = FN[fk]["requirement_ids"]; fsc = scope_of(fk)
            fid_ = fk if not fk.startswith("XF-") else "—"
            rows.append(blank(wbs_code=f"{ei}.{mi}.{fi_}", level="Feature", id=fk if not fk.startswith("XF") else f"FEAT-{mod}",
                              parent_id=f"MOD-{mod}", epic_id=eid, module_code=mod, function_id=fid_, name=fname,
                              requirement_ids=frq, release_scope=fsc, priority=PRIO[fsc],
                              milestone=fts[0]["ms"], effort_opt_pd=o, effort_ml_pd=m, effort_pess_pd=p, effort_pert_pd=pe))
            for ti, t in enumerate(fts, 1):
                o, m, p = t["eff"]
                code = f"{ei}.{mi}.{fi_}.{ti}"
                rows.append(blank(wbs_code=code, level="Task", id=t["id"],
                                  parent_id=(fk if not fk.startswith("XF") else f"FEAT-{mod}"), epic_id=eid,
                                  module_code=mod, function_id=t["fid"], name=t["name"], description=t["description"],
                                  requirement_ids="; ".join(t["reqs"]), design_refs="; ".join(t["refs"]),
                                  release_scope=t["scope"], priority=t["prio"], milestone=t["ms"],
                                  ref_sprint_S2=t["sprint"], dependencies="; ".join(t["deps"]),
                                  complexity=cx(m) if t["ttype"] != "X" else "—", effort_opt_pd=o, effort_ml_pd=m,
                                  effort_pess_pd=p, effort_pert_pd=pert(o, m, p), required_skills=t["skills"],
                                  owner_role=t["owner"], deliverables=t["deliverables"], expected_result=t["result"],
                                  completion_criteria=t["completion"], tests=t["tests"], test_levels=t["levels"],
                                  definition_of_done=t["dod"], blocking_decisions_or_gates=t["gate"],
                                  status=t["status"], critical_path=t["cp"]))
                for si, (sfid, sname, spurp) in enumerate(t["subtasks"], 1):
                    rows.append(blank(wbs_code=f"{code}.{si}", level="Subtask", id=f"{t['id']}.S{si}", parent_id=t["id"],
                                      epic_id=eid, module_code=mod, function_id=sfid, name=sname, description=spurp,
                                      requirement_ids="; ".join(t["reqs"]) + " (inherited)", release_scope=t["scope"],
                                      priority=t["prio"], milestone=t["ms"], ref_sprint_S2=t["sprint"],
                                      effort_ml_pd="incl. in parent", tests=f"UT-{sfid}", test_levels="UT",
                                      definition_of_done="Covered by parent DoD", status=t["status"],
                                      completion_criteria=f"{sname}: behaviour per FS {sfid}; unit test UT-{sfid} passes"))

# ---- compact encodings (codes defined in IMPLEMENTATION_PLAN §5.3)
SKC = {SKILLS["KERNEL"]: "SK-KRN", SKILLS["BACKEND"]: "SK-BE", SKILLS["FRONTEND"]: "SK-FE", SKILLS["QA_OPS"]: "SK-QA; SK-OPS",
       SKILLS["EXT"]: "SK-DOM", SKILLS["QA_GEO"]: "SK-QAG"}
EXC = {"exact predicates (Shewchuk), BVH, numba": "SK-ROB", "polygon triangulation, exact orient2d": "SK-ROB",
       "minimum-weight triangulation, sparse linear algebra": "SK-NUM", "three.js, WebGL, Web Workers, three-mesh-bvh": "SK-3D",
       "three.js picking, BVH raycast": "SK-3D", "BVH closest point, tie rules": "SK-ROB", "signed distance, pseudonormals": "SK-ROB",
       "hash chains, RFC 8785 JCS, Postgres locking": "SK-SEC", "content-addressed caching, determinism": "SK-DET",
       "WeasyPrint, HTML/CSS print layout": "SK-PDF", "software rasterisation": "SK-NUM", "threat modelling, OWASP ASVS": "SK-SEC",
       "Supabase, S3-compatible storage, restic": "SK-OPS", "Playwright, cross-browser testing": "SK-QA",
       "privacy engineering, erasure procedures": "SK-PRV", "privacy inspection (VER-22) evidence": "SK-PRV"}
def skc(x):
    out = []
    for part in [p.strip() for p in x.split("; ") if p.strip()]:
        pass
    for k, v in SKC.items():
        if x.startswith(k): out.append(v); x = x[len(k):]
    for k, v in EXC.items():
        if k in x: out.append(v)
    return "; ".join(dict.fromkeys(out)) or x
ROC = {"Kernel engineer": "KE", "Backend engineer": "BE", "Frontend engineer": "FE", "QA / DevOps engineer": "QA",
       "QA engineer (geometry) - not the author of the K task": "QAG (not K author)", "Engineering lead + product owner": "EL + PO",
       "Requirements owner + engineering lead": "RO + EL", "Engineering lead": "EL", "Privacy specialist": "PS",
       "Clinic IT + engineering lead": "CIT + EL", "Engineering lead + clinic IT": "EL + CIT", "Product owner": "PO",
       "Clinic technician + engineering lead": "CT + EL", "QA lead + clinic production": "QA + CP",
       "Product owner + clinical lead": "PO + CL", "Frontend engineer + product owner": "FE + PO",
       "Product owner + engineering lead": "PO + EL", "See name": "EL"}
TYPEL = {"K": "kernel", "V": "geometric verification", "B": "domain/API", "U": "UI", "J": "job", "A": "service",
         "O": "procedure", "C": "CI tooling", "X": "outline"}
def short_status(stt):
    stt = stt.replace("Ready after IDR ratification (XC-FND-01); was blocked by ", "Ready after XC-FND-01 (was blocked: ")
    if stt.startswith("Ready after XC-FND-01") and not stt.endswith(")"): stt = stt.split(";")[0] + ")"
    stt = stt.replace("Ready (open items closed by ", "Ready (").replace("final values gated by", "values gated by")
    return stt
for r in rows:
    if r["level"] != "Task": continue
    t = tasks[r["id"]]
    r["required_skills"] = skc(t["skills"])
    r["owner_role"] = ROC.get(t["owner"], t["owner"])
    r["status"] = short_status(t["status"])
    if t["ttype"] == "KG":
        r["required_skills"] = "SK-KRN"; r["owner_role"] = "KE"
    if t["ttype"] in TYPEL:
        r["name"] = f"{FN[t['fid']]['name'] if t['ttype'] != 'U' else EXTRA_UI.get(t['fid'], FN[t['fid']]['name'])} [{TYPEL[t['ttype']]}]"
        tt = t["ttype"]; fid = t["fid"]; mod = t["mod"]
        algs = [x for x in t["refs"] if x.startswith("ALG")]; tds = [x for x in t["refs"] if x.startswith("TD")]
        al = (" per " + ", ".join(algs)) if algs else ""
        td = ("; " + ", ".join(tds)) if tds else ""
        spec = "; ".join(x for x in [", ".join(algs), ", ".join(tds)] if x)
        r["description"] = f"Template TT-{tt} (IMPLEMENTATION_PLAN §5.2)" + (f"; {spec}" if spec else "") if tt != "X" else t["description"]
        r["deliverables"] = {
            "K": f"kernel/{PKG.get(mod, '')} + tests",
            "V": f"tests/geometry/{PKG.get(mod, '')} + golden",
            "B": f"api/domain/{mod.lower()} + tests",
            "U": f"web/features/{mod.lower()} + tests",
            "J": f"worker/jobs/{mod.lower()} + tests",
            "A": f"jude_api/{'platform' if mod in ('IAM','API','AUD','JOB','BLB') else 'domain'}/{mod.lower()} + tests",
            "O": f"scripts/ops + docs/runbooks/{fid}.md + record template",
            "C": f".github/workflows + tools or tests harness",
            "X": t["deliverables"]}[tt]
        r["tests"] = r["tests"].replace(" (hypothesis, seeded)", "").replace(" (API+Postgres+storage fake)", "").replace(" (vitest/RTL)", "").replace(" (job runner + Postgres + storage fake; failure/retry paths)", "").replace(" (seeded violation makes the stage fail; clean tree passes)", "").replace(" (dry run on staging, record produced)", "").replace(" (proposed)", "")
        r["definition_of_done"] = t["dod"]
        seen_ = []
        for x in re.split(r"[;,] ", r["tests"]):
            x = x.strip()
            if x and x not in seen_: seen_.append(x)
        r["tests"] = "; ".join(seen_)

with open(f"{OUT}/WORK_BREAKDOWN_STRUCTURE_v1.1.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)

# ---------------- Dependency matrix (edge list) + gates
def dep_kind(t, d):
    dt = tasks[d]
    if d == "XC-FND-01": return "Decision gate (IDR ratification)"
    if d.startswith("XC-PLT-01"): return "Data gate (VER-22 record)"
    if d.startswith("XC-EXP"): return "Experiment evidence"
    if d.startswith("XC-STB"): return "Milestone stabilisation"
    if d.startswith("XC-"): return "Enabler / infrastructure"
    if t["id"].startswith("XC-STB"): return "Milestone stabilisation"
    if dt["fid"] == t["fid"]: return "Same function (implementation before UI/verification)"
    return "Functional dependency (FUNCTION_CATALOG depends_on)"

KCODE = {"Decision gate (IDR ratification)": "DEC", "Data gate (VER-22 record)": "DATA", "Experiment evidence": "EXPR",
         "Milestone stabilisation": "STAB", "Enabler / infrastructure": "ENAB", "Same function (implementation before UI/verification)": "SAME",
         "Functional dependency (FUNCTION_CATALOG depends_on)": "FUNC"}
drows = []
for n in sched_ids:
    t = tasks[n]
    for d in t["deps"]:
        dt = tasks[d]
        k = "REL" if d == "XC-REL-01" or n == "XC-REL-01" else KCODE[dep_kind(t, d)]
        drows.append({"task_id": n, "task_ms": t["ms"], "depends_on": d, "dep_ms": dt["ms"], "kind": k,
                      "critical": "Y" if (n in CPSET and d in CPSET) else ""})
with open(f"{OUT}/TASK_DEPENDENCY_MATRIX_v1.1.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(drows[0].keys())); w.writeheader(); w.writerows(drows)
# module-level matrix (row depends on column; cell = number of task edges)
mods = sorted({tasks[n]["mod"] for n in sched_ids})
mm = defaultdict(int)
for r_ in drows: mm[(tasks[r_["task_id"]]["mod"], tasks[r_["depends_on"]]["mod"])] += 1
with open(f"{OUT}/_module_matrix.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["module"] + mods)
    for a in mods: w.writerow([a] + [mm.get((a, b), "") for b in mods])

# ---------------- Stats for documents
st = {}
sch = [tasks[n] for n in sched_ids]
st["n_tasks_sched"] = len(sch)
st["n_tasks_total"] = len(tasks)
st["n_subtasks"] = sum(1 for r in rows if r["level"] == "Subtask")
st["n_edges"] = len(drows)
st["violations_fixed"] = viol
def sums(ts):
    return [round(sum(t["eff"][i] for t in ts), 1) for i in range(3)] + [round(sum(pert(*t["eff"]) for t in ts), 1)]
st["total"] = sums(sch)
st["by_scope"] = {s: sums([t for t in sch if t["scope"] == s]) for s in ("MVP-Core", "MVP-Should")}
st["by_ms"] = {m: sums([t for t in sch if t["ms"] == m]) for m in MS_LIST}
st["by_pool"] = {p: sums([t for t in sch if t["pool"] == p]) for p in ("KERNEL", "BACKEND", "FRONTEND", "QA_OPS", "EXT")}
st["by_epic"] = {e: sums([t for t in sch if EPIC_OF_MOD.get(t["mod"], "EP-12") == e]) for e in EPICS}
st["by_ms_pool"] = {m: {p: round(sum(t["eff"][1] for t in sch if t["ms"] == m and t["pool"] == p), 1) for p in ("KERNEL", "BACKEND", "FRONTEND", "QA_OPS", "EXT")} for m in MS_LIST}
st["n_by_ms"] = {m: sum(1 for t in sch if t["ms"] == m) for m in MS_LIST}
st["cp"] = [(n, tasks[n]["name"], tasks[n]["ms"], tasks[n]["eff"][1]) for n in cp]
st["cp_days"] = round(EF[end], 1)
st["pool_finish_ref"] = {p: round(max(results[REF][1][n] for n in sched_ids if tasks[n]["pool"] == p), 1) for p in ("KERNEL", "BACKEND", "FRONTEND", "QA_OPS", "EXT")}
st["sched_ml"] = {sc: round(max(results[sc][1].values()), 1) for sc in SCEN}
st["ms_finish_ml"] = {sc: {m: round(max(results[sc][1][n] for n in sched_ids if mnum(tasks[n]) == m), 1) for m in range(len(MS_LIST))} for sc in SCEN}
st["mc"] = MC
st["should_cut"] = [(f, FN[f]["name"], sums([t for t in sch if t["fid"] == f])[1]) for f in CUT_ORDER]
st["promoted"] = PROMOTED
st["next"] = [(f, FN[f]["name"]) for f in sorted(NEXT)]
st["deferred"] = [(f, FN[f]["name"]) for f in sorted(DEFERRED)]
st["scope_counts"] = {s: sum(1 for r in FUNCS if scope_of(r["function_id"]) == s) for s in ("MVP-Core", "MVP-Should", "Next (v1.1)", "Deferred")}
st["sprints_ref"] = defaultdict(list)
for n in sched_ids:
    st["sprints_ref"][tasks[n]["sprint"]].append(n)
st["sprints_ref"] = {k: v for k, v in sorted(st["sprints_ref"].items())}
st["sprint_ml"] = {k: round(sum(tasks[n]["eff"][1] for n in v), 1) for k, v in st["sprints_ref"].items()}
st["sprint_ms"] = {k: sorted(set(tasks[n]["ms"] for n in v)) for k, v in st["sprints_ref"].items()}
# requirement coverage
mvp_reqs = {k for k, v in rtm.items() if v["release"] == "MVP"}
covered = set()
for t in sch:
    for q in t["reqs"]:
        covered.add(q)
st["mvp_reqs"] = len(mvp_reqs); st["mvp_reqs_uncovered"] = sorted(mvp_reqs - covered)
st["unknown_reqs"] = sorted({q for t in tasks.values() for q in t["reqs"] if q not in rtm and not q.startswith("(")})
mvp_funcs = {r["function_id"] for r in FUNCS if scope_of(r["function_id"]) in ("MVP-Core", "MVP-Should")}
st["mvp_funcs"] = len(mvp_funcs)
st["mvp_funcs_without_task"] = sorted(f for f in mvp_funcs if not FTASKS.get(f))
subs_mvp = [s for s in fc if s["level"] == "Subfunction" and s["parent_function_id"] in mvp_funcs]
st["subs_mvp"] = len(subs_mvp)
st["subs_mapped"] = sum(1 for r in rows if r["level"] == "Subtask")
st["ext_tasks"] = [(t["id"], t["name"], t["gate"]) for t in sch if t["pool"] == "EXT" or t["status"].startswith("Gated")]
st["core_to_should_edges"] = CORE_TO_SHOULD
st["ms_window_ref"] = {m: (round(min(ref_st[n] for n in sched_ids if tasks[n]["ms"] == m), 1), round(max(ref_fi[n] for n in sched_ids if tasks[n]["ms"] == m), 1)) for m in MS_LIST}
st["sprint_top"] = {k: sorted([(tasks[n]["eff"][1], n, tasks[n]["name"]) for n in v], reverse=True)[:5] for k, v in st["sprints_ref"].items()}
st["drop_edges"] = {f"{a} -> {b}": v for (a, b), v in DROP_EDGES.items()}
st["all_EF"] = round(max(EF.values()), 1)
json.dump(st, open(f"{OUT}/_stats.json", "w"), indent=1, default=list)
print(json.dumps({k: st[k] for k in ("n_tasks_sched", "n_tasks_total", "n_subtasks", "n_edges", "total", "by_scope", "by_pool", "cp_days", "sched_ml", "mvp_reqs", "mvp_reqs_uncovered", "unknown_reqs", "mvp_funcs", "mvp_funcs_without_task", "subs_mvp", "subs_mapped", "scope_counts")}, indent=1, default=list))
print("violations fixed:", viol)
