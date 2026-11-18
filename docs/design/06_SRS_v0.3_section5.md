## 5. Requirements by capability (MVP release; generated from the RTM)

Post-MVP, research-only and TBD-release rows are in the RTM only.

#### ODC-00 (no capability assigned)

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| STK-07 | STK | Measurable added value vs incumbent CAD | Must | A → VER-10 | Both measures reported (VER-10, VER-23); thresholds recorded by the clinic before pilot end; result stated against each threshold |
| VER-10 | VER | Technician usability test | Must | D → — | Completion, critical errors (wrong side/case/unit = 0) and median end-to-end design time recorded for UC-02…UC-10; time compared with the clinic's current process on comparable cases against the clinic's threshold (DEC-030) |
| VER-14 | VER | Sign-convention test object | Must | T → — | Pass/fail on sphere phantom in all three outputs (UI control label, deviation map sign, manifest effect block); 0 mismatches |
| VER-15 | VER | Positive closure verification | Must | T → — | 100% of phantoms yield closed valid solids meeting FR-173 criteria |
| VER-16 | VER | Physical positive vs exported STL | Must | A → — | Record exists; production compares against its own limits (confidential) and records pass/fail |
| VER-20 | VER | Functional test coverage | Must | I → — | TC catalogue (09_TEST_CASE_CATALOGUE_v0.2.csv) lists ≥1 TC-<ID> for 100% of MVP FR/DATA/INT/SAF/SEC requirements; all pass before pilot release |
| VER-21 | VER | Security test suite | Must | T + I → — | Every listed SEC acceptance criterion executed and passed on the pilot configuration; every threat in the threat model maps to ≥1 passing test or to a recorded risk acceptance by a named approver |
| VER-22 | VER | Privacy controls inspection | Must | I → — | Signed inspection record lists each control as pass with evidence reference; any fail keeps real_patient_data_enabled false |
| VER-23 | VER | Agreement with manual measurements | Must | A → — | Report per index: n, bias, 95% limits of agreement, manual method and Jude definition; compared with the clinic's threshold |

#### ODC-01

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| STK-02 | STK | Case records for the clinic | Must | D → VER-20 | See UR-05 |
| UR-05 | UR | Find everything for a case | Must | D → VER-20 | See FR-004 |
| FR-001 | FR | Create case | Must | T → VER-20 | Case created with unique ID; data model inspection shows no direct-identifier fields; event in audit log |
| FR-002 | FR | Single-case ownership | Must | T → VER-20 | DB constraint rejects objects with zero or two case links; API test confirms |
| FR-003 | FR | Archive instead of delete | Must | T → VER-20 | No UI/API path removes a case object; archived object visible in archive view and not editable |
| FR-004 | FR | Case contents view | Must | T → VER-20 | For a seeded case with N objects, list shows exactly N rows with all four fields |
| FR-164 | FR | Prescription reference attachment | Must | T → VER-12, VER-20 | Approval of a version whose case has no attached prescription returns PRESCRIPTION_MISSING; downloaded file is byte-identical to the upload; each view/download creates one read event |
| FR-170 | FR | Scan-to-case confirmation | Must | T → VER-20 | Unconfirmed scan: landmark/measure/design API returns "case association not confirmed"; one log event per confirmation |
| DATA-10 | DATA | No direct identifiers in pilot | Must | I → VER-20 | Schema review finds none of the listed fields |
| SEC-12 | SEC | Consent reference before upload | Must | T → VER-22 | Upload to a case without consent reference returns CONSENT_REF_MISSING; consent reference change logged; scope values enumerated exactly as stated |
| SEC-18 | SEC | Scans treated as pseudonymised personal data | Must | I → VER-22 | Classification recorded in DR-2026-11-12; UI, docs and DATA-10 wording use "no direct identifiers", not "anonymised"; prescription files covered by SEC-13, SEC-15, SEC-16; VER-09 lint flag list includes "анонимизирован" |

#### ODC-02

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| STK-01 | STK | Single traceable design path for the technician | Must | D → VER-10 | See UR-01..UR-08 and VER-10 |
| UR-01 | UR | Design from scan to export | Must | D → VER-10 | In VER-10, each participating technician completes UC-02..UC-10 on an anonymised scan with no other 3D software opened |
| FR-010 | FR | Import mesh files | Must | T → VER-20, VER-08 | Reference files of each format (incl. ≥3 anonymised clinic exports) import with vertex/face counts equal to a reference parser |
| FR-015 | FR | Reject unreadable files | Must | T → VER-08 | Corrupt, empty and oversize test files each give a distinct reason; case object count unchanged |
| FR-181 | FR | Scan metadata lock after first measurement | Should | T → VER-20 | PUT metadata after first measurement returns METADATA_LOCKED; correction entry stored with reason and link |
| NFR-03 | NFR | Mesh size capacity | Must | T → VER-11 | Reference mesh of N triangles completes UC-02..UC-10 on min-spec client |
| DATA-01 | DATA | Scan record metadata | Should | I → VER-20 | Schema has all fields; 'unknown' stored explicitly, not empty |
| INT-01 | INT | STL import | Must | T → VER-20 | Reference files parse (FR-010) |
| INT-02 | INT | OBJ import | Must | T → VER-20 | Textured OBJ imports geometry; notice shown |
| INT-03 | INT | PLY import | Must | T → VER-20 | Reference PLY files parse |
| INT-08 | INT | Clinic export coverage | Must | T → VER-20 | ≥3 anonymised clinic files per format used import |
| SEC-07 | SEC | Untrusted upload handling | Must | T + I → VER-21 | Oversize, face-bomb and malformed fixtures are rejected with codes and no API crash; container inspection shows non-root, read-only FS, no egress route |

#### ODC-03

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| UR-08 | UR | Know scan problems before measuring | Must | D → VER-08 | See FR-013, FR-014 |
| FR-012 | FR | Unit confirmation | Must | T → VER-20 | With unit unconfirmed, landmark/measure/design controls are disabled (UI + API); confirmation logged with user/time |
| FR-013 | FR | Integrity report | Must | T → VER-08 | On VER-08 defect meshes, each seeded defect is reported with correct count |
| FR-014 | FR | Quality gate | Must | T → VER-08 | Gate logic with test-only thresholds: metric at T passes, at T+1 unit triggers the configured action; production thresholds are entered by the clinic technician in configuration (values confidential, not recorded in project documents); pilot start requires no NOT_SET gate value |
| FR-171 | FR | Input self-intersection count | Should | T → VER-08 | Seeded ghost-layer and self-intersecting meshes in VER-08 report count > 0; clean phantoms report 0 |
| FR-172 | FR | Post-frame coverage check | Should | T → VER-08 | Phantom with one sector removed is reported for that sector only; sector count and reference plane are clinic configuration values (confidential); pilot start requires them set |
| SAF-04 | SAF | Implausible dimension warning | Should | T → VER-20 | Mesh scaled ×10 triggers warning with configured range |
| SAF-05 | SAF | Logged override | Must | T → VER-13 | Override without reason refused; with reason logged |
| VER-08 | VER | Defect mesh catalogue | Must | T → — | 100% of seeded defects detected; 0 false failures on clean phantoms |

#### ODC-04

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| FR-020 | FR | Remove regions | Must | T → VER-20 | Removed face set recorded; re-application on original yields identical mesh hash |
| FR-021 | FR | Fill holes | Should | T → VER-08 | On VER-08 holed meshes, all loops ≤ set perimeter are closed and none larger |
| FR-022 | FR | Decimate | Should | T → VER-20 | Output triangle count within ±1% of target; displacement reported |
| FR-023 | FR | Non-destructive cleanup | Must | T → VER-07 | Disabling all cleanup ops reproduces original mesh hash |

#### ODC-05

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| FR-030 | FR | Place named landmarks | Must | T → VER-20 | Each landmark of the active set can be placed; stored coordinates lie on surface (distance < 1e-6 mm) |
| FR-031 | FR | Compute anatomical frame | Must | T → VER-01, VER-03 | On VER-01 phantoms with known landmarks, axes match analytic frame within VER-01 tolerance |
| FR-032 | FR | Frame confirmation gate | Must | T → VER-20 | Measurement/design API calls return 'frame not confirmed' before confirmation |
| FR-033 | FR | Store frame provenance | Must | T → VER-20 | Reloading case re-displays identical landmarks and frame |
| DATA-07 | DATA | Landmark/frame definition | Must | I → VER-20 | Schema contains every field listed in the statement with the stated type and NOT NULL where the statement does not allow absence; migration test on an empty database passes |
| SAF-03 | SAF | Laterality verification | Must | T → VER-03 | VER-03 asymmetric object: marked side remains on same side in display, measurements and exported STL |
| SAF-08 | SAF | Stale dependency blocking | Must | T → VER-20 | Move a landmark -> dependent design not approvable |
| VER-03 | VER | Laterality test object | Must | T → — | Test object with a one-sided feature on the patient-left side: feature shown on the side labelled L in the viewer, side-specific values computed on that side, and in the exported STL the feature centroid lies on the same side of the mid-sagittal plane; 0 mismatches across STL/OBJ/PLY inputs |

#### ODC-06

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| STK-03 | STK | Measurements comparable with the physician's method | Must | I → VER-04 | See FR-044, SAF-06 |
| UR-02 | UR | Know how each value was computed | Must | D → VER-20 | See FR-044 |
| FR-040 | FR | Compute cranial indices | Must | T → VER-01, VER-02 | Values on VER-01 phantoms within VER-01 tolerance for every definition variant |
| FR-041 | FR | Versioned measurement definitions | Must | T → VER-20 | Edit of a definition yields version n+1; values computed under n still reference n |
| FR-042 | FR | CVAI variants available | Must | T → VER-01 | Presets at 30° and 40° present in both denominator variants; computed values match analytic values on the VER-01 asymmetric phantom within the VER-01 tolerance; UI and API refuse a measurement set without an explicitly selected definition |
| FR-043 | FR | Value provenance | Must | T → VER-20 | Schema inspection + API test: no value record lacks any of the 7 fields |
| FR-044 | FR | Show definition with value | Must | I → VER-20 | UI inspection: every screen showing a value also shows its definition label |
| FR-045 | FR | No classification output | Must | I → VER-09 | String and UI review finds no severity terms or threshold logic; code search finds no threshold constants for indices |
| FR-046 | FR | Recompute creates new set | Must | T → VER-20 | After landmark move, two sets exist; earlier flagged superseded |
| FR-047 | FR | Show measurement plane | Must | D → VER-20 | Plane and diagonals displayed for each set; geometry matches stored parameters |
| FR-178 | FR | Show repeatability band or not-established text | Should | I → VER-20 | Before VER-05: text present on all value views; after: band value equals VER-05 result |
| NFR-09 | NFR | Display precision | Should | T → VER-20 | Stored value precision ≥ double; display follows config |
| DATA-02 | DATA | Measurement definition schema | Must | I → VER-20 | Schema contains every field listed in the statement with the stated type and NOT NULL where the statement does not allow absence; migration test on an empty database passes |
| DATA-03 | DATA | Measurement value record | Must | I → VER-20 | Schema contains every field listed in the statement with the stated type and NOT NULL where the statement does not allow absence; migration test on an empty database passes |
| SAF-06 | SAF | No definition-less values | Must | T → VER-20 | Automated scan of all outputs finds 0 values without definition |
| VER-01 | VER | Synthetic phantom suite | Must | T → — | DEC-025 option A on icosphere phantoms R = 75 mm, subdivision 6: point and displacement tolerance e = 0.011 mm, section perimeter 0.032 mm, frame axis atan(2e/b), index tolerance propagated (e.g. \|δCI\| ≤ 100·(e/L + W·e/L²)); all phantom cases within these limits; suite automated in CI |
| VER-02 | VER | Physical phantom check | Must | T → — | Procedure of VERIFICATION_CRITERIA_PROPOSALS §6 executed; differences compared with limits set by the clinic (confidential); clinic records pass/fail and signs the record |
| VER-04 | VER | Jude vs Rodin4D comparison | Should | A → — | Report with per-scan differences and definitions |

#### ODC-07

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| FR-050 | FR | Define correction zone | Must | T → VER-01, VER-08 | On a sphere phantom, a zone of magnitude m yields max signed displacement m ±(VER tolerance) at centre and 0 outside extent+transition |
| FR-054 | FR | Zone categories | Should | T → VER-20 | Zone cannot be saved without category; category appears in manifest (FR-103) |
| FR-055 | FR | No default correction | Must | T → VER-20 | New design: modification list length = 0 |
| FR-179 | FR | Optional positive smoothing | Should | T → VER-01 | Op stored with region and both parameters; vertices outside region + transition bit-identical to input; reported max/RMS deviation equals independent computation within VER-01 tolerance; measurement endpoints reject smoothed artifacts |
| FR-180 | FR | Zone overlap rule | Must | T → VER-08 | Saving overlapping zones returns ZONE_OVERLAP_NOT_ALLOWED naming both zones; non-overlapping zones save |
| DATA-08 | DATA | Zone record | Must | I → VER-20 | Schema contains every field listed in the statement with the stated type and NOT NULL where the statement does not allow absence; migration test on an empty database passes |
| SAF-02 | SAF | No system-proposed correction values | Must | I → VER-20 | Code and UI review: all correction fields default empty or from template |
| SAF-07 | SAF | Out-of-range magnitude confirmation | Should | T → VER-20 | Value beyond range prompts and logs; in-range does not |
| SAF-10 | SAF | Positive/device sign convention | Must | I + T → VER-14 | UI/manifest inspection shows both statements; VER-14 passes |

#### ODC-08

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| FR-051 | FR | Global adjustment | Must | T → VER-01 | On VER-01 phantom, +x mm A-P adjustment changes A-P length by x within tolerance |
| FR-177 | FR | Uniform normal offset | Should | T → VER-01 | Sphere radius r offset by +d gives radius r+d within VER-01 tolerance; new design has no offset op |

#### ODC-09

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| UR-03 | UR | Reproduce any past design | Must | T → VER-07 | See FR-052, FR-053 |
| FR-052 | FR | Parametric design regeneration | Must | T → VER-07 | 100 regenerations of 10 reference designs give 1 hash each |
| FR-053 | FR | Edit modification stack | Must | T → VER-07 | Disable+re-enable an op returns the prior geometry hash |
| FR-056 | FR | Save design version | Must | T → VER-20 | Saved version cannot be modified via UI/API; edits create version n+1 |
| DATA-04 | DATA | Design version record | Must | T → VER-20 | Schema contains every field listed in the statement with the stated type; migration test passes; an UPDATE on a saved version is rejected |
| SAF-09 | SAF | Failed regeneration keeps last valid state | Must | T → VER-08 | Injected failure leaves geometry hash unchanged |
| VER-07 | VER | Determinism test | Must | T → — | 100 regenerations of each of 10 reference designs give exactly 1 distinct geometry_sha per design on the CI host; second-host result recorded (ADR-010 fallback if different) |

#### ODC-10

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| UR-07 | UR | Reuse clinic correction settings | Should | D → VER-20 | See FR-060..FR-062 |
| FR-060 | FR | Save template | Should | T → VER-20 | Saved template lists the same operations and values as source design |
| FR-061 | FR | Apply template | Should | T → VER-20 | Design shows template ID+version; ops editable |
| FR-062 | FR | Template versioning | Should | T → VER-20 | After template edit, older design still references old version |

#### ODC-12

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| UR-06 | UR | See what the design changed | Must | D → VER-20 | See FR-070, FR-071 |
| FR-070 | FR | Deviation map | Must | T → VER-01 | On sphere phantom with zone m, reported max equals m within VER-01 tolerance; legend values match stored data |
| FR-071 | FR | Point query | Should | T → VER-20 | Picked value equals computed distance for that vertex/face |

#### ODC-16

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| FR-080 | FR | Geometry validity checks | Must | T → VER-08 | Each VER-08 defect type is detected; valid phantoms pass |
| FR-081 | FR | Validity failure blocks approval | Must | T → VER-08 | Approve control disabled and API returns reason for failing version |
| FR-082 | FR | Geometry-only wording | Must | I → VER-09 | Label present on validity panel and in report |
| FR-173 | FR | Positive closure and base | Must | T → VER-01, VER-08, VER-15 | Output passes FR-080; base plane at configured position within VER-01 tolerance; vertices above the base plane have zero displacement from closure |

#### ODC-17

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| UR-04 | UR | Approve a specific version | Must | D → VER-20 | See FR-090..FR-093 |
| FR-090 | FR | Approve design version | Must | T → VER-12, VER-20 | Admin role cannot approve (API 403); approval stores all 5 bindings and a test altering any one of them makes FR-101 refuse export; incomplete checklist blocks |
| FR-091 | FR | Approval does not carry over | Must | T → VER-20 | Edit after approval -> new version with status 'not approved'; old approval unchanged |
| FR-092 | FR | Reject with reason | Should | T → VER-20 | Rejected version shows reason, user, time |
| FR-093 | FR | Self-approval disclosure | Must | T → VER-20 | Self-approved test version shows statement in UI and report; independent approval does not |
| FR-101 | FR | Export only approved geometry | Must | T → VER-12 | Export of unapproved or hash-mismatched version refused via UI and API |
| FR-175 | FR | Latest-scan check at approval and export | Should | T → VER-20 | Two-scan case: approving a design on the older scan shows warning and logs confirmation; single-scan case shows none |
| FR-182 | FR | Prescription file bound to approval | Must | T → VER-12, VER-20 | Approval stores prescription SHA-256 equal to the attached file; report shows file name and date; API offers no "not available" option |
| DATA-05 | DATA | Approval record | Must | I → VER-20 | Schema contains every field listed in the statement with the stated type and NOT NULL where the statement does not allow absence; migration test on an empty database passes |
| VER-12 | VER | Permission and gate tests | Must | T → — | Every role × endpoint cell of the permission-matrix YAML returns the specified status (100% of cells executed); each approval/export gate error code of 07 §8.2 and FR-141/FR-182 is triggered by ≥1 test; the 5 approval bindings of FR-090 are each tamper-tested |

#### ODC-18

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| STK-04 | STK | Manufacturable hand-off | Must | T → VER-06 | See FR-100..FR-103 |
| FR-100 | FR | Export positive STL | Must | T → VER-06 | Exported STL bounding box (mm) equals in-app bbox within FR-102 tolerance |
| FR-102 | FR | Re-import verification | Must | T → VER-06 | Corrupted-write injection test marks export failed; normal exports pass with max deviation ≤ 1e-4 mm |
| FR-103 | FR | Export manifest | Must | T → VER-06 | Manifest validates against schema; STL hash in manifest equals file hash |
| DATA-06 | DATA | Export record | Must | I → VER-20 | Schema contains every field listed in the statement with the stated type and NOT NULL where the statement does not allow absence; migration test on an empty database passes |
| INT-04 | INT | Rodin4D Neo compatibility | Must | T → VER-06 | VER-06 pass on clinic installation (version recorded) |
| INT-05 | INT | Manifest format | Must | I → VER-20 | Published schema; sample validates |
| SEC-16 | SEC | Controlled export and download | Must | T → VER-12, VER-21 | Download of unreleased export returns EXPORT_NOT_RELEASED; blob of another case returns 403; file names match pattern J-xxxxxxxx_*; no endpoint returns more than one case's scans |
| VER-06 | VER | Export round-trip | Must | T → — | Jude re-import: triangle count equal and max vertex deviation ≤ FR-102 tolerance for 100% of suite exports; Rodin4D Neo: file opens without repair prompt and bounding box differs ≤ FR-102 tolerance; Neo version recorded |

#### ODC-19

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| UR-10 | UR | Produce a case report | Should | D → VER-20 | See FR-110, FR-111 |
| FR-110 | FR | Case report | Should | T → VER-20 | Automated compare: every value in report equals DB value to stored precision; definition ID present per value |
| FR-111 | FR | Report contains no interpretation | Must | I → VER-09 | Template review + VER-09 lint pass |
| INT-06 | INT | Report PDF | Should | T → VER-20 | PDF opens with correct Cyrillic text in two PDF readers |

#### ODC-20

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| FR-011 | FR | Retain original file | Must | T → VER-20 | Downloaded original is byte-identical to upload; hash shown in case view |
| FR-120 | FR | Event log | Must | T → VER-13 | Scripted run of each event type yields one log entry each with all fields |
| FR-121 | FR | Log immutability | Must | T → VER-12 | All mutate endpoints for log absent or return 403/405 |
| FR-122 | FR | View and export log | Should | T → VER-20 | Filtered export row count equals filtered view count |
| NFR-07 | NFR | Persistence after commit | Must | T → VER-20 | Kill browser 1 s after commit; reopen shows operation in 50/50 trials |
| NFR-08 | NFR | Time and version stamps | Must | T → VER-20 | DB timestamps UTC; display offset equals config; build version on exports and reports |
| DATA-09 | DATA | Audit event record | Must | I → VER-20 | Schema contains every field listed in the statement with the stated type and NOT NULL where the statement does not allow absence; migration test on an empty database passes |
| DATA-13 | DATA | Provenance class per value | Should | I → VER-20 | Schema contains provenance_class with the 6 enumerated values (plus DATA-21 reserved values) on every value table; insert without class is rejected by a NOT NULL constraint test |
| INT-07 | INT | Log CSV export | Should | T → VER-20 | CSV parses; Cyrillic preserved |
| SEC-03 | SEC | Tamper-evident log | Should | T → VER-13 | Altering one stored event is detected at that event |
| SEC-11 | SEC | Retention and erasure procedure | Must | T → VER-22 | On a test case: after erasure no file or row for the case is retrievable via API or DB; tombstone event present; backup purge record exists |
| SEC-14 | SEC | Incident and breach handling | Must | I → VER-22 | Incident procedure approved by product owner, consistent with the clinic contract; tabletop exercise record exists before pilot |
| SEC-15 | SEC | Read-access logging | Must | T → VER-13, VER-21 | Scripted session reading each object type yields one read event per access with all five fields; events are hash-chained |
| VER-13 | VER | Audit completeness test | Must | T → — | All event types present; chain verifies |

#### ODC-23

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| FR-140 | FR | Clinic configuration | Must | T → VER-20 | Each setting edit creates version n+1 and a log entry; objects record the config version used |
| FR-141 | FR | Versioned change of controlled configuration with re-approval | Must | T → VER-12 | Controlled change creates version n+1 with diff hash and audit event; approval record shows last-changed-by/at of the controlled configuration; export of a version approved under version n after a controlled change returns REAPPROVAL_REQUIRED; with the optional switch on, a self-approved controlled change stays inactive |
| DATA-11 | DATA | Configuration version reference | Must | T → VER-20 | Change config; new objects reference n+1, old keep n |

#### ODC-24

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| STK-06 | STK | Protection of infant data | Must | I → VER-22 | VER-22 inspection record signed; SEC-17 gate enabled only after it |
| FR-130 | FR | Two-role permission matrix | Must | T → VER-12 | Permission test matrix: every role × action pair returns the specified allow/deny |
| SEC-01 | SEC | Individual authentication | Must | T → VER-12 | No account type without a named person; every log entry has one user |
| SEC-02 | SEC | Server-side authorisation | Must | T → VER-12 | Direct API calls outside role return 403 for all matrix denies |
| SEC-04 | SEC | Encrypted transport | Must | T → VER-12 | TLS scan shows no protocol below 1.2 and no plaintext endpoint |
| SEC-05 | SEC | Password storage and login throttling | Must | T → VER-21 | DB inspection: password column holds argon2id encodings only; 5 failures within 15 min lock the account for 15 min and log auth.login_failed + account.locked; values read from config |
| SEC-06 | SEC | Session idle timeout | Must | T → VER-21 | Request after 31 min of inactivity returns 401; request after logout returns 401 |
| SEC-19 | SEC | Account lifecycle | Should | T → VER-21 | Deactivated user login returns 401; deactivation logged; quarterly account-review record exists |
| SEC-20 | SEC | CSRF protection | Must | T → VER-21 | Mutating request without or with wrong token returns 403 for 100% of mutating endpoints in the OpenAPI contract |

#### ODC-25

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| UR-09 | UR | Work in Russian | Must | I → VER-09 | See NFR-05 |
| NFR-01 | NFR | Supported browsers | Must | T → VER-11 | List published; VER-11 green on each entry |
| NFR-02 | NFR | Minimum client hardware | Must | T → VER-11 | Spec published; VER-11 passes on min-spec machine |
| NFR-04 | NFR | Interaction time budgets | Should | T → VER-11 | 95th percentile of 20 runs ≤ budget; budgets TBD from usability pilot |
| NFR-05 | NFR | Russian localisation | Must | I → VER-09 | Lint: zero hard-coded UI strings; Russian resource file covers every key |
| SEC-08 | SEC | Backup and restore | Must | T → VER-21 | Backup log shows daily DB and file-storage backups; restore test record: chain verification and SHA re-verification of all files pass; restore ≤ 24 h; data-loss window ≤ 24 h |
| SEC-09 | SEC | Dependency vulnerability management | Should | I → VER-21 | CI log shows scan per build; seeded vulnerable package fails the release job |
| SEC-10 | SEC | Data location (residency) | Must | I → VER-22 | Deployment record names the Supabase project, region and the storage of backups and logs, and cites DR-2026-11-12 |
| SEC-13 | SEC | Encryption at rest | Must | I → VER-22 | Deployment record cites the Supabase encryption statement for database, storage and backups; any self-managed backup target is encrypted |
| SEC-17 | SEC | Real-patient-data gate | Must | T → VER-22 | With flag false, upload returns REAL_DATA_DISABLED; enabling without decision record ID and VER-22 record ID is refused; enabling is logged |
| VER-11 | VER | Browser/hardware E2E suite | Must | T → — | Each UC-02…UC-10 E2E scenario completes with 0 failed steps on every browser in the NFR-01 list on a machine at NFR-02 minimum spec with the N-triangle reference mesh; p95 timings recorded against NFR-04 budgets |

#### ODC-26

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| DATA-14 | DATA | Secondary-use permission per scan | Should | T → VER-20 | New scan = not_permitted; technician cannot change level (403); change logged with consent ref; export filter test excludes lower levels |
| DATA-15 | DATA | Landmark placement trail | Should | T → VER-20 | Place, move twice: 3 history rows, final landmark equals last row; no UPDATE/DELETE on history table |
| DATA-16 | DATA | Cleanup label retention | Must | T → VER-07 | Re-applying stored face sets to original reproduces prepared-mesh hash after archive and restore |
| DATA-17 | DATA | Scan outcome tag | Should | T → VER-20 | Rescanned scan cannot be tagged without reason category and link; tag changes audited |
| DATA-18 | DATA | Cohort descriptors without identifiers | Could | I → VER-09 | Fields optional; no DOB field; referral field labelled as entered by user; VER-09 wording lint passes |
| DATA-19 | DATA | Effort data | Could | T → VER-13 | Scripted session: per-step durations computable from audit rows |
| DATA-21 | DATA | Reserved model provenance classes | Should | T → VER-20 | Enum contains values; test asserts zero MVP writes |
| DATA-22 | DATA | Structured reason categories | Should | T → VER-13 | Override/rejection without category refused; category in audit event |
| AI-10 | AI | Reserved AI audit event types | Should | I → VER-13 | Event catalogue contains names; no MVP code emits them |

#### ODC-28

| ID | Type | Title | Pri | Verification | Acceptance criteria |
|---|---|---|---|---|---|
| STK-05 | STK | Specialist-support intended use | Must | I → VER-09 | See SAF-01, SAF-02, FR-045, NFR-06 |
| NFR-06 | NFR | Wording rule | Must | I → VER-09 | VER-09 lint returns 0 hits on the in-scope file set; the exclusion file lists each excluded path with a reason |
| SAF-01 | SAF | Intended-use statement | Must | I → VER-09 | Statement present in 3 locations; text matches approved version |
| SAF-11 | SAF | Approval scope statement | Must | I → VER-09 | Statement present at approval and in report; text matches approved version |
| VER-09 | VER | Wording and localisation lint | Must | T → — | 0 hits blocks merge otherwise |
