# Change Notice CN-2026-11-17 — CAD workspace parity with the clinic's current tool (Rodin4D)

| Field | Value |
|---|---|
| Document | CHANGE_NOTICE_CN-2026-11-17.md |
| Date | 2026-11-17 |
| Trigger | Photos of Rodin4D at Saigak Orto (a TLSO case, remote desktop session), shared by the product owner on 2026-11-17 |
| Decision | Product owner approved the change list CH-01…CH-16 on 2026-11-17 ("согласна"). Recorded as IDR-37 in IMPLEMENTATION_PLAN_v1.1 |
| Affects | MVP_SCOPE v1.1, IMPLEMENTATION_PLAN v1.1, WORK_BREAKDOWN_STRUCTURE v1.1, TASK_DEPENDENCY_MATRIX v1.1, DEVELOPMENT_ROADMAP v1.1, DEVELOPMENT_TEST_PLAN v1.1, DEVELOPMENT_RISK_REGISTER v1.1. REPOSITORY_STRUCTURE v1.0 and DEVELOPMENT_STANDARDS v1.0 are unchanged |
| To follow | RTM v0.4 (new rows FR-183…FR-193), FUNCTION_CATALOG v1.1 (11 new functions), ALGORITHM_CATALOG v1.1 (ALG-62, ALG-63) — task XC-FND-10 |
| Privacy | The photos show a patient's name and an X-ray. They are not stored in the project or repository; nothing patient-identifying is reproduced here |

## 1. Observations from the photos

| Rodin4D element | Behaviour | Status in plan v1.0 |
|---|---|---|
| Operation tree with enable checkboxes and signed values (Area −20 mm, Sym Area, Radius −12 mm, Complete Smoothing, Elongate 31 mm; ~19 ops in one design) | Parametric history | Present (FN-DES-02, IDR-01) |
| Area tool: free-form contour with control points on the surface; Insert/Delete point, Push contour/edge, Stretch | Zone of any shape | Missing — circle/ellipse only |
| Transition profile editor (plateau / peak / custom), overall amplitude, amplitude at vertex | Shaped fall-off | Missing — one fixed profile |
| Area filtering (Light) | Smoothing inside a zone | Missing |
| Sym Area | Mirrored zone | Missing (mirror was display-only, post-MVP) |
| Radius | Circumference change at a level | Present (FN-KOP-09) |
| Elongate: Total / 2 Levels, Height | Elongation between two levels | Partial (whole model only) |
| Complete Smoothing | Whole-surface smoothing | Excluded by DEC-028 (local only) |
| Live panel H / AP (anterior, posterior) / ML / Cir / Vol with deltas mm and % | Metrics during design | Missing |
| 2D transverse section and silhouette, original vs modified | 2D comparison | Missing |
| Original overlay with opacity, modified regions highlighted | Visual control during design | Review only (M5) |
| View cube, Shift / Balance / Twist, Tape measure, X-ray underlay | Viewing, orientation, ad-hoc measurement, reference image | Missing |
| Rodin4D used through Chrome Remote Desktop from a laptop on battery; patient name in window title and file name; patient queue on paper | Clinic environment | Not reflected in benchmarks |

Not transferable to cranial helmets: Bend, Extrusion, Toe Box, Prosthesis Measurements (limb/TLSO tools).

## 2. Changes

| ID | Change | Scope | New / changed items | Requirement | Task IDs (WBS v1.1) | ML pd |
|---|---|---|---|---|---|---|
| CH-01 | Free-form zone contour on the surface (control points, insert/delete/move, push contour/edge, stretch); circle/ellipse kept as presets | MVP-Core | New FN-KOP-14; new ALG-62 | FR-183 | TSK-KOP-14-K/-V/-U | 20.0 |
| CH-02 | Parametric transition profile (plateau, peak, custom), overall amplitude, amplitude at vertex | MVP-Core | New FN-KOP-15; new ALG-63; IDR-20 revised | FR-184 | TSK-KOP-15-K/-V/-U | 8.5 |
| CH-03 | Live design metrics at a movable level with deltas vs prepared scan (AP split, ML, circumference, volume; CI/CVA/CVAI where defined) | MVP-Core | New FN-DES-08 | FR-186 | TSK-DES-08-B/-U | 10.0 |
| CH-04 | Original/modified overlay with opacity and highlight in the workspace | MVP-Core | New FN-UIX-07; FN-KCP-01/02 and FN-UIX-04 moved from M5 to M4b | FR-187 | TSK-UIX-07-B/-U | 4.0 |
| CH-05 | Symmetric zone linked across the mid-sagittal plane | MVP-Core | New FN-KOP-16 | FR-185 | TSK-KOP-16-K/-V/-U | 7.5 |
| CH-06 | 2D section comparison views | MVP-Should | New FN-UIX-08 | FR-188 | TSK-UIX-08-B/-U | 6.5 |
| CH-07 | Elongation between two levels | MVP-Should | New FN-KOP-17 | FR-189 | TSK-KOP-17-K/-V | 3.0 |
| CH-08 | In-zone filtering | MVP-Should | New FN-KOP-18 | FR-190 | TSK-KOP-18-K/-V | 3.0 |
| CH-09 | Tape measure | MVP-Should | New FN-MEA-05 | FR-191 | TSK-MEA-05-B/-U | 3.5 |
| CH-10 | Manual orientation fine-tuning (shift/tilt/twist), recorded | MVP-Should | New FN-ANA-06 | FR-192 | TSK-ANA-06-B/-U | 4.0 |
| CH-11 | View cube / standard views | MVP-Should | New FN-UIX-09 | FR-193 | TSK-UIX-09-U | 1.0 |
| CH-12 | Whole-surface smoothing mode as an explicit recorded op (closure faces excluded, deviation report, no default parameters) | MVP-Should — **OD-09 closed by IDR-38** (DEC-028 amended) | FN-KOP-12 extension | FR-179 | TSK-KOP-12-KG | 2.0 |
| CH-13 | Reference image underlay | Next (v1.1) | New FN-PMV-13 (outline) | — | TSK-PMV-13-X | — |
| CH-14 | Benchmarks on real technician devices and the remote-desktop/network setup | Process | XC-PLT-02, XC-EXP-BM04 descriptions | NFR-01/02 | — | 0 |
| CH-15 | ~20-operation reference history as benchmark/golden design | Process | XC-EXP-04 (now M4a), T9 | NFR-04, VER-07 | — | 0 |
| CH-16 | Observation of a modelling session at the clinic | **Done 2026-11-17** (source of the photos; the case observed was a TLSO — helmet-specific tool use to be confirmed informally at the next clinic contact, non-blocking) | XC-PLT-13 recorded as done | UR-01, STK-07 | XC-PLT-13 | 2.0 (spent) |

New algorithms to add to ALGORITHM_CATALOG v1.1:
- **ALG-62 Surface contour region:** closed polyline of anchors (face_id, bary) on the positive; edges traced as plane-section paths between consecutive anchors; simplicity tested with exact predicates in a local projection; membership = vertices enclosed (winding in the local chart) plus Euclidean distance to the contour for the transition band; resolved on the full-resolution mesh.
- **ALG-63 Parametric transition profile:** w(u) on u ∈ [0, 1] across the transition; presets plateau (smoothstep) and peak (cosine), custom = monotone cubic Hermite (Fritsch–Carlson) through technician points; amplitude at vertex = m·w at the contour vertex; C¹ for presets; no overshoot by construction.

## 3. Impact

| Metric | Plan v1.0 | Plan v1.1 | Change |
|---|---|---|---|
| MVP functions (Core / Should) | 127 / 19 | 132 / 25 | +5 / +6 |
| MVP requirements covered | 174 | 185 (incl. 11 proposed) | +11 |
| Scheduled tasks / dependency edges | 310 / 1,268 | 338 / 1,391 | +28 / +123 |
| Effort ML (PERT) | 677.8 (715.0) pd | 757.7 (798.2) pd | +79.9 (+11.8 %) |
| Effort Monte Carlo P50 / P80 | 812 / 900 pd | 915 / 1,009 pd | +103 / +109 |
| S2 duration plan / P50 / P80 | 376 / 442 / 498 WD | 413 / 492 / 546 WD | +37 / +50 / +48 WD |
| S3 duration plan / P50 / P80 | 280 / 340 / 375 WD | 324 / 385 / 431 WD | +44 / +45 / +56 WD |
| Milestones | M0…M7 | M0, M1, M2, M3, **M4a** (zones, profiles, ops), **M4b** (live metrics, overlay, sections), M5, M6, M7 | M4 split |

## 4. Decisions changed or opened

| ID | Change |
|---|---|
| IDR-20 | Zone profile no longer fixed to plateau + smoothstep: profile is a parameter (FN-KOP-15); plateau + smoothstep remains the default preset |
| ALG-42 | Mirroring enters MVP as a design operation (FN-KOP-16, mirrored zone parameters only — never a reflection of stored geometry; SAF-03 holds) |
| IDR-37 (new) | Adopt CN-2026-11-17 (this notice) |
| IDR-38 (new) | Closes OD-09: DEC-028 amended — whole-surface smoothing allowed as an explicit, recorded, replayable op (smooth.windowed_sinc with region = whole scan-origin surface); local smoothing stays the primary tool; no default iteration/pass-band values; closure (wall/cap) faces excluded; max/RMS deviation reported and shown before saving; measurements refuse smoothed artifacts (FR-179) |
