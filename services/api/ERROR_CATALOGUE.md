# Error catalogue `error/1`

This document describes the error catalogue of the API: which codes exist, which HTTP status each refusal returns, and how the catalogue is kept complete and stable (TSK-API-02-A; FN-API-02, IDR-05, TD-22, DS-24).

- **Catalogue:** [`src/jude_api/platform/error_catalogue.json`](src/jude_api/platform/error_catalogue.json).
- **Russian messages:** [`src/jude_api/platform/messages_ru.json`](src/jude_api/platform/messages_ru.json) (NFR-05).
- **CI check:** [`tools/contract/error_catalogue.py`](../../tools/contract/error_catalogue.py), run in the `contract` stage.

## Status

**Draft.** IDR-05 freezes the catalogue at the M0 exit after the engineering lead signs it off. Until then, codes may still be added or reworded. Sign-off covers:

- the HTTP statuses assigned by rule (R1, R2 below);
- the platform codes;
- the Russian messages.

From the moment `schema` is `error/1` on `main`, the CI check also enforces stability: no code is removed or renamed, and no `http_status` or `kind` changes. A new meaning gets a new code.

## Contents: 100 codes

The codes come from two sources, plus four platform codes:

- **Every code used by any function of FUNCTION_TECHNICAL_SPECIFICATIONS_v1.0.** That is 95 codes, the completion criterion of the task.
- **Every code named by RTM v0.3 and v0.4** (IDR-05: RTM v0.3 names win). This adds `ZONE_CONTOUR_INVALID` (FR-183, RTM v0.4). The retired CN-11 names do not occur in the repository.
- **Four platform codes:** `INTERNAL` (FN-API-02), and `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `REQUEST_INVALID` (introduced by XC-FND-11 for framework errors).

Each entry has a `kind`:

| kind | Count | How it reaches the user | `http_status` |
|---|---|---|---|
| `refusal` | 74 | Top-level DS-24 error of a refused request; `ApiError` accepts only these | 4xx/5xx |
| `kernel` | 14 | `reason_code` of a rejected op (OpResult, EH-KRN); shown in job results and as `gates[]` entries | none |
| `job` | 5 | Reason of a failed job (EH-JOB) | none |
| `measurement` | 3 | Reason of a `NOT_COMPUTED` measurement | none |
| `warning` | 3 | Non-blocking notice; the action proceeds | none |
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
- **`platform`, 4 codes:** 500, 404, 405 and 422.

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
