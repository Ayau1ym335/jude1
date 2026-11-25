# Error catalogue `error/1`

This document describes the error catalogue of the API: which codes exist, which HTTP status each refusal returns, and how the catalogue is kept complete and stable (TSK-API-02-A; FN-API-02, IDR-05, TD-22, DS-24).

- **Catalogue:** [`src/jude_api/platform/error_catalogue.json`](src/jude_api/platform/error_catalogue.json).
- **Russian messages:** [`src/jude_api/platform/messages_ru.json`](src/jude_api/platform/messages_ru.json) (NFR-05).
- **CI check:** [`tools/contract/error_catalogue.py`](../../tools/contract/error_catalogue.py), run in the `contract` stage.

## Status

**Frozen 2026-11-25.** The engineering lead (the repository owner, Ayau1ym335) signed the catalogue off at the M0 exit, as IDR-05 requires. The sign-off covers:

- the HTTP statuses assigned by rule (R1, R2 below);
- the platform codes;
- the Russian messages.

`status` in `error_catalogue.json` now reads `frozen 2026-11-25 (…)`. From here on, the CI check also enforces stability against the base commit:
- no code is removed or renamed;
- no `http_status` or `kind` changes.

A new meaning gets a new code, and adding codes stays possible. A Russian message may still be reworded, because it is not part of a code's identity.

At the freeze the catalogue held 107 codes; the decisions recorded below are part of what was signed off.

## Contents: 107 codes

The codes come from two sources, plus platform codes and codes added by later tasks:

- **Every code used by any function of FUNCTION_TECHNICAL_SPECIFICATIONS_v1.0.** That is 95 codes, the completion criterion of the task.
- **Every code named by RTM v0.3 and v0.4** (IDR-05: RTM v0.3 names win). This adds `ZONE_CONTOUR_INVALID` (FR-183, RTM v0.4). The retired CN-11 names do not occur in the repository.
- **Six platform codes:**
  - `INTERNAL` (FN-API-02);
  - `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `REQUEST_INVALID`, introduced by XC-FND-11 for framework errors;
  - `IDEMPOTENCY_KEY_REUSED` and `IF_MATCH_REQUIRED`, introduced by TSK-API-01-A (see the decisions below).
- **Three job-result codes** of TSK-JOB-02-J: `JOB_HANDLER_ERROR`, `JOB_LEASE_EXPIRED`, `JOB_TYPE_UNKNOWN`.
- **Two codes of kernel tasks:** `EXTENSION_MISMATCH` (warning, TSK-KIO-01-K) and `TRANSFORM_NOT_RIGID` (kernel, TSK-KFR-03-K).

That is 95 + 1 + 6 + 3 + 2 = 107.

Each entry has a `kind`:

| kind | Count | How it reaches the user | `http_status` |
|---|---|---|---|
| `refusal` | 76 | Top-level DS-24 error of a refused request; `ApiError` accepts only these | 4xx/5xx |
| `kernel` | 15 | `reason_code` of a rejected op (OpResult, EH-KRN); shown in job results and as `gates[]` entries | none |
| `job` | 8 | Reason of a failed job (EH-JOB) | none |
| `measurement` | 3 | Reason of a `NOT_COMPUTED` measurement | none |
| `warning` | 4 | Non-blocking notice; the action proceeds | none |
| `startup` | 1 | The service refuses to start (`CONFIG_TEST_VALUE_IN_PROD`) | none |

Any catalogued code may appear in `gates[]`. For example, approval refused with `VALIDITY_FAILED` can list the kernel codes behind it.

## HTTP statuses

- **`FS`, 53 codes:** the status is stated in the specification, for example `409 GATE_BLOCKED` or `CATEGORY_REQUIRED (422)`.
- **R1 (state gate → 409), 16 codes.** The request is valid, but the object is not in a state that allows the action:
  - the frame, units or association are not confirmed;
  - the version is not saved or not a draft;
  - the approval, prescription or checklist is missing;
  - validity failed, or regeneration is pending or failed.

  The FS itself answers every comparable gate with 409 (`GATE_BLOCKED`, `EXPORT_NOT_RELEASED`, `LANDMARKS_INCOMPLETE`, `DEPENDENCY_SUPERSEDED`, `ZONE_OVERLAP_NOT_ALLOWED`, …).

  The 16 codes are `APPROVAL_HASH_MISMATCH`, `APPROVAL_REQUIRED`, `CHECKLIST_INCOMPLETE`, `COVERAGE_BLOCKED`, `FRAME_NOT_CONFIRMED`, `GATE_NOT_PASSED`, `MEASUREMENT_SET_INVALID`, `NOT_SAVED`, `PRESCRIPTION_MISSING`, `REAPPROVAL_REQUIRED`, `REGEN_FAILED`, `REGEN_PENDING`, `STALE_SOURCE_UNCONFIRMED`, `UNIT_NOT_CONFIRMED`, `VALIDITY_FAILED` and `VERSION_NOT_DRAFT`.
- **R2 (invalid input → 422), 1 code:** `ZONE_CONTOUR_INVALID`. A self-intersecting contour in the request is invalid input, like `PARAM_INVALID`.
- **`platform`, 6 codes:** 500, 404, 405, 422 (two codes) and 428.

## Which tokens are codes

The CI check treats every UPPER_SNAKE token in the FS and the RTM as a code. The only exceptions are the tokens listed in `NON_CODES`, each with its reason:

- document names, such as `TECHNICAL_DESIGN`;
- mathematical symbols, such as `F_S`;
- status values: `NOT_SET`, `NOT_COMPUTED` and `NOT_APPLICABLE`. These carry a reason code; they are not codes themselves.

A new token in either document fails CI until it is catalogued or added to `NON_CODES`. The check never guesses.

## Changing the catalogue

1. **Add the code** to `error_catalogue.json`, with `kind`, `http_status` (refusals only), `message_key = error.<code lower case>` and `sources`.
2. **Add the Russian message** to `messages_ru.json`. Messages are neutral and technical: they never assess the patient or the outcome (see CLAUDE.md, intended-use boundary).
3. **Raise it** with `raise ApiError("CODE", gates=[...])`. An unknown code, or a code that is not a refusal, raises at once.

## Points for sign-off

- **`CONTOUR_NOT_CLOSED` and `CONTOUR_AMBIGUOUS`.** FN-MEA-01 lists them under EH-API, but FN-KMS-02 defines them as reasons of a `NOT_COMPUTED` measurement. They are catalogued as `measurement`: the measurement call succeeds and returns the status with its reason. Make them refusals instead if the UI should get an error.
- **`FRAME_DEGENERATE` and `FRAME_INVALID`** are `job` codes, because FN-ANA-03 computes the frame in a job (EH-JOB). If frame computation becomes synchronous, they need statuses, and that is a new code or a pre-freeze edit.
- **`DUPLICATE_CLINIC_REF`, `LATERALITY_LABEL_MISMATCH` and `TARGET_NOT_REACHED`** are warnings. The FS says the action proceeds.

## Decisions taken (engineering, 2026-11-22)

The user delegated these non-clinical choices to engineering. They were signed off with the freeze on 2026-11-25.

- **`JOB_HANDLER_ERROR`, `JOB_LEASE_EXPIRED` and `JOB_TYPE_UNKNOWN` are kept as `job` codes** (TSK-JOB-02-J). FN-JOB-02 names only `JOB_RESOURCE_LIMIT`, but its algorithm has three more outcomes, each of which needs a code:
  - an infrastructure error after the last attempt;
  - a lease that expired with no attempts left;
  - a job type with no handler.

  They are job-result codes, not HTTP refusals.
- **Worker resource limits have no default in code** (SEC-07). `JUDE_JOB_CPU_SECONDS` and `JUDE_JOB_MEMORY_MB` are deployment settings, and the worker refuses to start without them. The memory limit is added on top of the worker's footprint at fork time, because numba and LLVM already occupy a large address space. `compose.yaml` holds development values only (600 s, 2 048 MB).
- **Account requests reuse `REQUEST_INVALID`** (TSK-IAM-05-B, 2026-11-24). An initial password shorter than 12 characters, or a login outside `[a-z0-9][a-z0-9._@-]{0,63}` after trimming and case-folding, answers 422 `REQUEST_INVALID` with the field as gate detail. No new code was added. FN-IAM-05's own codes (`NAME_REQUIRED`, `LOGIN_TAKEN`, `LAST_ADMIN`) keep their FS meaning.
- **Two codes added for FN-API-01** (TSK-API-01-A, 2026-11-24). FN-API-01 names `IDEMPOTENCY_KEY_REQUIRED` and `VERSION_CONFLICT`, but its algorithm has two more outcomes, and each needs a code:
  - **`IDEMPOTENCY_KEY_REUSED` (422):** the same key is sent with a different request (method, path or body). Replaying the stored response would answer a request the client did not make.
  - **`IF_MATCH_REQUIRED` (428):** a versioned resource is edited without `If-Match`. A missing version is not a stale version, so it is not `VERSION_CONFLICT`.
- **A malformed `Idempotency-Key` or `If-Match` gives `REQUEST_INVALID`** with the header as gate detail. Keys are UUID v4; the text is case-insensitive (RFC 9562) and stored in lower case.
- **`EXTENSION_MISMATCH` (kind `warning`, no HTTP status)** was added for FN-KIO-01 (TSK-KIO-01-K, 2026-11-25). The FS names the notice "extension mismatch" but gives no code. It is raised when the extension names another format family than the content (stl / obj / ply). It never changes the detected format and never refuses the file (FR-010).
- **`TRANSFORM_NOT_RIGID` (kind `kernel`)** was added for FN-KFR-03 (TSK-KFR-03-K, 2026-11-25). ALG-32 lists "scale ≠ 1" among the matrices the guard rejects, but only names `REFLECTION_REJECTED` (det < 0). A matrix with det > 0 that is not a rotation within the DS-06 tolerance 1e-9 (scale, shear) needs its own code; it is not a mirror.
