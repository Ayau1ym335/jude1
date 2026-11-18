# Function Technical Specifications v1.0 — Jude CRO/CRH design software

| Field | Value |
|---|---|
| Document | FUNCTION_TECHNICAL_SPECIFICATIONS_v1.0.md |
| Date | 2026-11-15 |
| Status | Draft v1.0 for review — engineering proposal. **Not approved**; no decision in this set is final until signed by the engineering lead (ADR/TD status "Proposed"). |
| Scope | All 226 rows of FUNCTION_CATALOG_v1.0 (159 functions + 67 subfunctions) — none skipped |
| Sources | FUNCTIONAL_SPECIFICATION_v1.0 (function fields reused verbatim where they exist), RTM v0.3, TC catalogue v0.3, ALGORITHM_CATALOG_v1.0, LIBRARY_COMPARISON_v1.0, DATA_STRUCTURES_AND_INTERFACES_v1.0, TECHNICAL_DECISIONS_v1.0 |
| Conventions | Subfunction fields marked "Inherited from FN-…" are identical to the parent and intentionally not repeated. "TBD" = value not set by an approved decision; methodology in PERFORMANCE_REQUIREMENTS_v1.0. Library statuses: R-MVP recommended, CAND candidate (experiment decides), ORACLE/DEV not shipped, RESERVE post-MVP, REJECT not used. No status here is an approval. |
| Boundary | Geometric/software correctness only; no clinical rule, threshold or correction is defined (STK-05, FR-045, FR-082). |

## SS-01 — Platform, identity, audit and configuration

### Module IAM — Identity and access

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Security and Audit Layer / Application Layer; UI Layer |
| Runtime and execution | C3 API process (request thread); C1 browser for screens · Synchronous request |
| Input data structures | HTTP request, session cookie, CSRF token; governance.user/session/role_grant rows |
| Output data structures | Session row; DS-24 errors; DS-18 audit events |
| Interfaces | IF-01; IF-08; IF-09 |
| External libraries | LIB-FASTAPI; LIB-POSTGRES; argon2-cffi 25.1.0 (MIT, PyPI 2026-11-15) |
| Performance | PM-13, PM-14 (approved values); login latency TBD; argon2id parameters to be calibrated so that one verify ≤ TBD ms on the API host (BM-05) |
| Security | Deny by default; constant-time compare; dummy hash verify for unknown users (no user enumeration); cookies httpOnly+Secure+SameSite=Strict; CSRF double-submit (SEC-20); lockout/idle values from SD-01/SD-02; no tokens in logs |
| Integration tests | API tests against the permission matrix (VER-12) for every route × role; session expiry with frozen clock; lockout across concurrent requests; audit events present |
| Alternatives | Supabase Auth (JWT) verified in FastAPI (TQ-04); external IdP post-MVP (ADR-014) |
| Versioning | Permission table version; session schema migration |

#### FN-IAM-01 — Authenticate user

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-IAM-01 |
| Function Name | Authenticate user |
| Related Requirement IDs | SEC-01; SEC-04; SEC-05; SEC-19; SEC-20 |
| Architecture Component | C3/M01, C1/W01 · Security and Audit Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Establish an individual, attributable session for a named person. Login form (W01) posts credentials; M01 verifies the argon2id hash, applies the lockout rule, creates a server-side session and returns an httpOnly session cookie plus an anti-CSRF token. |
| Input Data | login (string), password (string), client IP (from proxy header) · Preconditions: Account exists and is active (FN-IAM-05). TLS endpoint (SEC-04). |
| Input Data Structures | POST /auth/login, JSON {login: string ≤ 254, password: string ≤ 1024} · module baseline DS |
| Processing Algorithm | 1. Normalise login (trim, case-fold).<br>2. Load account; if absent, run a dummy argon2id verify (constant-time behaviour) and return BAD_CREDENTIALS.<br>3. If account.locked_until > now_utc → return ACCOUNT_LOCKED (do not verify password).<br>4. Verify password against stored argon2id encoding.<br>5. On failure: insert failure row; count failures for this account within the last W_fail = 15 min (security config SD-01); if count ≥ L_fail = 5 → set locked_until = now + 15 min and emit account.locked; emit auth.login_failed.<br>6. On success: clear failure counter; create session row {id (256-bit random), user_id, created_at, last_seen_at}; issue CSRF token (256-bit random, bound to session); emit auth.login.<br>7. Return 200 with Set-Cookie (httpOnly, Secure, SameSite=Strict) and {csrf_token, user, role}. |
| Mathematical Model | Lock condition: \|{failures f : now − f.at ≤ W_fail}\| ≥ L_fail. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Session; CSRF token; audit events auth.login / auth.login_failed / account.locked. |
| Output Data Structures | HTTP 200 JSON {user:{id, display_name, role}, csrf_token}; cookie jude_session. · module baseline DS |
| Error Handling | Wrong credentials → 401 BAD_CREDENTIALS (same message for unknown login).<br>Locked → 423 ACCOUNT_LOCKED with unlock time (UTC).<br>Deactivated account → 401 BAD_CREDENTIALS + audit auth.login_failed(reason=deactivated).<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-AUD-01 · Technical decisions: TD-14, TD-26 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Supabase Auth (JWT) verified in FastAPI (TQ-04); external IdP post-MVP (ADR-014) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-SEC-01; TC-SEC-04; TC-SEC-05; TC-SEC-19; TC-SEC-20 · suites: VER-12, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-IAM-01 (proposed id)<br>Acceptance criteria as unit/component assertions: 5 failures within 15 min lock the account for 15 min; 6th attempt with correct password returns ACCOUNT_LOCKED.<br>Password column contains only argon2id encodings (DB inspection).<br>Every attempt produces exactly one audit event.<br>One negative test per error code: ACCOUNT_LOCKED, BAD_CREDENTIALS<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SEC-01; TC-SEC-04; TC-SEC-05; TC-SEC-19; TC-SEC-20 |
| Open Technical Questions | TQ-04 |

##### FN-IAM-01.1 — Verify credential

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-IAM-01.1 |
| Function Name | Verify credential  (subfunction of FN-IAM-01 Authenticate user) |
| Related Requirement IDs | Inherited from parent FN-IAM-01: SEC-01; SEC-04; SEC-05; SEC-19; SEC-20 |
| Architecture Component | C3/M01, C1/W01 · Security and Audit Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | argon2id verify; dummy verify for unknown login. |
| Input Data | Inherited from FN-IAM-01 |
| Input Data Structures | Inherited from FN-IAM-01 (HTTP request, session cookie, CSRF token; governance.user/session/role_grant rows) |
| Processing Algorithm | argon2id verify; dummy verify for unknown login. |
| Mathematical Model | Inherited from FN-IAM-01 |
| Geometry Operations | Inherited from FN-IAM-01 |
| Output Data | Inherited from FN-IAM-01 |
| Output Data Structures | Inherited from FN-IAM-01 |
| Error Handling | Inherited from FN-IAM-01 |
| Performance Requirements | Inherited from FN-IAM-01 |
| Dependencies | Inherited from FN-IAM-01 |
| External Libraries | Inherited from FN-IAM-01 |
| Alternative Implementations | Inherited from FN-IAM-01 |
| Security Considerations | Inherited from FN-IAM-01 |
| Verification Strategy | T — verified within FN-IAM-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-IAM-01.1 (proposed id)<br>Isolated test of this step with positive and negative cases: argon2id verify; dummy verify for unknown login. |
| Integration Test Requirements | Inherited from FN-IAM-01 |
| Open Technical Questions | TQ-04 |

##### FN-IAM-01.2 — Apply lockout rule

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-IAM-01.2 |
| Function Name | Apply lockout rule  (subfunction of FN-IAM-01 Authenticate user) |
| Related Requirement IDs | Inherited from parent FN-IAM-01: SEC-01; SEC-04; SEC-05; SEC-19; SEC-20 |
| Architecture Component | C3/M01, C1/W01 · Security and Audit Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Sliding 15-min window, 5 failures, 15-min lock (SD-01). |
| Input Data | Inherited from FN-IAM-01 |
| Input Data Structures | Inherited from FN-IAM-01 (HTTP request, session cookie, CSRF token; governance.user/session/role_grant rows) |
| Processing Algorithm | Sliding 15-min window, 5 failures, 15-min lock (SD-01). |
| Mathematical Model | Inherited from FN-IAM-01 |
| Geometry Operations | Inherited from FN-IAM-01 |
| Output Data | Inherited from FN-IAM-01 |
| Output Data Structures | Inherited from FN-IAM-01 |
| Error Handling | Inherited from FN-IAM-01 |
| Performance Requirements | Inherited from FN-IAM-01 |
| Dependencies | Inherited from FN-IAM-01 |
| External Libraries | Inherited from FN-IAM-01 |
| Alternative Implementations | Inherited from FN-IAM-01 |
| Security Considerations | Inherited from FN-IAM-01 |
| Verification Strategy | T — verified within FN-IAM-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-IAM-01.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Sliding 15-min window, 5 failures, 15-min lock (SD-01). |
| Integration Test Requirements | Inherited from FN-IAM-01 |
| Open Technical Questions | TQ-04 |

##### FN-IAM-01.3 — Issue session and CSRF token

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-IAM-01.3 |
| Function Name | Issue session and CSRF token  (subfunction of FN-IAM-01 Authenticate user) |
| Related Requirement IDs | Inherited from parent FN-IAM-01: SEC-01; SEC-04; SEC-05; SEC-19; SEC-20 |
| Architecture Component | C3/M01, C1/W01 · Security and Audit Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Server-side session row; token bound to session. |
| Input Data | Inherited from FN-IAM-01 |
| Input Data Structures | Inherited from FN-IAM-01 (HTTP request, session cookie, CSRF token; governance.user/session/role_grant rows) |
| Processing Algorithm | Server-side session row; token bound to session. |
| Mathematical Model | Inherited from FN-IAM-01 |
| Geometry Operations | Inherited from FN-IAM-01 |
| Output Data | Inherited from FN-IAM-01 |
| Output Data Structures | Inherited from FN-IAM-01 |
| Error Handling | Inherited from FN-IAM-01 |
| Performance Requirements | Inherited from FN-IAM-01 |
| Dependencies | Inherited from FN-IAM-01 |
| External Libraries | Inherited from FN-IAM-01 |
| Alternative Implementations | Inherited from FN-IAM-01 |
| Security Considerations | Inherited from FN-IAM-01 |
| Verification Strategy | T — verified within FN-IAM-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-IAM-01.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Server-side session row; token bound to session. |
| Integration Test Requirements | Inherited from FN-IAM-01 |
| Open Technical Questions | TQ-04 |

#### FN-IAM-02 — Validate session and enforce idle timeout

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-IAM-02 |
| Function Name | Validate session and enforce idle timeout |
| Related Requirement IDs | SEC-06; SEC-20; SEC-19; DATA-19 |
| Architecture Component | C3/M01, C1/W01 · Security and Audit Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Reject requests from expired, logged-out or unknown sessions. Request middleware executed before every authenticated endpoint. |
| Input Data | Session cookie; CSRF header X-CSRF-Token for mutating methods · Preconditions: Request carries jude_session cookie. |
| Input Data Structures | HTTP headers · module baseline DS |
| Processing Algorithm | 1. Look up session by id; absent → 401 SESSION_INVALID.<br>2. If now_utc − last_seen_at > T_idle = 30 min (SD-02) → delete session, 401 SESSION_EXPIRED.<br>3. If user deactivated → delete session, 401 SESSION_INVALID.<br>4. For POST/PUT/PATCH/DELETE: compare X-CSRF-Token with session token (constant time); mismatch → 403 CSRF_INVALID.<br>5. Update last_seen_at (at most once per 60 s to limit writes).<br>6. Attach {user_id, role, session_id, ui_session_id} to request context (ui_session_id used by DATA-19). |
| Mathematical Model | Expired ⇔ now − last_seen_at > 1800 s. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Authenticated request context or error. |
| Output Data Structures | Internal context object; HTTP 401/403 on failure. · module baseline DS |
| Error Handling | Expired → 401 SESSION_EXPIRED.<br>Missing/wrong CSRF token → 403 CSRF_INVALID.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-IAM-01 · Technical decisions: TD-14 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Supabase Auth (JWT) verified in FastAPI (TQ-04); external IdP post-MVP (ADR-014) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-19; TC-SEC-06; TC-SEC-19; TC-SEC-20 · suites: VER-13, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-IAM-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Request after 31 min inactivity → 401.<br>Mutating request without/with wrong token → 403 on 100% of mutating endpoints.<br>One negative test per error code: CSRF_INVALID, SESSION_EXPIRED<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-19; TC-SEC-06; TC-SEC-19; TC-SEC-20 |
| Open Technical Questions | TQ-04 |

#### FN-IAM-03 — Log out

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-IAM-03 |
| Function Name | Log out |
| Related Requirement IDs | SEC-06 |
| Architecture Component | C3/M01, C1/W01 · Security and Audit Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | End a session on user request. Deletes the server-side session and clears the cookie. |
| Input Data | Session cookie · Preconditions: Valid session. |
| Input Data Structures | POST /auth/logout · module baseline DS |
| Processing Algorithm | 1. Delete session row.<br>2. Emit auth.logout.<br>3. Return 204 with expired cookie. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Session removed. |
| Output Data Structures | HTTP 204 · module baseline DS |
| Error Handling | Unknown session → 204 (idempotent).<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-IAM-02; FN-AUD-01 · Technical decisions: TD-14 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Supabase Auth (JWT) verified in FastAPI (TQ-04); external IdP post-MVP (ADR-014) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-SEC-06 · suites: VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-IAM-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Request with the old cookie after logout → 401.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SEC-06 |
| Open Technical Questions | TQ-04 |

#### FN-IAM-04 — Authorise request (permission matrix + case scope)

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-IAM-04 |
| Function Name | Authorise request (permission matrix + case scope) |
| Related Requirement IDs | FR-130; SEC-02; FR-002; FR-003 |
| Architecture Component | C3/M01, C1/W01 · Security and Audit Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Enforce role permissions and case scoping on the server for every call. A single YAML permission table (role × action → allow/deny) drives FastAPI route dependencies and generates the VER-12 test matrix. |
| Input Data | role, action key of the route, target case_id (if any) · Preconditions: Authenticated request context (FN-IAM-02). |
| Input Data Structures | permissions.yaml: {action: {technician: allow\|deny, clinic_admin: allow\|deny}} · module baseline DS |
| Processing Algorithm | 1. Resolve action key declared on the route; routes without a key fail application start-up (deny by default).<br>2. Look up role × action; deny → 403 ROLE_FORBIDDEN + audit authz.denied.<br>3. If the route targets a case-scoped object, resolve its case_id via FR-002 link; object of an archived case is read-only for mutating actions → 409 CASE_ARCHIVED.<br>4. Pass. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Allow / deny decision. |
| Output Data Structures | HTTP 403 ROLE_FORBIDDEN on deny · module baseline DS |
| Error Handling | Unknown action key at start-up → process refuses to start (configuration error).<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-IAM-02 · Technical decisions: TD-14 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Supabase Auth (JWT) verified in FastAPI (TQ-04); external IdP post-MVP (ADR-014) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-002; TC-FR-003; TC-FR-130; TC-SEC-02 · suites: VER-12, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-IAM-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Generated role × action matrix test passes for 100% of cells.<br>Clinic admin approve/export calls → 403.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-002; TC-FR-003; TC-FR-130; TC-SEC-02 |
| Open Technical Questions | TQ-04 |

##### FN-IAM-04.1 — Load and validate permission table

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-IAM-04.1 |
| Function Name | Load and validate permission table  (subfunction of FN-IAM-04 Authorise request (permission matrix + case scope)) |
| Related Requirement IDs | Inherited from parent FN-IAM-04: FR-130; SEC-02; FR-002; FR-003 |
| Architecture Component | C3/M01, C1/W01 · Security and Audit Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Schema check at start-up; every route declares an action. |
| Input Data | Inherited from FN-IAM-04 |
| Input Data Structures | Inherited from FN-IAM-04 (HTTP request, session cookie, CSRF token; governance.user/session/role_grant rows) |
| Processing Algorithm | Schema check at start-up; every route declares an action. |
| Mathematical Model | Inherited from FN-IAM-04 |
| Geometry Operations | Inherited from FN-IAM-04 |
| Output Data | Inherited from FN-IAM-04 |
| Output Data Structures | Inherited from FN-IAM-04 |
| Error Handling | Inherited from FN-IAM-04 |
| Performance Requirements | Inherited from FN-IAM-04 |
| Dependencies | Inherited from FN-IAM-04 |
| External Libraries | Inherited from FN-IAM-04 |
| Alternative Implementations | Inherited from FN-IAM-04 |
| Security Considerations | Inherited from FN-IAM-04 |
| Verification Strategy | T — verified within FN-IAM-04 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-IAM-04.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Schema check at start-up; every route declares an action. |
| Integration Test Requirements | Inherited from FN-IAM-04 |
| Open Technical Questions | TQ-04 |

##### FN-IAM-04.2 — Role check

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-IAM-04.2 |
| Function Name | Role check  (subfunction of FN-IAM-04 Authorise request (permission matrix + case scope)) |
| Related Requirement IDs | Inherited from parent FN-IAM-04: FR-130; SEC-02; FR-002; FR-003 |
| Architecture Component | C3/M01, C1/W01 · Security and Audit Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Deny by default. |
| Input Data | Inherited from FN-IAM-04 |
| Input Data Structures | Inherited from FN-IAM-04 (HTTP request, session cookie, CSRF token; governance.user/session/role_grant rows) |
| Processing Algorithm | Deny by default. |
| Mathematical Model | Inherited from FN-IAM-04 |
| Geometry Operations | Inherited from FN-IAM-04 |
| Output Data | Inherited from FN-IAM-04 |
| Output Data Structures | Inherited from FN-IAM-04 |
| Error Handling | Inherited from FN-IAM-04 |
| Performance Requirements | Inherited from FN-IAM-04 |
| Dependencies | Inherited from FN-IAM-04 |
| External Libraries | Inherited from FN-IAM-04 |
| Alternative Implementations | Inherited from FN-IAM-04 |
| Security Considerations | Inherited from FN-IAM-04 |
| Verification Strategy | T — verified within FN-IAM-04 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-IAM-04.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Deny by default. |
| Integration Test Requirements | Inherited from FN-IAM-04 |
| Open Technical Questions | TQ-04 |

##### FN-IAM-04.3 — Case-scope check

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-IAM-04.3 |
| Function Name | Case-scope check  (subfunction of FN-IAM-04 Authorise request (permission matrix + case scope)) |
| Related Requirement IDs | Inherited from parent FN-IAM-04: FR-130; SEC-02; FR-002; FR-003 |
| Architecture Component | C3/M01, C1/W01 · Security and Audit Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Object → case → user may access (single-clinic MVP: all active users). |
| Input Data | Inherited from FN-IAM-04 |
| Input Data Structures | Inherited from FN-IAM-04 (HTTP request, session cookie, CSRF token; governance.user/session/role_grant rows) |
| Processing Algorithm | Object → case → user may access (single-clinic MVP: all active users). |
| Mathematical Model | Inherited from FN-IAM-04 |
| Geometry Operations | Inherited from FN-IAM-04 |
| Output Data | Inherited from FN-IAM-04 |
| Output Data Structures | Inherited from FN-IAM-04 |
| Error Handling | Inherited from FN-IAM-04 |
| Performance Requirements | Inherited from FN-IAM-04 |
| Dependencies | Inherited from FN-IAM-04 |
| External Libraries | Inherited from FN-IAM-04 |
| Alternative Implementations | Inherited from FN-IAM-04 |
| Security Considerations | Inherited from FN-IAM-04 |
| Verification Strategy | T — verified within FN-IAM-04 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-IAM-04.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Object → case → user may access (single-clinic MVP: all active users). |
| Integration Test Requirements | Inherited from FN-IAM-04 |
| Open Technical Questions | TQ-04 |

#### FN-IAM-05 — Manage user accounts

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-IAM-05 |
| Function Name | Manage user accounts |
| Related Requirement IDs | SEC-01; SEC-19; FR-130 |
| Architecture Component | C3/M01, C1/W01 · Security and Audit Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Create named individual accounts, assign one role, deactivate accounts. Admin screen W07. No account type without a named person; no delete, only deactivate (SEC-19). |
| Input Data | display_name, login, role ∈ {technician, clinic_admin}, initial password (or set-password link token), active flag · Preconditions: Caller is clinic admin. |
| Input Data Structures | GET/POST /users, PATCH /users/{id} JSON · module baseline DS |
| Processing Algorithm | 1. Validate display_name non-empty (named person), login unique.<br>2. Create account with argon2id hash; emit user.created.<br>3. PATCH role or active: deactivation sets active=false, deletes all sessions of the user, emits user.deactivated; role change emits user.changed.<br>4. No DELETE endpoint. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | User record; audit events. |
| Output Data Structures | JSON user {id, display_name, login, role, active, created_at} · module baseline DS |
| Error Handling | Duplicate login → 409 LOGIN_TAKEN.<br>Empty display name → 422 NAME_REQUIRED.<br>Admin deactivating own last admin account → 409 LAST_ADMIN.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-AUD-01; FN-IAM-04 · Technical decisions: TD-14 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Supabase Auth (JWT) verified in FastAPI (TQ-04); external IdP post-MVP (ADR-014) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-130; TC-SEC-01; TC-SEC-19 · suites: VER-12, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-IAM-05 (proposed id)<br>Acceptance criteria as unit/component assertions: Deactivated user cannot log in (401) and active sessions are invalidated.<br>No API path deletes a user.<br>One negative test per error code: LAST_ADMIN, LOGIN_TAKEN, NAME_REQUIRED<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-130; TC-SEC-01; TC-SEC-19 |
| Open Technical Questions | TQ-04 |

#### FN-IAM-06 — Record quarterly account review

*Operational procedure (software-supported) · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-IAM-06 |
| Function Name | Record quarterly account review |
| Related Requirement IDs | SEC-19 |
| Architecture Component | C3/M01, C1/W01 · Security and Audit Layer · Operator procedure supported by API/worker jobs |
| Technical Purpose | Evidence the quarterly review of active accounts (SD-10). Admin opens the active-account list, marks it reviewed; system stores a review record. |
| Input Data | Reviewed list snapshot, comment · Preconditions: Clinic admin. |
| Input Data Structures | POST /users/reviews · module baseline DS |
| Processing Algorithm | 1. Snapshot active users (id, role, last login).<br>2. Store review record with reviewer and UTC time; emit users.reviewed.<br>3. Admin dashboard shows days since last review; > 92 days → banner 'account review overdue'. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Review record. |
| Output Data Structures | JSON {review_id, at_utc, reviewer, users[]} · module baseline DS |
| Error Handling | —<br>Policy EH-PROC (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-IAM-05; FN-AUD-01 · Technical decisions: TD-14 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Supabase Auth (JWT) verified in FastAPI (TQ-04); external IdP post-MVP (ADR-014) |
| Security Considerations | Module baseline |
| Verification Strategy | Method I · test cases: TC-SEC-19 · suites: VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-IAM-06 (proposed id)<br>Acceptance criteria as unit/component assertions: Review record exists per quarter; overdue banner after 92 days. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SEC-19 |
| Open Technical Questions | TQ-04 |

### Module API — API conventions (idempotency, concurrency, errors)

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Application Layer / Security and Audit Layer |
| Runtime and execution | C3 API process · Synchronous request middleware |
| Input data structures | Idempotency-Key, If-Match headers, request body |
| Output data structures | Stored response for idempotent replay (ops.idempotency_key); DS-24 |
| Interfaces | IF-01 |
| External libraries | LIB-FASTAPI; LIB-POSTGRES |
| Performance | Middleware overhead TBD (BM-05) |
| Security | Idempotency records scoped per user; keys expire (TBD); error messages contain no internal details; correlation id only |
| Integration tests | Replay same key → same response, single side effect; concurrent If-Match → one 409 VERSION_CONFLICT; every error code reachable in contract tests |
| Alternatives | Optimistic concurrency via row version only (no idempotency) — rejected (NFR-07) |
| Versioning | /api/v1 (TD-22); error catalogue version error/1 |

#### FN-API-01 — Idempotent, concurrency-safe mutations

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-API-01 |
| Function Name | Idempotent, concurrency-safe mutations |
| Related Requirement IDs | NFR-07 |
| Architecture Component | C3 (FastAPI layer), C0 · Application Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Guarantee that committed operations persist exactly once and stale edits are refused. Cross-cutting middleware: Idempotency-Key replay table and If-Match optimistic concurrency on versioned resources (07 §6.1). |
| Input Data | Idempotency-Key (UUID v4) header; If-Match (resource version) header · Preconditions: Mutating request. |
| Input Data Structures | HTTP headers · module baseline DS |
| Processing Algorithm | 1. If an idempotency row exists for (user, key): return stored status/body without re-executing.<br>2. Else execute handler inside one DB transaction; store (user, key, status, body hash, body) in the same transaction.<br>3. For versioned resources: compare If-Match with current version; mismatch → 409 VERSION_CONFLICT.<br>4. Commit; the response is sent only after commit (NFR-07). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Exactly-once side effects. |
| Output Data Structures | Original HTTP response on replay · module baseline DS |
| Error Handling | Missing Idempotency-Key on mutating route → 428 IDEMPOTENCY_KEY_REQUIRED.<br>Stale If-Match → 409 VERSION_CONFLICT.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: none |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Optimistic concurrency via row version only (no idempotency) — rejected (NFR-07) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-API-01 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-API-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Kill browser 1 s after commit; reopen shows the operation in 50/50 trials.<br>Replay of the same key returns identical body and creates no second audit event.<br>One negative test per error code: IDEMPOTENCY_KEY_REQUIRED, VERSION_CONFLICT<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: UT-FN-API-01 (proposed) |
| Open Technical Questions | None registered |

#### FN-API-02 — Error catalogue and gate responses

*API service (synchronous) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-API-02 |
| Function Name | Error catalogue and gate responses |
| Related Requirement IDs | NFR-05; FR-015 |
| Architecture Component | C3 (FastAPI layer), C0 · Application Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Return machine-readable gate/error codes that the UI renders as gate lists. Single error catalogue (07 §6.8 + CN-11 + RTM v0.3 codes); every refusal returns {code, http, message_key_ru, details, gates[]}. Codes first named in this FS (e.g. ACCOUNT_LOCKED, SESSION_EXPIRED, CSRF_INVALID, CONTOUR_AMBIGUOUS, MEASUREMENT_SET_INVALID, REAPPROVAL_REQUIRED usage) are proposals to be added when the catalogue is frozen (OQ-FS-06). |
| Input Data | Exception or gate result · Preconditions: — |
| Input Data Structures | Internal · module baseline DS |
| Processing Algorithm | 1. Map domain exception → catalogue entry.<br>2. Attach correlation ID; for 5xx write application log (no mesh data, no secrets).<br>3. Return JSON problem body; message text resolved from ru resource file by key (NFR-05). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Error response. |
| Output Data Structures | application/problem+json {code, message_key, details, correlation_id} · module baseline DS |
| Error Handling | Unmapped exception → 500 INTERNAL with correlation ID.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: none · Technical decisions: TD-22 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Optimistic concurrency via row version only (no idempotency) — rejected (NFR-07) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-015 · suites: VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-API-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Every code used by any function in this specification exists in the catalogue (CI check).<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-015 |
| Open Technical Questions | OQ-FS-06 |

### Module AUD — Audit

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Security and Audit Layer / Data Layer |
| Runtime and execution | C3 API process (append in caller transaction); C4 worker (verify job) · In-transaction append; background verification |
| Input data structures | Event core + summaries from callers |
| Output data structures | DS-18 rows; verification report |
| Interfaces | IF-08 |
| External libraries | LIB-POSTGRES; LIB-RFC8785; hashlib |
| Performance | PM-19 append overhead TBD; verify O(N) events |
| Security | INSERT-only role; chain head lock; summaries exclude mesh data and secrets; erasable summaries split from hashed core (OQ-FS-07) |
| Integration tests | Scripted session yields one event per action (VER-13); tamper one row → verification flags it; DB role cannot UPDATE/DELETE |
| Alternatives | Per-case chains; external append-only log service |
| Versioning | audit/1 event schema; event type list versioned |

#### FN-AUD-01 — Append audit event (in-transaction, hash-chained)

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-AUD-01 |
| Function Name | Append audit event (in-transaction, hash-chained) |
| Related Requirement IDs | FR-120; DATA-09; SEC-03; NFR-08; DATA-19; AI-10 |
| Architecture Component | C3/M02, C5 · Security and Audit Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Record every state change attributably and tamper-evidently in the same transaction as the change. Service called by every domain module; writes through an INSERT-only DB role (ADR-012). |
| Input Data | type (catalogue), user_id, role, object_type, object_id, object_version, before/after summary, ui_session_id · Preconditions: Caller holds an open DB transaction. |
| Input Data Structures | Internal call; event type ∈ event catalogue (07 §9.2 + CN-12 + AI-10 reserved names) · module baseline DS |
| Processing Algorithm | 1. Validate type against catalogue; reserved ai.* types are rejected in MVP code paths.<br>2. Lock chain head (SELECT … FOR UPDATE on single-row chain_head).<br>3. seq = head.seq + 1; canonical JSON of event (RFC 8785 key order, UTC ISO-8601 timestamps).<br>4. hash = SHA-256(prev_hash ‖ canonical_json); insert row; update head.<br>5. Rollback of the caller's transaction removes the event (atomicity, INV-09).<br>Algorithms: ALG-58 Audit hash chain |
| Mathematical Model | h_n = SHA-256(h_{n−1} ‖ JCS(event_n)); h_0 = SHA-256('JUDE-AUDIT-GENESIS').<br>ALG-58: h_i = SHA-256(h_{i−1} ‖ JCS(core_i)) where core = (seq, type, user_id, role, object type/id/version, at_utc); erasable summary stored outside the hashed core (OQ-FS-07 recommendation). Verification recomputes the chain and reports the first broken link. |
| Geometry Operations | ALG-58 Audit hash chain [approval records / audit] |
| Output Data | audit_event row. |
| Output Data Structures | DATA-09 fields + seq, hash, prev_hash · module baseline DS |
| Error Handling | Unknown event type → programming error, transaction aborted (500).<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-58: O(1) append; O(N) verify |
| Dependencies | Functions: none |
| External Libraries | LIB-RFC8785 rfc8785 (Apache-2.0; CAND); LIB-POSTGRES PostgreSQL on Supabase (+ psycopg 3, SQLAlchemy 2, Alembic) (PostgreSQL licence [N]; psycopg LGPL-3.0-only (dynamically linked, allowed by ADR-011); SQLAlchemy/Alembic MIT; R-MVP); module baseline |
| Alternative Implementations | ALG-58: Per-case chains (parallel) — unnecessary for one clinic. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-09; TC-DATA-19; TC-FR-120; TC-SEC-03 · suites: VER-13, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-AUD-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Scripted session of every event type yields one entry each with all DATA-09 fields.<br>Rolled-back operation leaves no event.<br>ALG-58: Tamper one row → first broken link = that row. Invariants: Chain verifies after any sequence of appends. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-09; TC-DATA-19; TC-FR-120; TC-SEC-03 |
| Open Technical Questions | None registered |

#### FN-AUD-02 — Log read access

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-AUD-02 |
| Function Name | Log read access |
| Related Requirement IDs | SEC-15; FR-164 |
| Architecture Component | C3/M02, C5 · Security and Audit Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Record each view/download of infant data objects. Wrapper on download endpoints for scan blobs, display meshes, exports, reports, audit CSV and prescription files. |
| Input Data | user, role, case_id, object_type, object_id · Preconditions: Authorised read request. |
| Input Data Structures | Internal · module baseline DS |
| Processing Algorithm | 1. After authorisation and before streaming the body, append blob.read / export.downloaded / report.downloaded / audit.exported / prescription.read via FN-AUD-01 in its own committed transaction.<br>2. If the audit write fails, the download is refused (no unlogged read). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Read event. |
| Output Data Structures | audit_event · module baseline DS |
| Error Handling | Audit write failure → 503 AUDIT_UNAVAILABLE, no data returned.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-AUD-01 |
| External Libraries | LIB-POSTGRES PostgreSQL on Supabase (+ psycopg 3, SQLAlchemy 2, Alembic) (PostgreSQL licence [N]; psycopg LGPL-3.0-only (dynamically linked, allowed by ADR-011); SQLAlchemy/Alembic MIT; R-MVP); module baseline |
| Alternative Implementations | Module baseline: Per-case chains; external append-only log service |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-164; TC-SEC-15 · suites: VER-12, VER-13, VER-20, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-AUD-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Scripted session reading each object type yields one read event per access with user, role, UTC time, case ID, object ID.<br>One negative test per error code: AUDIT_UNAVAILABLE<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-164; TC-SEC-15 |
| Open Technical Questions | None registered |

#### FN-AUD-03 — Verify audit chain

*Background job · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-AUD-03 |
| Function Name | Verify audit chain |
| Related Requirement IDs | SEC-03; FR-121; SEC-14 |
| Architecture Component | C3/M02, C5 · Security and Audit Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Detect alteration or deletion of audit rows. Recomputes the hash chain from genesis and reports the first broken link. |
| Input Data | Optional range [from_seq, to_seq] · Preconditions: — |
| Input Data Structures | POST /audit/verify · module baseline DS |
| Processing Algorithm | 1. Iterate events ordered by seq; recompute h_n; compare with stored hash and prev_hash.<br>2. Detect seq gaps.<br>3. Stop at first mismatch; record result; emit audit.verified with outcome.<br>4. Nightly job; mismatch raises incident (SEC-14 detection source).<br>Algorithms: ALG-58 Audit hash chain |
| Mathematical Model | Valid ⇔ ∀n: stored_hash_n = SHA-256(stored_hash_{n−1} ‖ JCS(event_n)) ∧ seq_n = seq_{n−1}+1.<br>ALG-58: h_i = SHA-256(h_{i−1} ‖ JCS(core_i)) where core = (seq, type, user_id, role, object type/id/version, at_utc); erasable summary stored outside the hashed core (OQ-FS-07 recommendation). Verification recomputes the chain and reports the first broken link. |
| Geometry Operations | ALG-58 Audit hash chain [approval records / audit] |
| Output Data | Verification result. |
| Output Data Structures | JSON {ok, checked, first_broken_seq?, reason?} · module baseline DS |
| Error Handling | Broken link → result ok=false, incident flag set.<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-58: O(1) append; O(N) verify |
| Dependencies | Functions: FN-AUD-01; FN-JOB-01 · Technical decisions: TD-25 |
| External Libraries | LIB-POSTGRES PostgreSQL on Supabase (+ psycopg 3, SQLAlchemy 2, Alembic) (PostgreSQL licence [N]; psycopg LGPL-3.0-only (dynamically linked, allowed by ADR-011); SQLAlchemy/Alembic MIT; R-MVP); module baseline |
| Alternative Implementations | ALG-58: Per-case chains (parallel) — unnecessary for one clinic. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-121; TC-SEC-03; TC-SEC-14 · suites: VER-12, VER-13, VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-AUD-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Altering one stored event is detected at that event.<br>Deleting one row is detected as a seq gap.<br>ALG-58: Tamper one row → first broken link = that row. Invariants: Chain verifies after any sequence of appends. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-121; TC-SEC-03; TC-SEC-14 |
| Open Technical Questions | None registered |

#### FN-AUD-04 — View and filter audit log

*User interaction · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-AUD-04 |
| Function Name | View and filter audit log |
| Related Requirement IDs | FR-122; NFR-08 |
| Architecture Component | C3/M02, C5 · Security and Audit Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Let the admin inspect who did what. Paged list with filters by case, user, event type and UTC date range. |
| Input Data | case, user, type, from, to, page · Preconditions: Clinic admin. |
| Input Data Structures | GET /audit?… · module baseline DS |
| Processing Algorithm | 1. Validate filters; query with indexes on (case_id, at_utc), (user_id), (type).<br>2. Display times in clinic time zone (NFR-08). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Filtered rows. |
| Output Data Structures | JSON page {items[], total} · module baseline DS |
| Error Handling | Invalid date range → 422 INVALID_FILTER.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-AUD-01 |
| External Libraries | LIB-POSTGRES PostgreSQL on Supabase (+ psycopg 3, SQLAlchemy 2, Alembic) (PostgreSQL licence [N]; psycopg LGPL-3.0-only (dynamically linked, allowed by ADR-011); SQLAlchemy/Alembic MIT; R-MVP); module baseline |
| Alternative Implementations | Module baseline: Per-case chains; external append-only log service |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-122 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-AUD-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Filtered view count equals filtered CSV row count.<br>One negative test per error code: INVALID_FILTER<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-122 |
| Open Technical Questions | None registered |

#### FN-AUD-05 — Export audit log as CSV

*User interaction · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-AUD-05 |
| Function Name | Export audit log as CSV |
| Related Requirement IDs | FR-122; INT-07; SEC-15 |
| Architecture Component | C3/M02, C5 · Security and Audit Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Provide the log outside the application. UTF-8 CSV with header; same filters as FN-AUD-04; download logged. |
| Input Data | Filters · Preconditions: Clinic admin. |
| Input Data Structures | GET /audit.csv?… · module baseline DS |
| Processing Algorithm | 1. Stream rows with header: seq, at_utc, type, user_id, role, object_type, object_id, object_version, summary, hash.<br>2. Emit audit.exported via FN-AUD-02 before streaming. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | CSV file. |
| Output Data Structures | text/csv; charset=utf-8; RFC 4180 quoting · module baseline DS |
| Error Handling | —<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-AUD-04; FN-AUD-02 |
| External Libraries | LIB-POSTGRES PostgreSQL on Supabase (+ psycopg 3, SQLAlchemy 2, Alembic) (PostgreSQL licence [N]; psycopg LGPL-3.0-only (dynamically linked, allowed by ADR-011); SQLAlchemy/Alembic MIT; R-MVP); module baseline |
| Alternative Implementations | Module baseline: Per-case chains; external append-only log service |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-122; TC-INT-07; TC-SEC-15 · suites: VER-13, VER-20, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-AUD-05 (proposed id)<br>Acceptance criteria as unit/component assertions: CSV parses; Cyrillic preserved; row count equals view count.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-122; TC-INT-07; TC-SEC-15 |
| Open Technical Questions | None registered |

#### FN-AUD-06 — Enforce audit immutability

*Build / CI tooling · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-AUD-06 |
| Function Name | Enforce audit immutability |
| Related Requirement IDs | FR-121; SEC-03 |
| Architecture Component | C3/M02, C5 · Security and Audit Layer · CI container |
| Technical Purpose | Make edit/delete of log entries impossible through UI/API and the application DB role. DB grants + absence of mutate endpoints, checked by tests. |
| Input Data | Migrations, OpenAPI contract · Preconditions: — |
| Input Data Structures | SQL grants; OpenAPI 3.1 · module baseline DS |
| Processing Algorithm | 1. Application role has INSERT/SELECT only on audit_event and chain_head UPDATE only through a SECURITY DEFINER append function.<br>2. CI test: OpenAPI contains no PUT/PATCH/DELETE on /audit*; direct UPDATE/DELETE as app role fails.<br>Algorithms: ALG-58 Audit hash chain |
| Mathematical Model | ALG-58: h_i = SHA-256(h_{i−1} ‖ JCS(core_i)) where core = (seq, type, user_id, role, object type/id/version, at_utc); erasable summary stored outside the hashed core (OQ-FS-07 recommendation). Verification recomputes the chain and reports the first broken link. |
| Geometry Operations | ALG-58 Audit hash chain [approval records / audit] |
| Output Data | Enforced constraints. |
| Output Data Structures | — · module baseline DS |
| Error Handling | —<br>Policy EH-CI (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-58: O(1) append; O(N) verify |
| Dependencies | Functions: FN-AUD-01 · Technical decisions: TD-13 |
| External Libraries | LIB-POSTGRES PostgreSQL on Supabase (+ psycopg 3, SQLAlchemy 2, Alembic) (PostgreSQL licence [N]; psycopg LGPL-3.0-only (dynamically linked, allowed by ADR-011); SQLAlchemy/Alembic MIT; R-MVP); module baseline |
| Alternative Implementations | ALG-58: Per-case chains (parallel) — unnecessary for one clinic. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-121; TC-SEC-03 · suites: VER-12, VER-13 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-AUD-06 (proposed id)<br>Acceptance criteria as unit/component assertions: All mutate endpoints for log absent or return 403/405; UPDATE as app role raises permission error.<br>ALG-58: Tamper one row → first broken link = that row. Invariants: Chain verifies after any sequence of appends. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-121; TC-SEC-03 |
| Open Technical Questions | None registered |

### Module CFG — Clinic configuration

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Domain Layer / Data Layer; UI Layer |
| Runtime and execution | C3 API process; C1 admin screens; C4 for safety check job · Synchronous request; background check |
| Input data structures | DS-16 drafts; DS-10 definitions |
| Output data structures | Published DS-16 versions with diff_sha; NOT_SET resolution results |
| Interfaces | IF-01; IF-07 |
| External libraries | LIB-JSONSCHEMA; LIB-RFC8785; LIB-POSTGRES |
| Performance | Negligible (small documents) |
| Security | No production defaults (INV-12); test_only values cannot reach production; controlled-section changes disclosed in approvals (FR-141) |
| Integration tests | Publish → new version + audit event + diff; objects created afterwards reference the new version; NOT_SET blocks dependent endpoints with CONFIG_NOT_SET |
| Alternatives | Key-value table instead of versioned documents (loses diff/version binding) |
| Versioning | config/1 schema; migration functions for schema changes |

#### FN-CFG-01 — Edit configuration draft

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-01 |
| Function Name | Edit configuration draft |
| Related Requirement IDs | FR-140; DATA-02; DATA-07; FR-054; DATA-22; NFR-09 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Let the technician enter clinic-owned values; nothing ships with production values (INV-12). Form-based editor over the versioned configuration document (07 §5.4). Every key starts NOT_SET in production. |
| Input Data | Configuration document sections: measurement_definitions, frame_definitions, quality_gate, coverage_check, plausible_bbox_mm, zone_categories, magnitude_ranges_mm, positive_base, export_frame, reimport_tolerance_mm, review_checklist, repeatability_bands, reason_categories, display_decimals, time_zone, second_person_config_approval (bool), security (SD-01/02 values), real_patient_data_enabled · Preconditions: Technician (DEC-020). Draft exists or is created from the active version. |
| Input Data Structures | JSON document validated by JSON Schema config/1 (no 'default' keywords for clinical/production keys) · module baseline DS |
| Processing Algorithm | 1. Create draft = copy of active version (or empty with NOT_SET).<br>2. Validate each edit against schema (types, units in key names, enum codes).<br>3. Show per-section diff vs active version.<br>4. Draft edits are not audited individually; publication is (FN-CFG-02). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Draft document. |
| Output Data Structures | JSON draft {id, base_version, payload} · module baseline DS |
| Error Handling | Schema violation → 422 CONFIG_SCHEMA with JSON pointer list.<br>Test fixture value (test_only=true) in production DB → 422 TEST_ONLY_VALUE.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-IAM-04 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Key-value table instead of versioned documents (loses diff/version binding) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-02; TC-DATA-07; TC-DATA-22; TC-FR-054; TC-FR-140 · suites: VER-13, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CFG-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Every key in production starts NOT_SET; schema contains no defaults for clinical/production keys (schema test).<br>One negative test per error code: CONFIG_SCHEMA, TEST_ONLY_VALUE<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-02; TC-DATA-07; TC-DATA-22; TC-FR-054; TC-FR-140 |
| Open Technical Questions | OQ-FS-14; Missing data: Configuration key for the landmark snap-distance limit is not in the FR-140 list (OQ-FS-14). |

##### FN-CFG-01.1 — Section editors

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-01.1 |
| Function Name | Section editors  (subfunction of FN-CFG-01 Edit configuration draft) |
| Related Requirement IDs | Inherited from parent FN-CFG-01: FR-140; DATA-02; DATA-07; FR-054; DATA-22; NFR-09 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Typed editors per section; Russian labels. |
| Input Data | Inherited from FN-CFG-01 |
| Input Data Structures | Inherited from FN-CFG-01 (DS-16 drafts; DS-10 definitions) |
| Processing Algorithm | Typed editors per section; Russian labels. |
| Mathematical Model | Inherited from FN-CFG-01 |
| Geometry Operations | Inherited from FN-CFG-01 |
| Output Data | Inherited from FN-CFG-01 |
| Output Data Structures | Inherited from FN-CFG-01 |
| Error Handling | Inherited from FN-CFG-01 |
| Performance Requirements | Inherited from FN-CFG-01 |
| Dependencies | Inherited from FN-CFG-01 |
| External Libraries | Inherited from FN-CFG-01 |
| Alternative Implementations | Inherited from FN-CFG-01 |
| Security Considerations | Inherited from FN-CFG-01 |
| Verification Strategy | T — verified within FN-CFG-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-CFG-01.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Typed editors per section; Russian labels. |
| Integration Test Requirements | Inherited from FN-CFG-01 |
| Open Technical Questions | Inherited from FN-CFG-01 |

##### FN-CFG-01.2 — Schema validation

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-01.2 |
| Function Name | Schema validation  (subfunction of FN-CFG-01 Edit configuration draft) |
| Related Requirement IDs | Inherited from parent FN-CFG-01: FR-140; DATA-02; DATA-07; FR-054; DATA-22; NFR-09 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | JSON Schema config/1. |
| Input Data | Inherited from FN-CFG-01 |
| Input Data Structures | Inherited from FN-CFG-01 (DS-16 drafts; DS-10 definitions) |
| Processing Algorithm | JSON Schema config/1. |
| Mathematical Model | Inherited from FN-CFG-01 |
| Geometry Operations | Inherited from FN-CFG-01 |
| Output Data | Inherited from FN-CFG-01 |
| Output Data Structures | Inherited from FN-CFG-01 |
| Error Handling | Inherited from FN-CFG-01 |
| Performance Requirements | Inherited from FN-CFG-01 |
| Dependencies | Inherited from FN-CFG-01 |
| External Libraries | LIB-JSONSCHEMA jsonschema (MIT; R-MVP); module baseline |
| Alternative Implementations | Inherited from FN-CFG-01 |
| Security Considerations | Inherited from FN-CFG-01 |
| Verification Strategy | T — verified within FN-CFG-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-CFG-01.2 (proposed id)<br>Isolated test of this step with positive and negative cases: JSON Schema config/1. |
| Integration Test Requirements | Inherited from FN-CFG-01 |
| Open Technical Questions | Inherited from FN-CFG-01 |

##### FN-CFG-01.3 — Draft diff

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-01.3 |
| Function Name | Draft diff  (subfunction of FN-CFG-01 Edit configuration draft) |
| Related Requirement IDs | Inherited from parent FN-CFG-01: FR-140; DATA-02; DATA-07; FR-054; DATA-22; NFR-09 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Structural diff vs active version. |
| Input Data | Inherited from FN-CFG-01 |
| Input Data Structures | Inherited from FN-CFG-01 (DS-16 drafts; DS-10 definitions) |
| Processing Algorithm | Structural diff vs active version. |
| Mathematical Model | Inherited from FN-CFG-01 |
| Geometry Operations | Inherited from FN-CFG-01 |
| Output Data | Inherited from FN-CFG-01 |
| Output Data Structures | Inherited from FN-CFG-01 |
| Error Handling | Inherited from FN-CFG-01 |
| Performance Requirements | Inherited from FN-CFG-01 |
| Dependencies | Inherited from FN-CFG-01 |
| External Libraries | Inherited from FN-CFG-01 |
| Alternative Implementations | Inherited from FN-CFG-01 |
| Security Considerations | Inherited from FN-CFG-01 |
| Verification Strategy | T — verified within FN-CFG-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-CFG-01.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Structural diff vs active version. |
| Integration Test Requirements | Inherited from FN-CFG-01 |
| Open Technical Questions | Inherited from FN-CFG-01 |

#### FN-CFG-02 — Publish configuration version

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-02 |
| Function Name | Publish configuration version |
| Related Requirement IDs | FR-140; FR-141; DATA-11; SEC-17 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Activate a configuration version with a stored diff; apply the controlled-change rule (FR-141, DEC-020). Publishing creates version n+1. If a controlled section changed, designs approved under version n are marked as needing re-approval before export (rule G-07). |
| Input Data | draft_id; optional comment · Preconditions: Technician; draft valid. |
| Input Data Structures | POST /config/drafts/{id}/publish · module baseline DS |
| Processing Algorithm | 1. Compute diff(draft, active) per section; diff_sha = SHA-256(JCS(diff)).<br>2. controlled = diff touches any of {review_checklist, quality_gate, coverage_check, plausible_bbox_mm, magnitude_ranges_mm, positive_base, export_frame, reimport_tolerance_mm, real_patient_data_enabled}.<br>3. If controlled ∧ second_person_config_approval = true → store version n+1 with state pending_approval (inactive) and stop; activation via FN-CFG-03.<br>4. Else store version n+1 active; record controlled_last_changed_by/at when controlled.<br>5. If controlled: for every approval whose config_version < n+1 and whose design has no released export under it, set approval.reapproval_required = true (export gate E4).<br>6. Emit config.published (with diff_sha, controlled flag).<br>Algorithms: ALG-55 Canonical JSON hash (RFC 8785 JCS) |
| Mathematical Model | ALG-55: params_sha = SHA-256(JCS(op-log ‖ frame ref ‖ config version)); JCS sorts keys by UTF-16 code units and serialises numbers per ECMAScript (shortest round-trip). |
| Geometry Operations | ALG-55 Canonical JSON hash (RFC 8785 JCS) [design versions / parameter binding / configuration diff] |
| Output Data | Active configuration version. |
| Output Data Structures | JSON {version, diff_sha, controlled, state} · module baseline DS |
| Error Handling | Concurrent publication → 409 VERSION_CONFLICT.<br>real_patient_data_enabled true without decision-record ID and VER-22 record ID → 422 PRIVACY_RECORD_REQUIRED (FN-CFG-08).<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-55: O(size) |
| Dependencies | Functions: FN-CFG-01; FN-AUD-01 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-55: Python json.dumps(sort_keys) — differs from JCS for some numbers/strings. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-11; TC-FR-140; TC-FR-141; TC-SEC-17 · suites: VER-12, VER-20, VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CFG-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Edit creates version n+1 with diff hash and audit event.<br>After a controlled change, export of a design approved under version n returns REAPPROVAL_REQUIRED.<br>With the optional switch on, a controlled change stays inactive until a different user approves.<br>ALG-55: RFC 8785 test vectors. Invariants: Key order independence.<br>One negative test per error code: PRIVACY_RECORD_REQUIRED, VERSION_CONFLICT |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-11; TC-FR-140; TC-FR-141; TC-SEC-17 |
| Open Technical Questions | OQ-FS-05 |

##### FN-CFG-02.1 — Diff and controlled-section detection

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-02.1 |
| Function Name | Diff and controlled-section detection  (subfunction of FN-CFG-02 Publish configuration version) |
| Related Requirement IDs | Inherited from parent FN-CFG-02: FR-140; FR-141; DATA-11; SEC-17 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Per-section diff and diff_sha. |
| Input Data | Inherited from FN-CFG-02 |
| Input Data Structures | Inherited from FN-CFG-02 (DS-16 drafts; DS-10 definitions) |
| Processing Algorithm | Per-section diff and diff_sha. — implemented by ALG-55 |
| Mathematical Model | ALG-55: params_sha = SHA-256(JCS(op-log ‖ frame ref ‖ config version)); JCS sorts keys by UTF-16 code units and serialises numbers per ECMAScript (shortest round-trip). |
| Geometry Operations | ALG-55 Canonical JSON hash (RFC 8785 JCS) [design versions / parameter binding / configuration diff] |
| Output Data | Inherited from FN-CFG-02 |
| Output Data Structures | Inherited from FN-CFG-02 |
| Error Handling | Inherited from FN-CFG-02 |
| Performance Requirements | Inherited from FN-CFG-02 — complexity: ALG-55: O(size) |
| Dependencies | Inherited from FN-CFG-02 |
| External Libraries | LIB-RFC8785 rfc8785 (Apache-2.0; CAND); module baseline |
| Alternative Implementations | ALG-55: Python json.dumps(sort_keys) — differs from JCS for some numbers/strings. |
| Security Considerations | Inherited from FN-CFG-02 |
| Verification Strategy | T — verified within FN-CFG-02 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-CFG-02.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Per-section diff and diff_sha.<br>ALG-55: RFC 8785 test vectors. Invariants: Key order independence. |
| Integration Test Requirements | Inherited from FN-CFG-02 |
| Open Technical Questions | Inherited from FN-CFG-02 |

##### FN-CFG-02.2 — Activation

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-02.2 |
| Function Name | Activation  (subfunction of FN-CFG-02 Publish configuration version) |
| Related Requirement IDs | Inherited from parent FN-CFG-02: FR-140; FR-141; DATA-11; SEC-17 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Immediate or pending (optional second person). |
| Input Data | Inherited from FN-CFG-02 |
| Input Data Structures | Inherited from FN-CFG-02 (DS-16 drafts; DS-10 definitions) |
| Processing Algorithm | Immediate or pending (optional second person). |
| Mathematical Model | Inherited from FN-CFG-02 |
| Geometry Operations | Inherited from FN-CFG-02 |
| Output Data | Inherited from FN-CFG-02 |
| Output Data Structures | Inherited from FN-CFG-02 |
| Error Handling | Inherited from FN-CFG-02 |
| Performance Requirements | Inherited from FN-CFG-02 |
| Dependencies | Inherited from FN-CFG-02 |
| External Libraries | Inherited from FN-CFG-02 |
| Alternative Implementations | Inherited from FN-CFG-02 |
| Security Considerations | Inherited from FN-CFG-02 |
| Verification Strategy | T — verified within FN-CFG-02 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-CFG-02.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Immediate or pending (optional second person). |
| Integration Test Requirements | Inherited from FN-CFG-02 |
| Open Technical Questions | Inherited from FN-CFG-02 |

##### FN-CFG-02.3 — Re-approval marking

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-02.3 |
| Function Name | Re-approval marking  (subfunction of FN-CFG-02 Publish configuration version) |
| Related Requirement IDs | Inherited from parent FN-CFG-02: FR-140; FR-141; DATA-11; SEC-17 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Flag approvals under older controlled version (G-07). |
| Input Data | Inherited from FN-CFG-02 |
| Input Data Structures | Inherited from FN-CFG-02 (DS-16 drafts; DS-10 definitions) |
| Processing Algorithm | Flag approvals under older controlled version (G-07). |
| Mathematical Model | Inherited from FN-CFG-02 |
| Geometry Operations | Inherited from FN-CFG-02 |
| Output Data | Inherited from FN-CFG-02 |
| Output Data Structures | Inherited from FN-CFG-02 |
| Error Handling | Inherited from FN-CFG-02 |
| Performance Requirements | Inherited from FN-CFG-02 |
| Dependencies | Inherited from FN-CFG-02 |
| External Libraries | Inherited from FN-CFG-02 |
| Alternative Implementations | Inherited from FN-CFG-02 |
| Security Considerations | Inherited from FN-CFG-02 |
| Verification Strategy | T — verified within FN-CFG-02 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-CFG-02.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Flag approvals under older controlled version (G-07). |
| Integration Test Requirements | Inherited from FN-CFG-02 |
| Open Technical Questions | Inherited from FN-CFG-02 |

#### FN-CFG-03 — Approve controlled configuration change (optional second person)

*User interaction · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-03 |
| Function Name | Approve controlled configuration change (optional second person) |
| Related Requirement IDs | FR-141 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Optional segregation of duties for safety-relevant settings when the switch is on. Only used when second_person_config_approval = true (off by default, DEC-020). |
| Input Data | version id, decision (approve/refuse), reason · Preconditions: Pending version exists; caller ≠ author. |
| Input Data Structures | POST /config/versions/{id}/approve · module baseline DS |
| Processing Algorithm | 1. If caller = author → 403 SELF_APPROVAL_FORBIDDEN, emit config.approval_refused.<br>2. Approve → activate version, then run step 5 of FN-CFG-02; emit config.approved.<br>3. Refuse → version stays inactive with reason. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Activated or refused version. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | Not pending → 409 NOT_PENDING.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CFG-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Key-value table instead of versioned documents (loses diff/version binding) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-141 · suites: VER-12 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CFG-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Author approving own pending version is refused.<br>One negative test per error code: NOT_PENDING<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-141 |
| Open Technical Questions | None registered |

#### FN-CFG-04 — Resolve active configuration value (NOT_SET gate)

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-04 |
| Function Name | Resolve active configuration value (NOT_SET gate) |
| Related Requirement IDs | FR-140; DATA-11; SAF-02 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Single read path for configuration; missing values block dependent operations instead of defaulting. Library used by all modules and by kernel job builders. |
| Input Data | key path, purpose · Preconditions: — |
| Input Data Structures | Internal · module baseline DS |
| Processing Algorithm | 1. Read active version (cached per request).<br>2. If value is NOT_SET → raise CONFIG_NOT_SET {key}.<br>3. Return value and config_version (caller stores it, DATA-11). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Value + version. |
| Output Data Structures | Internal tuple · module baseline DS |
| Error Handling | NOT_SET → 409 CONFIG_NOT_SET with key.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CFG-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Key-value table instead of versioned documents (loses diff/version binding) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-11; TC-FR-140; TC-SAF-02 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CFG-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Each dependent operation with an unset key returns CONFIG_NOT_SET naming the key.<br>One negative test per error code: CONFIG_NOT_SET, NOT_SET<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-11; TC-FR-140; TC-SAF-02 |
| Open Technical Questions | None registered |

#### FN-CFG-05 — Manage measurement definitions

*User interaction · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-05 |
| Function Name | Manage measurement definitions |
| Related Requirement IDs | FR-041; FR-042; DATA-02; STK-03 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Versioned definitions so every index value is reproducible and labelled (DEC-014, DEC-027). Ships four preset definitions (CVAI/CVA at diagonal angle 30° and 40°, each with shorter- and longer-diagonal denominator) plus CI and HC definition templates without frame binding; technician completes frame/plane rules. |
| Input Data | DATA-02 fields: id, version, name, formula type, denominator rule, diagonal angle (deg), plane/level rule, frame definition ID, unit, source reference, author; plus proposed fields contour_selection_rule and diagonal_centre_rule (OQ-FS-03) · Preconditions: Technician. |
| Input Data Structures | JSON object in configuration document · module baseline DS |
| Processing Algorithm | 1. Create or edit; any edit of a published definition creates version n+1 (FR-041).<br>2. Validate: angle ∈ (0°, 90°); denominator ∈ {shorter_diagonal, longer_diagonal} for CVAI; formula type ∈ enumerated set (OQ-FS-02).<br>3. Presets are flagged 'preset (DEC-027)' and still require frame/plane rules before use; a definition with any NOT_SET field cannot be selected. |
| Mathematical Model | CI = 100·W/L; CVA = \|D₁ − D₂\| (mm); CVAI_short = 100·\|D₁ − D₂\|/min(D₁,D₂); CVAI_long = 100·\|D₁ − D₂\|/max(D₁,D₂); HC = perimeter of the selected closed contour (mm). |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Versioned definitions. |
| Output Data Structures | DATA-02 JSON · module baseline DS |
| Error Handling | Incomplete definition selected → 422 DEFINITION_INCOMPLETE.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CFG-01; FN-CFG-06 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Key-value table instead of versioned documents (loses diff/version binding) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-02; TC-FR-041; TC-FR-042 · suites: VER-01, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CFG-05 (proposed id)<br>Acceptance criteria as unit/component assertions: Presets at 30° and 40° present in both denominator variants.<br>Editing definition n yields n+1; values computed under n still reference n.<br>One negative test per error code: DEFINITION_INCOMPLETE<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-02; TC-FR-041; TC-FR-042 |
| Open Technical Questions | OQ-FS-02; OQ-FS-03; Missing data: DATA-02 has a free 'formula expression' field but no contour-selection or diagonal-centre rule; representation must be decided (OQ-FS-02, OQ-FS-03). |

#### FN-CFG-06 — Manage landmark/frame definitions

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-06 |
| Function Name | Manage landmark/frame definitions |
| Related Requirement IDs | DATA-07; FR-030; FR-031 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Define the named landmark set and the construction rule for origin and axes (UD-02). Versioned frame definition object; construction rule chosen from an enumerated rule family so FN-KFR-02 can execute it deterministically. |
| Input Data | name, landmarks[{code, name_ru, description, side ∈ {L, R, midline}}], origin_rule, axis_rules (primary axis from landmark pair/plane, secondary axis, handedness), version · Preconditions: Technician. |
| Input Data Structures | JSON (DATA-07) · module baseline DS |
| Processing Algorithm | 1. Validate landmark codes unique; rule references only declared landmarks; paired L/R landmarks declared as pairs.<br>2. Rule family (engineering proposal, to confirm with UD-02 owner): origin = point \| midpoint(pair) \| centroid(set) \| projection of point on plane; X axis = direction between two points/midpoints; plane from ≥3 landmarks; Y = n_plane × X; Z = X × Y (right-handed).<br>3. Edit creates new version. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Frame definition version. |
| Output Data Structures | DATA-07 JSON · module baseline DS |
| Error Handling | Rule refers to undefined landmark → 422 FRAME_RULE_INVALID.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CFG-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Key-value table instead of versioned documents (loses diff/version binding) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-07; TC-FR-030; TC-FR-031 · suites: VER-01, VER-03, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CFG-06 (proposed id)<br>Acceptance criteria as unit/component assertions: Schema contains DATA-07 fields; definition with unresolved references cannot be published.<br>One negative test per error code: FRAME_RULE_INVALID<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-07; TC-FR-030; TC-FR-031 |
| Open Technical Questions | OQ-FS-03; Missing data: Clinic landmark set and construction rule (UD-02) are clinic configuration values entered on site (DEC-027/DEC-029). |

#### FN-CFG-07 — Production configuration safety check

*Background job · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-07 |
| Function Name | Production configuration safety check |
| Related Requirement IDs | FR-140; FR-014; FR-172 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Prevent test fixture values from reaching production and detect unset pilot-entry keys. Start-up and pre-pilot check. |
| Input Data | Active configuration, environment = production\|test · Preconditions: Application start. |
| Input Data Structures | Internal · module baseline DS |
| Processing Algorithm | 1. If production and any value carries test_only=true → refuse start (log CONFIG_TEST_VALUE_IN_PROD).<br>2. Produce pilot-readiness report listing every NOT_SET key used by the MVP workflow. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Start/refuse; readiness report. |
| Output Data Structures | JSON {not_set_keys[]} · module baseline DS |
| Error Handling | Test value in production → process exits non-zero.<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CFG-04 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Key-value table instead of versioned documents (loses diff/version binding) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-014; TC-FR-140; TC-FR-172 · suites: VER-08, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CFG-07 (proposed id)<br>Acceptance criteria as unit/component assertions: Production DB refuses test_only configuration; report lists every NOT_SET key.<br>Job handler tests with fake kernel results: success, deterministic rejection, retryable failure, idempotent re-run. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-014; TC-FR-140; TC-FR-172 |
| Open Technical Questions | None registered |

#### FN-CFG-08 — Real-patient-data gate

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-CFG-08 |
| Function Name | Real-patient-data gate |
| Related Requirement IDs | SEC-17; VER-22; STK-06 |
| Architecture Component | C3/M04, C1/W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Block uploads of real scans until privacy approvals exist (SEC-17, VER-22). Deployment setting real_patient_data_enabled (controlled section). Enabling requires the decision record ID (DR-2026-11-12) and the VER-22 inspection record ID. |
| Input Data | real_patient_data_enabled, decision_record_id, ver22_record_id · Preconditions: Technician; FN-CFG-02 path. |
| Input Data Structures | Config section privacy_gate · module baseline DS |
| Processing Algorithm | 1. Enabling without both IDs → 422 PRIVACY_RECORD_REQUIRED.<br>2. Change goes through FN-CFG-02 (controlled section, audit event).<br>3. FN-SCN-01 reads the flag; false → REAL_DATA_DISABLED. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Gate state. |
| Output Data Structures | Config value · module baseline DS |
| Error Handling | Missing record IDs → 422.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CFG-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Key-value table instead of versioned documents (loses diff/version binding) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-SEC-17 · suites: VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CFG-08 (proposed id)<br>Acceptance criteria as unit/component assertions: With flag false, upload returns REAL_DATA_DISABLED; enabling without both record IDs is refused; enabling is logged.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SEC-17 |
| Open Technical Questions | OQ-FS-05 |

### Module JOB — Jobs and worker runtime

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Application Layer / Data Layer; Geometry Engine |
| Runtime and execution | C3 (enqueue, status, completion handler) + C4 worker pool (claim/run) · Asynchronous jobs |
| Input data structures | DS-17 job rows |
| Output data structures | DS-17 results; DS-05 summaries |
| Interfaces | IF-02 |
| External libraries | LIB-POSTGRES |
| Performance | PM-18 claim latency; pool size k from BM-06 |
| Security | Worker cannot authorise or write audit directly (07 §3); payloads contain shas and params only; per-job CPU/memory limits (SEC-07) |
| Integration tests | Kill worker mid-job → lease expiry → retry (idempotent) or failed (non-idempotent); completion handler writes result + domain change + audit atomically |
| Alternatives | Celery/RQ + Redis (rejected ADR-007) |
| Versioning | job/1 payload schema; job type names with version suffix |

#### FN-JOB-01 — Enqueue job transactionally

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-JOB-01 |
| Function Name | Enqueue job transactionally |
| Related Requirement IDs | NFR-07 |
| Architecture Component | C3/M12, C4, C5 · Application Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Hand long or untrusted work to the worker atomically with the domain change. Inserts a job row in the caller's transaction (ADR-007). |
| Input Data | type, input artifact SHAs, params, requested_by, idempotency_key · Preconditions: Open transaction. |
| Input Data Structures | job row JSON payload · module baseline DS |
| Processing Algorithm | 1. Insert job(status=queued, attempts=0, idempotent=flag from op registry).<br>2. Return job_id; API responds 202 {job_id}. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Queued job. |
| Output Data Structures | HTTP 202 {job_id} · module baseline DS |
| Error Handling | —<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: none · Technical decisions: TD-15 |
| External Libraries | LIB-POSTGRES PostgreSQL on Supabase (+ psycopg 3, SQLAlchemy 2, Alembic) (PostgreSQL licence [N]; psycopg LGPL-3.0-only (dynamically linked, allowed by ADR-011); SQLAlchemy/Alembic MIT; R-MVP); module baseline |
| Alternative Implementations | Module baseline: Celery/RQ + Redis (rejected ADR-007) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-JOB-01 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-JOB-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Rolled-back request leaves no job.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: UT-FN-JOB-01 (proposed) |
| Open Technical Questions | None registered |

#### FN-JOB-02 — Worker claim, lease, heartbeat and retry

*Background job · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-JOB-02 |
| Function Name | Worker claim, lease, heartbeat and retry |
| Related Requirement IDs | NFR-07; SAF-09; SEC-07 |
| Architecture Component | C3/M12, C4, C5 · Application Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Run jobs reliably with crash recovery and without duplicate side effects. Worker loop claims with FOR UPDATE SKIP LOCKED, holds a lease, heartbeats, retries idempotent jobs up to 3 attempts. |
| Input Data | job table · Preconditions: Worker process with resource limits (SEC-07). |
| Input Data Structures | SQL · module baseline DS |
| Processing Algorithm | 1. Poll every ≤ 250 ms: claim oldest queued job; set status=running, lease_until=now+L (L = 60 s), attempts+=1.<br>2. Heartbeat every L/3 extends lease.<br>3. Execute registered handler with CPU-time and memory limits.<br>4. Success → write result, call completion handler (FN-JOB-04).<br>5. Exception or kernel 'rejected' → status=failed with code (no retry for 'rejected').<br>6. Lease expiry detected by reaper: idempotent ∧ attempts<3 → queued; else failed. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Job outcomes. |
| Output Data Structures | job.status ∈ {queued, running, succeeded, failed} · module baseline DS |
| Error Handling | OOM/time limit → failed JOB_RESOURCE_LIMIT; last valid geometry unchanged (SAF-09).<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-JOB-01 · Technical decisions: TD-15 |
| External Libraries | LIB-POSTGRES PostgreSQL on Supabase (+ psycopg 3, SQLAlchemy 2, Alembic) (PostgreSQL licence [N]; psycopg LGPL-3.0-only (dynamically linked, allowed by ADR-011); SQLAlchemy/Alembic MIT; R-MVP); module baseline |
| Alternative Implementations | Module baseline: Celery/RQ + Redis (rejected ADR-007) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-SAF-09; TC-SEC-07 · suites: VER-08, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-JOB-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Killing worker mid-job → job re-queued after lease; retry yields the same geometry hash.<br>One negative test per error code: JOB_RESOURCE_LIMIT<br>Job handler tests with fake kernel results: success, deterministic rejection, retryable failure, idempotent re-run. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SAF-09; TC-SEC-07 |
| Open Technical Questions | None registered |

#### FN-JOB-03 — Report job status

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-JOB-03 |
| Function Name | Report job status |
| Related Requirement IDs | NFR-07 |
| Architecture Component | C3/M12, C4, C5 · Application Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Let the UI follow long operations. Polling endpoint. |
| Input Data | job_id · Preconditions: Requester owns job or may access its case. |
| Input Data Structures | GET /jobs/{id} · module baseline DS |
| Processing Algorithm | 1. Return status, progress (if reported), result summary or error code. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Status. |
| Output Data Structures | JSON {status, progress?, result?, error?} · module baseline DS |
| Error Handling | Unknown → 404.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-JOB-02 · Technical decisions: TD-15 |
| External Libraries | LIB-POSTGRES PostgreSQL on Supabase (+ psycopg 3, SQLAlchemy 2, Alembic) (PostgreSQL licence [N]; psycopg LGPL-3.0-only (dynamically linked, allowed by ADR-011); SQLAlchemy/Alembic MIT; R-MVP); module baseline |
| Alternative Implementations | Module baseline: Celery/RQ + Redis (rejected ADR-007) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-JOB-03 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-JOB-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Status transitions visible within one poll interval.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: UT-FN-JOB-03 (proposed) |
| Open Technical Questions | None registered |

#### FN-JOB-04 — Job completion handler

*Background job · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-JOB-04 |
| Function Name | Job completion handler |
| Related Requirement IDs | FR-120; NFR-07 |
| Architecture Component | C3/M12, C4, C5 · Application Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Persist kernel results and domain state changes with their audit event in one transaction. Per job type handler in C3 code (the worker never writes audit rows directly). |
| Input Data | Job result (artifact SHAs, report JSON) · Preconditions: Job succeeded or failed. |
| Input Data Structures | Internal · module baseline DS |
| Processing Algorithm | 1. Begin transaction; verify inputs still current (e.g. draft version unchanged) else mark result stale.<br>2. Insert artifacts/records; update domain state; append audit event.<br>3. Commit. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Domain records. |
| Output Data Structures | DB rows · module baseline DS |
| Error Handling | Stale result → discarded, job marked superseded_result.<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-JOB-02; FN-AUD-01 · Technical decisions: TD-15 |
| External Libraries | LIB-POSTGRES PostgreSQL on Supabase (+ psycopg 3, SQLAlchemy 2, Alembic) (PostgreSQL licence [N]; psycopg LGPL-3.0-only (dynamically linked, allowed by ADR-011); SQLAlchemy/Alembic MIT; R-MVP); module baseline |
| Alternative Implementations | Module baseline: Celery/RQ + Redis (rejected ADR-007) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-120 · suites: VER-13 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-JOB-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Each kernel job outcome produces exactly one audit event.<br>Job handler tests with fake kernel results: success, deterministic rejection, retryable failure, idempotent re-run. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-120 |
| Open Technical Questions | None registered |

### Module BLB — Blob store

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Data Layer / Security and Audit Layer |
| Runtime and execution | C3/C4 via IF-04; scheduled verification in C4 · Synchronous library calls; background verification |
| Input data structures | Bytes + kind + case_id |
| Output data structures | DS-19 artifact rows; sha256 |
| Interfaces | IF-04 |
| External libraries | LIB-SUPA-STORAGE; LIB-POSTGRES |
| Performance | PM-20 throughput; streaming hashing O(bytes) |
| Security | Content addressing; no overwrite; app credential without delete; separate purge credential (OQ-FS-07); case-scope check before any read (FR-002); every read logged (SEC-15) |
| Integration tests | put same bytes twice → one object; overwrite attempt with app credential refused (X-07); re-verification detects altered object; restore drill |
| Alternatives | Filesystem CAS on a clinic server; other S3-compatible storage |
| Versioning | Blob key layout v1 (<bucket>/<sha[0:2]>/<sha>) |

#### FN-BLB-01 — Store blob by content address

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-BLB-01 |
| Function Name | Store blob by content address |
| Related Requirement IDs | FR-011 |
| Architecture Component | C3/M13, C6 · Data Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Immutable storage of files and arrays addressed by SHA-256. put(bytes) → sha256; idempotent. |
| Input Data | bytes, kind · Preconditions: — |
| Input Data Structures | Binary · module baseline DS |
| Processing Algorithm | 1. Compute SHA-256 while streaming to a temp object.<br>2. If object sha exists → discard temp; else move to final key blobs/aa/bb/sha.<br>3. Never overwrite; no delete in the application interface. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | sha256. |
| Output Data Structures | char(64) · module baseline DS |
| Error Handling | Storage failure → 503 STORAGE_UNAVAILABLE; caller transaction aborted.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: none · Technical decisions: TD-13 |
| External Libraries | LIB-SUPA-STORAGE Supabase Storage (S3-compatible endpoint) (Service terms (Supabase client libs MIT); R-MVP); module baseline |
| Alternative Implementations | Module baseline: Filesystem CAS on a clinic server; other S3-compatible storage |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-011 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-BLB-01 (proposed id)<br>Acceptance criteria as unit/component assertions: put twice → same SHA, one object.<br>One negative test per error code: STORAGE_UNAVAILABLE<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-011 |
| Open Technical Questions | TQ-02; TQ-03; TQ-25 |

#### FN-BLB-02 — Retrieve blob with case scope

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-BLB-02 |
| Function Name | Retrieve blob with case scope |
| Related Requirement IDs | FR-002; SEC-15; SEC-16 |
| Architecture Component | C3/M13, C6 · Data Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Serve blobs only for cases the user may see, with read logging. GET /blobs/{sha}; SHAs are not capabilities. |
| Input Data | sha256 · Preconditions: Authenticated. |
| Input Data Structures | GET /blobs/{sha} · module baseline DS |
| Processing Algorithm | 1. Resolve blob → artifact → case (FR-002).<br>2. Authorise (FN-IAM-04).<br>3. Log read (FN-AUD-02).<br>4. Stream with ETag = sha. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Bytes. |
| Output Data Structures | application/octet-stream or jude-mesh/1 · module baseline DS |
| Error Handling | Blob not linked to an accessible case → 403.<br>Missing blob → 500 BLOB_MISSING + integrity incident; case set read-only.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-IAM-04; FN-AUD-02 · Technical decisions: TD-13 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Filesystem CAS on a clinic server; other S3-compatible storage |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-002; TC-SEC-15; TC-SEC-16 · suites: VER-12, VER-13, VER-20, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-BLB-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Blob of another case → 403.<br>One negative test per error code: BLOB_MISSING<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-002; TC-SEC-15; TC-SEC-16 |
| Open Technical Questions | TQ-02 |

#### FN-BLB-03 — Periodic blob re-verification

*Background job · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-BLB-03 |
| Function Name | Periodic blob re-verification |
| Related Requirement IDs | FR-011; SEC-08; SEC-14 |
| Architecture Component | C3/M13, C6 · Data Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Detect silent corruption or loss of stored files. Nightly recompute SHA of a rotating sample and full run after restore. |
| Input Data | Blob index · Preconditions: — |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. For each blob in batch: recompute SHA-256; mismatch or missing → incident record, emit blob.integrity_failed. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Verification report. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | —<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-BLB-01 · Technical decisions: TD-13, TD-25 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Filesystem CAS on a clinic server; other S3-compatible storage |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-011; TC-SEC-08; TC-SEC-14 · suites: VER-20, VER-21, VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-BLB-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Corrupted test blob is reported.<br>Job handler tests with fake kernel results: success, deterministic rejection, retryable failure, idempotent re-run. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-011; TC-SEC-08; TC-SEC-14 |
| Open Technical Questions | TQ-02 |

#### FN-BLB-04 — Privileged purge for erasure

*Operational procedure (software-supported) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-BLB-04 |
| Function Name | Privileged purge for erasure |
| Related Requirement IDs | SEC-11 |
| Architecture Component | C3/M13, C6 · Data Layer · Operator procedure supported by API/worker jobs |
| Technical Purpose | Physically remove stored files of an erased case without exposing a general delete path. Separate credential and code path callable only by FN-CAS-08. |
| Input Data | List of SHAs exclusively referenced by the case · Preconditions: Erasure authorised by FN-CAS-08. |
| Input Data Structures | Internal · module baseline DS |
| Processing Algorithm | 1. Compute SHAs referenced only by the erased case (reference counting across cases).<br>2. Delete objects via purge credential; record purge manifest (SHA list, time). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Purge manifest. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | Partial failure → erasure state 'incomplete', retried; incident if > 24 h.<br>Policy EH-PROC (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-BLB-01 · Technical decisions: TD-13 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Filesystem CAS on a clinic server; other S3-compatible storage |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-SEC-11 · suites: VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-BLB-04 (proposed id)<br>Acceptance criteria as unit/component assertions: After erasure no blob of the case is retrievable; blobs shared with other cases remain. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SEC-11 |
| Open Technical Questions | OQ-FS-07; TQ-02; TQ-03; Missing data: Conflict between SEC-11 (erase stored files) and ADR-005/BL-009 (no delete path); resolution and purge credential model needed (OQ-FS-07). |

## SS-02 — Case and data governance

### Module CAS — Case, consent, prescription, retention

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Domain Layer / Data Layer; Security and Audit Layer; UI Layer |
| Runtime and execution | C3 API; C1 screens (W02, W07) · Synchronous request |
| Input data structures | DS-22 inputs |
| Output data structures | DS-22 records; DS-18 events |
| Interfaces | IF-01; IF-04; IF-08 |
| External libraries | LIB-FASTAPI; LIB-POSTGRES; LIB-SUPA-STORAGE |
| Performance | Negligible |
| Security | Clinical metadata zone Z-CLIN; no direct identifiers in DB fields (DATA-10); prescription file stored, never parsed; read logging; erasure procedure under OQ-FS-07 |
| Integration tests | Case lifecycle across archive; consent gate on upload; prescription attach/download with audit; erasure drill on test case (SEC-11) |
| Alternatives | — |
| Versioning | DB migrations (Alembic, forward-only) |

#### FN-CAS-01 — Create case

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-01 |
| Function Name | Create case |
| Related Requirement IDs | FR-001; FR-002; DATA-10; SEC-18 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Open a pseudonymous case that owns every later object. Admin creates a case; system generates ID 'J-' + 8 Crockford base32 characters. No structured identity fields exist (DATA-10). |
| Input Data | Optional clinic reference (free text ≤ 64 chars) · Preconditions: Clinic admin authenticated. |
| Input Data Structures | POST /cases JSON {clinic_ref?} · module baseline DS |
| Processing Algorithm | 1. Generate 40-bit random ID, encode Crockford base32 (8 chars), prefix 'J-'; retry on collision.<br>2. If clinic_ref duplicates an existing active case → return warning DUPLICATE_CLINIC_REF (creation still allowed).<br>3. Insert case {case_id, clinic_ref, status=active, created_by, created_at_utc}; emit case.created. |
| Mathematical Model | ID space 32⁸ ≈ 1.1·10¹²; collision handled by unique constraint + retry. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Case record. |
| Output Data Structures | JSON {case_id, clinic_ref, created_at} · module baseline DS |
| Error Handling | clinic_ref > 64 chars → 422 FIELD_TOO_LONG.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-AUD-01; FN-IAM-04 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-10; TC-FR-001; TC-FR-002; TC-SEC-18 · suites: VER-20, VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CAS-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Unique ID created; schema has no name/IIN/address/phone/DOB fields; event logged.<br>One negative test per error code: FIELD_TOO_LONG<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-10; TC-FR-001; TC-FR-002; TC-SEC-18 |
| Open Technical Questions | None registered |

#### FN-CAS-02 — List cases and show case contents

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-02 |
| Function Name | List cases and show case contents |
| Related Requirement IDs | FR-004; UR-05; STK-02 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Find a case and every object linked to it. Case list (search by case ID or clinic reference) and case contents view (type, version, creator, UTC time). |
| Input Data | Search string; case_id · Preconditions: Authenticated. |
| Input Data Structures | GET /cases?q= ; GET /cases/{id}/contents · module baseline DS |
| Processing Algorithm | 1. Case list: exact or prefix match on case_id/clinic_ref; active first, archived toggle.<br>2. Contents: union of scans, prescription files, landmark sets, frames, measurement sets, designs/versions, approvals, exports, reports with type, version, creator, created_at.<br>3. Show consent-reference status and real-data gate state on the case header. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Lists. |
| Output Data Structures | JSON arrays · module baseline DS |
| Error Handling | Unknown case → 404.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CAS-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-004 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CAS-02 (proposed id)<br>Acceptance criteria as unit/component assertions: For a seeded case with N objects the contents view shows exactly N rows with all four fields.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-004 |
| Open Technical Questions | OQ-FS-25; Missing data: Case list/search has no explicit requirement (GAP-M01); included as necessary navigation. |

#### FN-CAS-03 — Archive case or object

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-03 |
| Function Name | Archive case or object |
| Related Requirement IDs | FR-003 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Replace deletion with read-only archiving. Sets archived flag; archived objects remain retrievable in the archive view. |
| Input Data | case_id or object id · Preconditions: Clinic admin. |
| Input Data Structures | POST /cases/{id}/archive · module baseline DS |
| Processing Algorithm | 1. Refuse if the case has an approval whose export is not yet released or an active job → 409 ACTIVE_APPROVAL_IN_USE.<br>2. Set archived=true, archived_by/at; emit case.archived.<br>3. All mutating routes on archived objects → 409 CASE_ARCHIVED (FN-IAM-04). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Archived state. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | See logic.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-AUD-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-003 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CAS-03 (proposed id)<br>Acceptance criteria as unit/component assertions: No UI/API path removes a case object; archived object visible and not editable.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-003 |
| Open Technical Questions | None registered |

#### FN-CAS-04 — Record consent reference

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-04 |
| Function Name | Record consent reference |
| Related Requirement IDs | SEC-12; DATA-14 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Hold evidence of the lawful basis before any scan upload (SEC-12). Consent document stays outside Jude; Jude stores its reference. |
| Input Data | document_id (≤ 64), date (ISO date), scopes ⊆ {care, internal_qa, model_development, external_sharing} · Preconditions: Clinic admin; case active. |
| Input Data Structures | PUT /cases/{id}/consent-ref JSON · module baseline DS |
| Processing Algorithm | 1. Validate scopes ⊆ enumeration and 'care' ∈ scopes for upload eligibility.<br>2. Store new consent reference version (history kept); emit case.consent_ref_set. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Consent reference. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | Unknown scope → 422 INVALID_SCOPE.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CAS-01; FN-AUD-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-14; TC-SEC-12 · suites: VER-20, VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CAS-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Upload without consent reference returns CONSENT_REF_MISSING; change logged; scope values exactly as enumerated.<br>One negative test per error code: INVALID_SCOPE<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-14; TC-SEC-12 |
| Open Technical Questions | None registered |

#### FN-CAS-05 — Set secondary-use permission per scan

*User interaction · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-05 |
| Function Name | Set secondary-use permission per scan |
| Related Requirement IDs | DATA-14 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Record the permitted secondary use of each scan (default not_permitted). Ordered levels not_permitted < internal_qa < model_development < external_sharing; history kept. |
| Input Data | scan_id, level, consent reference id · Preconditions: Clinic admin; consent reference exists. |
| Input Data Structures | PUT /scans/{id}/secondary-use · module baseline DS |
| Processing Algorithm | 1. Level must be covered by the consent scopes of the referenced consent.<br>2. Append history row; emit scan.secondary_use_changed. |
| Mathematical Model | Dataset filter: include scan ⇔ rank(level) ≥ rank(required_level). |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Permission level. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | Technician call → 403.<br>Level beyond consent scope → 422 SCOPE_NOT_COVERED.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CAS-04 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-14 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CAS-05 (proposed id)<br>Acceptance criteria as unit/component assertions: New scan = not_permitted; technician change → 403; change logged.<br>One negative test per error code: SCOPE_NOT_COVERED<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-14 |
| Open Technical Questions | None registered |

#### FN-CAS-06 — Attach prescription document

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-06 |
| Function Name | Attach prescription document |
| Related Requirement IDs | FR-164; DATA-10; SEC-18; SEC-13 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Bind each helmet design to the physician's prescription file (DEC-022). Upload PDF/JPEG/PNG to the case; stored unmodified with SHA-256; never parsed into fields (DATA-10). |
| Input Data | File (PDF, JPEG or PNG), optional label · Preconditions: Case active; consent reference present; real-data gate open for real documents. |
| Input Data Structures | POST /cases/{id}/prescriptions multipart · module baseline DS |
| Processing Algorithm | 1. Detect type by signature (%PDF-, FFD8FF, 89504E47); other → 415 UNSUPPORTED_TYPE.<br>2. Enforce size limit (OQ-FS-26).<br>3. Store via FN-BLB-01; record {file_name, sha256, uploaded_at, uploaded_by}; emit case.prescription_attached.<br>4. Never extract text or metadata into structured fields. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Prescription record. |
| Output Data Structures | JSON {id, file_name, sha256, uploaded_at} · module baseline DS |
| Error Handling | Wrong type → 415.<br>Too large → 413.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-BLB-01; FN-AUD-01; FN-CAS-04 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-10; TC-FR-164; TC-SEC-13; TC-SEC-18 · suites: VER-12, VER-20, VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CAS-06 (proposed id)<br>Acceptance criteria as unit/component assertions: Downloaded file byte-identical to upload; approval without any attached file returns PRESCRIPTION_MISSING.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-10; TC-FR-164; TC-SEC-13; TC-SEC-18 |
| Open Technical Questions | OQ-FS-26; Missing data: Maximum prescription file size and the permission-matrix row for prescription endpoints are not specified (OQ-FS-26). |

#### FN-CAS-07 — View or download prescription document

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-07 |
| Function Name | View or download prescription document |
| Related Requirement IDs | FR-164; SEC-15; SEC-16 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Controlled, logged access to directly identifying documents. Streams the stored file; each access logged. |
| Input Data | prescription id · Preconditions: Authorised. |
| Input Data Structures | GET /prescriptions/{id}/file · module baseline DS |
| Processing Algorithm | 1. Authorise (case scope).<br>2. Log read (FN-AUD-02, prescription.read).<br>3. Stream with Content-Disposition file name J-xxxxxxxx_prescription_<n>.<ext>. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | File. |
| Output Data Structures | Original bytes · module baseline DS |
| Error Handling | Not accessible → 403.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CAS-06; FN-AUD-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-164; TC-SEC-15; TC-SEC-16 · suites: VER-12, VER-13, VER-20, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CAS-07 (proposed id)<br>Acceptance criteria as unit/component assertions: Each view/download creates one read event; file name carries pseudonymous case ID only.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-164; TC-SEC-15; TC-SEC-16 |
| Open Technical Questions | None registered |

#### FN-CAS-08 — Erase case at end of retention

*Operational procedure (software-supported) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-08 |
| Function Name | Erase case at end of retention |
| Related Requirement IDs | SEC-11; FR-003 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Operator procedure supported by API/worker jobs |
| Technical Purpose | Lawful erasure per the clinic contract (SEC-11) without breaking audit integrity. Controlled procedure: removes DB rows and stored files of a case from production and schedules backup purge; leaves a tombstone audit event. |
| Input Data | case_id, contract reference, confirmation phrase · Preconditions: Retention period of the contract reached (entered by admin); no active job. |
| Input Data Structures | POST /cases/{id}/erase · module baseline DS |
| Processing Algorithm | 1. Verify contract reference entered and typed confirmation equals the case ID.<br>2. In one transaction: delete case-linked domain rows (cascade), keep audit events but replace before/after summaries of that case with 'erased' (summaries never contain mesh data); append case.erased tombstone {case_id, time, user, contract_ref}.<br>3. Call FN-BLB-04 for exclusively referenced blobs.<br>4. Register backup purge task; record purge completion when backups older than the erasure roll off or are purged. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Erasure record. |
| Output Data Structures | JSON {case_id, erased_at, blob_purge_manifest_sha, backup_purge_due} · module baseline DS |
| Error Handling | Purge incomplete → state incomplete; retry; alert.<br>Policy EH-PROC (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-BLB-04; FN-AUD-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-003; TC-SEC-11 · suites: VER-20, VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CAS-08 (proposed id)<br>Acceptance criteria as unit/component assertions: After erasure no file or row of the case is retrievable via API or DB; tombstone present; backup purge record exists. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-003; TC-SEC-11 |
| Open Technical Questions | OQ-FS-07; Missing data: Hash-chain impact of removing summaries and the blob-store delete model need decision (OQ-FS-07). |

##### FN-CAS-08.1 — Authorisation and confirmation

*Operational procedure (software-supported) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-08.1 |
| Function Name | Authorisation and confirmation  (subfunction of FN-CAS-08 Erase case at end of retention) |
| Related Requirement IDs | Inherited from parent FN-CAS-08: SEC-11; FR-003 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Operator procedure supported by API/worker jobs |
| Technical Purpose | Contract reference and typed confirmation. |
| Input Data | Inherited from FN-CAS-08 |
| Input Data Structures | Inherited from FN-CAS-08 (DS-22 inputs) |
| Processing Algorithm | Contract reference and typed confirmation. |
| Mathematical Model | Inherited from FN-CAS-08 |
| Geometry Operations | Inherited from FN-CAS-08 |
| Output Data | Inherited from FN-CAS-08 |
| Output Data Structures | Inherited from FN-CAS-08 |
| Error Handling | Inherited from FN-CAS-08 |
| Performance Requirements | Inherited from FN-CAS-08 |
| Dependencies | Inherited from FN-CAS-08 |
| External Libraries | Inherited from FN-CAS-08 |
| Alternative Implementations | Inherited from FN-CAS-08 |
| Security Considerations | Inherited from FN-CAS-08 |
| Verification Strategy | T — verified within FN-CAS-08 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-CAS-08.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Contract reference and typed confirmation. |
| Integration Test Requirements | Inherited from FN-CAS-08 |
| Open Technical Questions | Inherited from FN-CAS-08 |

##### FN-CAS-08.2 — Record removal

*Operational procedure (software-supported) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-08.2 |
| Function Name | Record removal  (subfunction of FN-CAS-08 Erase case at end of retention) |
| Related Requirement IDs | Inherited from parent FN-CAS-08: SEC-11; FR-003 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Operator procedure supported by API/worker jobs |
| Technical Purpose | Case rows and erasable audit summaries. |
| Input Data | Inherited from FN-CAS-08 |
| Input Data Structures | Inherited from FN-CAS-08 (DS-22 inputs) |
| Processing Algorithm | Case rows and erasable audit summaries. |
| Mathematical Model | Inherited from FN-CAS-08 |
| Geometry Operations | Inherited from FN-CAS-08 |
| Output Data | Inherited from FN-CAS-08 |
| Output Data Structures | Inherited from FN-CAS-08 |
| Error Handling | Inherited from FN-CAS-08 |
| Performance Requirements | Inherited from FN-CAS-08 |
| Dependencies | Inherited from FN-CAS-08 |
| External Libraries | Inherited from FN-CAS-08 |
| Alternative Implementations | Inherited from FN-CAS-08 |
| Security Considerations | Inherited from FN-CAS-08 |
| Verification Strategy | T — verified within FN-CAS-08 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-CAS-08.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Case rows and erasable audit summaries. |
| Integration Test Requirements | Inherited from FN-CAS-08 |
| Open Technical Questions | Inherited from FN-CAS-08 |

##### FN-CAS-08.3 — Blob purge

*Operational procedure (software-supported) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-08.3 |
| Function Name | Blob purge  (subfunction of FN-CAS-08 Erase case at end of retention) |
| Related Requirement IDs | Inherited from parent FN-CAS-08: SEC-11; FR-003 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Operator procedure supported by API/worker jobs |
| Technical Purpose | FN-BLB-04 on exclusively referenced blobs. |
| Input Data | Inherited from FN-CAS-08 |
| Input Data Structures | Inherited from FN-CAS-08 (DS-22 inputs) |
| Processing Algorithm | FN-BLB-04 on exclusively referenced blobs. |
| Mathematical Model | Inherited from FN-CAS-08 |
| Geometry Operations | Inherited from FN-CAS-08 |
| Output Data | Inherited from FN-CAS-08 |
| Output Data Structures | Inherited from FN-CAS-08 |
| Error Handling | Inherited from FN-CAS-08 |
| Performance Requirements | Inherited from FN-CAS-08 |
| Dependencies | Inherited from FN-CAS-08 |
| External Libraries | Inherited from FN-CAS-08 |
| Alternative Implementations | Inherited from FN-CAS-08 |
| Security Considerations | Inherited from FN-CAS-08 |
| Verification Strategy | T — verified within FN-CAS-08 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-CAS-08.3 (proposed id)<br>Isolated test of this step with positive and negative cases: FN-BLB-04 on exclusively referenced blobs. |
| Integration Test Requirements | Inherited from FN-CAS-08 |
| Open Technical Questions | Inherited from FN-CAS-08 |

##### FN-CAS-08.4 — Backup purge tracking

*Operational procedure (software-supported) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-08.4 |
| Function Name | Backup purge tracking  (subfunction of FN-CAS-08 Erase case at end of retention) |
| Related Requirement IDs | Inherited from parent FN-CAS-08: SEC-11; FR-003 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Operator procedure supported by API/worker jobs |
| Technical Purpose | Due date and completion record. |
| Input Data | Inherited from FN-CAS-08 |
| Input Data Structures | Inherited from FN-CAS-08 (DS-22 inputs) |
| Processing Algorithm | Due date and completion record. |
| Mathematical Model | Inherited from FN-CAS-08 |
| Geometry Operations | Inherited from FN-CAS-08 |
| Output Data | Inherited from FN-CAS-08 |
| Output Data Structures | Inherited from FN-CAS-08 |
| Error Handling | Inherited from FN-CAS-08 |
| Performance Requirements | Inherited from FN-CAS-08 |
| Dependencies | Inherited from FN-CAS-08 |
| External Libraries | Inherited from FN-CAS-08 |
| Alternative Implementations | Inherited from FN-CAS-08 |
| Security Considerations | Inherited from FN-CAS-08 |
| Verification Strategy | T — verified within FN-CAS-08 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-CAS-08.4 (proposed id)<br>Isolated test of this step with positive and negative cases: Due date and completion record. |
| Integration Test Requirements | Inherited from FN-CAS-08 |
| Open Technical Questions | Inherited from FN-CAS-08 |

#### FN-CAS-09 — Record cohort descriptors (conditional)

*User interaction · MVP (conditional on OQ-AI-02) · Could · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-CAS-09 |
| Function Name | Record cohort descriptors (conditional) |
| Related Requirement IDs | DATA-18 |
| Architecture Component | C3/M03, C1/W02, W07 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Optional descriptors for representativeness, without identifiers. Age at scan in completed weeks, sex (incl. 'not recorded'), referral deformation pattern verbatim. |
| Input Data | age_weeks (int ≥ 0), sex enum, referral_pattern_text · Preconditions: Built only if owner + privacy specialist approve OQ-AI-02. |
| Input Data Structures | PUT /scans/{id}/cohort · module baseline DS |
| Processing Algorithm | 1. All fields optional with explicit 'not recorded'.<br>2. Referral field labelled 'as stated on referral, entered by user' (not computed). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Descriptor record. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | Negative age → 422.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-SCN-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method I · test cases: TC-DATA-18 · suites: VER-09 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-CAS-09 (proposed id)<br>Acceptance criteria as unit/component assertions: No DOB field; VER-09 wording lint passes.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-18 |
| Open Technical Questions | OQ-FS-36 |

## SS-03 — Scan intake and quality

### Module SCN — Scan intake, quality gate, cleanup records

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Domain Layer / Import/Export Layer; Validation Layer; Geometry Engine |
| Runtime and execution | C3 API (gates, records); C4 worker (parse, integrity, gate jobs) with sandboxed parse subprocess · Request + background jobs |
| Input data structures | File bytes; DS-01; DS-16 gate thresholds |
| Output data structures | scan rows; DS-02; gate results; cleanup op records; DS-19 artifacts |
| Interfaces | IF-01; IF-02; IF-03; IF-04; IF-11 |
| External libraries | Kernel (own) + LIB-NUMPY; LIB-SCIPY |
| Performance | PM-01…05 |
| Security | Untrusted input parsed only in the sandboxed worker child process (TD-16, SEC-07); size/face caps before allocation; real-data gate (SEC-17) |
| Integration tests | Upload → parse → confirmations → integrity → gate → cleanup → landmarks enabled; refusals leave case unchanged; corrupt/oversize/face-bomb fixtures |
| Alternatives | Client-side parsing (rejected ADR-001) |
| Versioning | integrity/1, gate result schema |

#### FN-SCN-01 — Upload scan file

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-01 |
| Function Name | Upload scan file |
| Related Requirement IDs | FR-010; FR-011; FR-015; SEC-07; SEC-12; SEC-17; NFR-03 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Accept a mesh file into a case and keep the original unmodified. Multipart upload through the proxy size cap; original stored with SHA-256; parse job enqueued. |
| Input Data | File (.stl/.obj/.ply, any case), declared device/software optional · Preconditions: Case active; consent reference present (SEC-12); real_patient_data_enabled = true or environment flagged synthetic/test (SEC-17). |
| Input Data Structures | POST /cases/{id}/scans multipart/form-data · module baseline DS |
| Processing Algorithm | 1. Gate checks in order: CASE_ARCHIVED, CONSENT_REF_MISSING, REAL_DATA_DISABLED.<br>2. Proxy and API reject bodies > S MB (NFR-03) → 413 FILE_TOO_LARGE.<br>3. Stream to blob store (FN-BLB-01) computing SHA-256; create scan {status=uploaded, original_sha, file_name, size, uploaded_by/at}.<br>4. Enqueue parse job (FN-SCN-02); emit scan.uploaded; return 202 {scan_id, job_id}. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Scan record (uploaded), job. |
| Output Data Structures | HTTP 202 JSON · module baseline DS |
| Error Handling | 413 FILE_TOO_LARGE; 409 CONSENT_REF_MISSING; 409 REAL_DATA_DISABLED. Case object count unchanged on any refusal.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-BLB-01; FN-JOB-01; FN-CAS-04; FN-CFG-08 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Client-side parsing (rejected ADR-001) |
| Security Considerations | Module baseline · Untrusted input path (SEC-07) |
| Verification Strategy | Method T · test cases: TC-FR-010; TC-FR-011; TC-FR-015; TC-SEC-07; TC-SEC-12; TC-SEC-17 · suites: VER-08, VER-20, VER-21, VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-SCN-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Downloaded original is byte-identical; refusals leave the case unchanged.<br>One negative test per error code: CONSENT_REF_MISSING, FILE_TOO_LARGE, REAL_DATA_DISABLED<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-010; TC-FR-011; TC-FR-015; TC-SEC-07; TC-SEC-12; TC-SEC-17 |
| Open Technical Questions | OQ-FS-29; TQ-13; Missing data: S (MB) and N (triangles) of NFR-03 are not yet set (OQ-G4, OQ-FS-29). |

#### FN-SCN-02 — Parse and import mesh (job)

*Background job · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-02 |
| Function Name | Parse and import mesh (job) |
| Related Requirement IDs | FR-010; FR-015; INT-01; INT-02; INT-03; INT-08; SEC-07 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Worker job; parsing delegated to sandboxed child process (TD-16) |
| Technical Purpose | Turn the uploaded bytes into a validated indexed triangle mesh. Worker job in the sandbox (SEC-07): format detection, parsing, triangulation, exact vertex merge; stores scan_original artifact (in file units). |
| Input Data | original_sha, limits {max_faces, max_bytes} · Preconditions: Scan uploaded. |
| Input Data Structures | Job payload · module baseline DS |
| Processing Algorithm | 1. FN-KIO-01 detect format by signature.<br>2. FN-KIO-02/03/04 parse.<br>3. FN-KIO-05 build indexed mesh, validate finite coordinates, index range, ≥1 face.<br>4. Store arrays artifact kind=scan_original (units=file_units) with stats (V, F, polygons triangulated, ignored attributes).<br>5. Completion handler: scan.status=parsed; import report; notices for ignored textures/colour; emit scan.parsed.<br>Algorithms: ALG-01 File format detection by signature |
| Mathematical Model | ALG-01: Content sniffing: PLY magic "ply\n" + format line; binary STL iff 84 + 50*n == file size where n = uint32 at offset 80; ASCII STL iff first non-blank token "solid" AND a "facet" token within the first 4 KiB AND the size rule fails; OBJ iff lines begin with … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-01) |
| Geometry Operations | ALG-01 File format detection by signature [mesh import] |
| Output Data | scan_original artifact; import report. |
| Output Data Structures | npz V float64[N,3], F int32[M,3]; JSON report · module baseline DS |
| Error Handling | FILE_UNREADABLE (422), FILE_EMPTY (422), FACE_LIMIT (413), NON_FINITE_COORDINATES (422); scan.status=rejected with reason, no derived objects.<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-01: O(1) on the 4 KiB prefix |
| Dependencies | Functions: FN-KIO-01; FN-KIO-02; FN-KIO-03; FN-KIO-04; FN-KIO-05; FN-JOB-02 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-01: Trust extension (rejected: FR-010); libmagic (adds C dependency, no mesh rules). |
| Security Considerations | Module baseline · Untrusted input path (SEC-07) |
| Verification Strategy | Method T · test cases: TC-FR-010; TC-FR-015; TC-INT-01; TC-INT-02; TC-INT-03; TC-INT-08; TC-SEC-07 · suites: VER-08, VER-20, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-SCN-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Reference files of each format import with V/F counts equal to a reference parser; corrupt/empty/oversize files give distinct reasons.<br>ALG-01: One fixture per format incl. binary STL with "solid" header; empty and random-bytes files. Invariants: Detection independent of file name.<br>One negative test per error code: FACE_LIMIT, FILE_EMPTY, FILE_UNREADABLE, NON_FINITE_COORDINATES |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-010; TC-FR-015; TC-INT-01; TC-INT-02; TC-INT-03; TC-INT-08; TC-SEC-07 |
| Open Technical Questions | OQ-FS-31; TQ-02 |

##### FN-SCN-02.1 — Sandboxed execution

*Background job · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-02.1 |
| Function Name | Sandboxed execution  (subfunction of FN-SCN-02 Parse and import mesh (job)) |
| Related Requirement IDs | Inherited from parent FN-SCN-02: FR-010; FR-015; INT-01; INT-02; INT-03; INT-08; SEC-07 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Worker job; parsing delegated to sandboxed child process (TD-16) |
| Technical Purpose | Non-root, read-only FS, no egress, CPU/memory caps (SEC-07). |
| Input Data | Inherited from FN-SCN-02 |
| Input Data Structures | Inherited from FN-SCN-02 (File bytes; DS-01; DS-16 gate thresholds) |
| Processing Algorithm | Non-root, read-only FS, no egress, CPU/memory caps (SEC-07). |
| Mathematical Model | Inherited from FN-SCN-02 |
| Geometry Operations | Inherited from FN-SCN-02 |
| Output Data | Inherited from FN-SCN-02 |
| Output Data Structures | Inherited from FN-SCN-02 |
| Error Handling | Inherited from FN-SCN-02 |
| Performance Requirements | Inherited from FN-SCN-02 |
| Dependencies | Inherited from FN-SCN-02 |
| External Libraries | Inherited from FN-SCN-02 |
| Alternative Implementations | Inherited from FN-SCN-02 |
| Security Considerations | Inherited from FN-SCN-02 |
| Verification Strategy | T — verified within FN-SCN-02 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-SCN-02.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Non-root, read-only FS, no egress, CPU/memory caps (SEC-07). |
| Integration Test Requirements | Inherited from FN-SCN-02 |
| Open Technical Questions | TQ-20; TQ-02 |

##### FN-SCN-02.2 — Parse dispatch

*Background job · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-02.2 |
| Function Name | Parse dispatch  (subfunction of FN-SCN-02 Parse and import mesh (job)) |
| Related Requirement IDs | Inherited from parent FN-SCN-02: FR-010; FR-015; INT-01; INT-02; INT-03; INT-08; SEC-07 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Worker job; parsing delegated to sandboxed child process (TD-16) |
| Technical Purpose | FN-KIO-01 then the matching parser. |
| Input Data | Inherited from FN-SCN-02 |
| Input Data Structures | Inherited from FN-SCN-02 (File bytes; DS-01; DS-16 gate thresholds) |
| Processing Algorithm | FN-KIO-01 then the matching parser. — implemented by ALG-01 |
| Mathematical Model | ALG-01: Content sniffing: PLY magic "ply\n" + format line; binary STL iff 84 + 50*n == file size where n = uint32 at offset 80; ASCII STL iff first non-blank token "solid" AND a "facet" token within the first 4 KiB AND the size rule fails; OBJ iff lines begin with … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-01) |
| Geometry Operations | ALG-01 File format detection by signature [mesh import] |
| Output Data | Inherited from FN-SCN-02 |
| Output Data Structures | Inherited from FN-SCN-02 |
| Error Handling | Inherited from FN-SCN-02 |
| Performance Requirements | Inherited from FN-SCN-02 — complexity: ALG-01: O(1) on the 4 KiB prefix |
| Dependencies | Inherited from FN-SCN-02 |
| External Libraries | Inherited from FN-SCN-02 |
| Alternative Implementations | ALG-01: Trust extension (rejected: FR-010); libmagic (adds C dependency, no mesh rules). |
| Security Considerations | Inherited from FN-SCN-02 |
| Verification Strategy | T — verified within FN-SCN-02 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-SCN-02.2 (proposed id)<br>Isolated test of this step with positive and negative cases: FN-KIO-01 then the matching parser.<br>ALG-01: One fixture per format incl. binary STL with "solid" header; empty and random-bytes files. Invariants: Detection independent of file name. |
| Integration Test Requirements | Inherited from FN-SCN-02 |
| Open Technical Questions | TQ-02 |

##### FN-SCN-02.3 — Import report

*Background job · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-02.3 |
| Function Name | Import report  (subfunction of FN-SCN-02 Parse and import mesh (job)) |
| Related Requirement IDs | Inherited from parent FN-SCN-02: FR-010; FR-015; INT-01; INT-02; INT-03; INT-08; SEC-07 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Worker job; parsing delegated to sandboxed child process (TD-16) |
| Technical Purpose | Counts, triangulated polygons, ignored attributes, notices. |
| Input Data | Inherited from FN-SCN-02 |
| Input Data Structures | Inherited from FN-SCN-02 (File bytes; DS-01; DS-16 gate thresholds) |
| Processing Algorithm | Counts, triangulated polygons, ignored attributes, notices. |
| Mathematical Model | Inherited from FN-SCN-02 |
| Geometry Operations | Inherited from FN-SCN-02 |
| Output Data | Inherited from FN-SCN-02 |
| Output Data Structures | Inherited from FN-SCN-02 |
| Error Handling | Inherited from FN-SCN-02 |
| Performance Requirements | Inherited from FN-SCN-02 |
| Dependencies | Inherited from FN-SCN-02 |
| External Libraries | Inherited from FN-SCN-02 |
| Alternative Implementations | Inherited from FN-SCN-02 |
| Security Considerations | Inherited from FN-SCN-02 |
| Verification Strategy | T — verified within FN-SCN-02 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-SCN-02.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Counts, triangulated polygons, ignored attributes, notices. |
| Integration Test Requirements | Inherited from FN-SCN-02 |
| Open Technical Questions | TQ-02 |

#### FN-SCN-03 — Confirm scan-to-case association

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-03 |
| Function Name | Confirm scan-to-case association |
| Related Requirement IDs | FR-170 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Prevent wrong-case use of an infant scan (R-37). Shows case ID, clinic reference and scan file name/time; technician confirms. |
| Input Data | scan_id, confirm=true · Preconditions: Scan parsed. |
| Input Data Structures | POST /scans/{id}/confirm-case · module baseline DS |
| Processing Algorithm | 1. Display case_id, clinic_ref, file name, upload time, thumbnail.<br>2. On confirm set case_confirmed_by/at; emit scan.case_confirmed.<br>3. All downstream endpoints check case_confirmed → else 409 CASE_ASSOC_NOT_CONFIRMED. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Confirmed flag. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | Already confirmed → idempotent 200.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-SCN-02; FN-AUD-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Client-side parsing (rejected ADR-001) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-170 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-SCN-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Unconfirmed scan: landmark/measure/design calls return CASE_ASSOC_NOT_CONFIRMED; one event per confirmation.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-170 |
| Open Technical Questions | None registered |

#### FN-SCN-04 — Confirm length unit and convert to millimetres

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-04 |
| Function Name | Confirm length unit and convert to millimetres |
| Related Requirement IDs | FR-012; SAF-04 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Remove unit ambiguity of STL/OBJ/PLY before any geometry use (R-03). Technician selects mm/cm/m/inch; system shows the bounding box under each candidate and, after confirmation, creates scan_mm by exact scaling. |
| Input Data | unit ∈ {mm, cm, m, inch} · Preconditions: Case association confirmed. |
| Input Data Structures | POST /scans/{id}/confirm-unit {unit} · module baseline DS |
| Processing Algorithm | 1. Before confirmation display bbox extents (sorted) for all four units side by side; no unit is preselected (OQ-FS-15).<br>2. On confirm: enqueue FN-KFR-01 with factor s; store scan_mm artifact; record op units.to_mm {unit, s}; emit scan.unit_confirmed.<br>3. Then enqueue integrity job (FN-SCN-05) and plausible-size check (FN-SCN-08).<br>Algorithms: ALG-30 Unit scaling to millimetres |
| Mathematical Model | s ∈ {1, 10, 1000, 25.4}; V_mm = s·V_file (exact float64 multiplication).<br>ALG-30: V_mm = s·V with s ∈ {1 (mm), 10 (cm), 1000 (m), 25.4 (inch)} from the technician-confirmed unit; recorded as op units.to_mm; frame F_scan = F_file scaled, same axes. |
| Geometry Operations | ALG-30 Unit scaling to millimetres [coordinate systems] |
| Output Data | scan_mm artifact. |
| Output Data Structures | npz (mm) · module baseline DS |
| Error Handling | Not case-confirmed → 409 CASE_ASSOC_NOT_CONFIRMED.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-30: O(n) |
| Dependencies | Functions: FN-SCN-03; FN-KFR-01 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-30: Unit heuristic from bbox (rejected for silent use; FR-012 shows all four bboxes, OQ-FS-15). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-012; TC-SAF-04 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-SCN-04 (proposed id)<br>Acceptance criteria as unit/component assertions: With unit unconfirmed, landmark/measure/design controls disabled in UI and API; ×10/×25.4/×1000 conversions exact; confirmation logged.<br>ALG-30: Each unit factor. Invariants: Angles and topology unchanged.<br>One negative test per error code: CASE_ASSOC_NOT_CONFIRMED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-012; TC-SAF-04 |
| Open Technical Questions | OQ-FS-15 |

#### FN-SCN-05 — Produce integrity report (job)

*Background job · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-05 |
| Function Name | Produce integrity report (job) |
| Related Requirement IDs | FR-013; FR-171; UR-08 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Report scan integrity metrics before landmarks or measurements are possible. Runs kernel validation on scan_mm. |
| Input Data | scan_mm artifact, ε_area · Preconditions: Unit confirmed. |
| Input Data Structures | Job payload · module baseline DS |
| Processing Algorithm | 1. Run FN-KVL-01 (edges, boundary loops, longest perimeter mm, non-manifold edges/vertices), FN-KVL-02 (degenerate faces), FN-KVL-03 (components), FN-KVL-04 (orientation consistency), FN-KVL-05 (self-intersecting pairs), FN-KVL-06 (bbox, watertight flag).<br>2. Store integrity_report {metrics, kernel_version, ε_area}.<br>3. Trigger FN-SCN-06. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | No own geometry computation; invokes kernel functions FN-KVL-01, FN-KVL-02, FN-KVL-03, FN-KVL-04, FN-KVL-05, FN-KVL-06 through IF-02/IF-03. |
| Output Data | Integrity report. |
| Output Data Structures | JSON {triangles, vertices, boundary_loops, longest_loop_mm, non_manifold_edges, non_manifold_vertices, degenerate_faces, components, self_intersecting_pairs, bbox_mm[3], orientation_consistent} · module baseline DS |
| Error Handling | Kernel failure → job failed; scan stays at 'unit_confirmed' with error shown.<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-KVL-01; FN-KVL-02; FN-KVL-03; FN-KVL-04; FN-KVL-05; FN-KVL-06; FN-SCN-04 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Client-side parsing (rejected ADR-001) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-013; TC-FR-171 · suites: VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-SCN-05 (proposed id)<br>Acceptance criteria as unit/component assertions: On VER-08 defect meshes every seeded defect is reported with the correct count; clean phantoms report 0 self-intersections.<br>Job handler tests with fake kernel results: success, deterministic rejection, retryable failure, idempotent re-run. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-013; TC-FR-171 |
| Open Technical Questions | OQ-FS-13; Missing data: ε_area kernel constant not yet fixed by the VER-01 numerical analysis (OQ-FS-13). |

#### FN-SCN-06 — Evaluate quality gate

*Background job · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-06 |
| Function Name | Evaluate quality gate |
| Related Requirement IDs | FR-014; UR-08 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Block or warn on integrity metrics using clinic thresholds (values confidential, DEC-029). Per-metric comparison with action block\|warn from configuration quality_gate. |
| Input Data | Integrity metrics; quality_gate config · Preconditions: Integrity report exists; thresholds set (else CONFIG_NOT_SET). |
| Input Data Structures | Internal · module baseline DS |
| Processing Algorithm | 1. For each configured metric m with threshold T and action a: result = pass if value ≤ T else a.<br>2. Overall = block if any block; warn if any warn; else pass.<br>3. Store gate_result {config_version, per_metric[]}; emit scan.gate_evaluated.<br>4. Block → no downstream step allowed (GATE_BLOCKED); warn → downstream requires FN-SCN-07 override. |
| Mathematical Model | result_m = pass ⇔ value_m ≤ T_m (all MVP metrics are counts or lengths where larger is worse). |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Gate result. |
| Output Data Structures | JSON {overall, per_metric[{metric, value, threshold, action, result}]} · module baseline DS |
| Error Handling | Any NOT_SET threshold → CONFIG_NOT_SET; pilot start requires none.<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-SCN-05; FN-CFG-04 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Client-side parsing (rejected ADR-001) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-014 · suites: VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-SCN-06 (proposed id)<br>Acceptance criteria as unit/component assertions: With test-only thresholds a metric at T passes and at T+1 unit triggers the configured action.<br>One negative test per error code: CONFIG_NOT_SET, NOT_SET<br>Job handler tests with fake kernel results: success, deterministic rejection, retryable failure, idempotent re-run. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-014 |
| Open Technical Questions | None registered |

#### FN-SCN-07 — Override a quality-gate warning

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-07 |
| Function Name | Override a quality-gate warning |
| Related Requirement IDs | SAF-05; DATA-22; DATA-17; FR-014 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Allow informed continuation with a recorded reason (SAF-05). Typed reason ≥ 10 characters plus a reason category from the clinic list (DATA-22). |
| Input Data | metric(s), reason text, reason category · Preconditions: Gate overall = warn. |
| Input Data Structures | POST /scans/{id}/gate-override · module baseline DS |
| Processing Algorithm | 1. Refuse for block → 409 GATE_BLOCKED.<br>2. len(trim(reason)) < 10 → 422 REASON_TOO_SHORT; missing category → 422 CATEGORY_REQUIRED.<br>3. Store override; set scan outcome tag accepted_with_override (DATA-17); emit scan.gate_override. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Override record. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | See logic.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-SCN-06; FN-AUD-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Client-side parsing (rejected ADR-001) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-17; TC-DATA-22; TC-FR-014; TC-SAF-05 · suites: VER-08, VER-13, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-SCN-07 (proposed id)<br>Acceptance criteria as unit/component assertions: Override without reason refused; with reason logged including category.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-17; TC-DATA-22; TC-FR-014; TC-SAF-05 |
| Open Technical Questions | None registered |

#### FN-SCN-08 — Plausible head-size warning

*Background job · MVP · Should · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-08 |
| Function Name | Plausible head-size warning |
| Related Requirement IDs | SAF-04 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Second barrier against unit errors. Compares bbox (mm) with configured plausible range. |
| Input Data | bbox_mm, plausible_bbox_mm {min[3], max[3]} · Preconditions: Unit confirmed. |
| Input Data Structures | Internal · module baseline DS |
| Processing Algorithm | 1. Sort bbox extents descending e₁ ≥ e₂ ≥ e₃ (no frame exists yet); compare against sorted min/max.<br>2. Outside → warning shown with configured range; NOT_SET → 'check not configured' notice (not a block). |
| Mathematical Model | warn ⇔ ∃i: eᵢ < minᵢ ∨ eᵢ > maxᵢ (sorted extents). |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Warning flag. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | —<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-SCN-04; FN-CFG-04 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Client-side parsing (rejected ADR-001) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-SAF-04 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-SCN-08 (proposed id)<br>Acceptance criteria as unit/component assertions: Mesh scaled ×10 triggers the warning.<br>Job handler tests with fake kernel results: success, deterministic rejection, retryable failure, idempotent re-run. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SAF-04 |
| Open Technical Questions | OQ-FS-22 |

#### FN-SCN-09 — Record and lock scan metadata

*User interaction · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-09 |
| Function Name | Record and lock scan metadata |
| Related Requirement IDs | DATA-01; FR-181 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Provenance of acquisition; locked after first measurement. Device, software+version, operator, acquisition date, cap used, posture, attempts; explicit 'unknown'. |
| Input Data | DATA-01 fields · Preconditions: Scan exists. |
| Input Data Structures | PUT /scans/{id}/metadata · module baseline DS |
| Processing Algorithm | 1. Every field required as value or 'unknown' (no empty).<br>2. If a measurement set exists for the scan → 409 METADATA_LOCKED; corrections via POST …/metadata-corrections {field, value, reason} linked to original.<br>3. Emit scan.metadata_changed. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Metadata. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | 409 METADATA_LOCKED.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-SCN-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Client-side parsing (rejected ADR-001) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-01; TC-FR-181 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-SCN-09 (proposed id)<br>Acceptance criteria as unit/component assertions: 'unknown' stored explicitly; PUT after first measurement returns METADATA_LOCKED; correction stored with reason and link.<br>One negative test per error code: METADATA_LOCKED<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-01; TC-FR-181 |
| Open Technical Questions | None registered |

#### FN-SCN-10 — Tag scan outcome

*User interaction · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-10 |
| Function Name | Tag scan outcome |
| Related Requirement IDs | DATA-17; DATA-22 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Record accepted / accepted_with_override / rescanned with reason and link. Labels for re-scan burden and future AI (DATA-17). |
| Input Data | tag, reason category (rescanned), superseding_scan_id · Preconditions: Gate evaluated. |
| Input Data Structures | PUT /scans/{id}/outcome · module baseline DS |
| Processing Algorithm | 1. rescanned requires reason category and a superseding scan in the same case.<br>2. Emit scan.outcome_tagged. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Tag. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | Missing reason/link → 422.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-SCN-06 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Client-side parsing (rejected ADR-001) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-17; TC-DATA-22 · suites: VER-13, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-SCN-10 (proposed id)<br>Acceptance criteria as unit/component assertions: Rescanned tag without reason and link refused; tag changes audited.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-17; TC-DATA-22 |
| Open Technical Questions | None registered |

#### FN-SCN-11 — Manage cleanup operations

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-11 |
| Function Name | Manage cleanup operations |
| Related Requirement IDs | FR-020; FR-021; FR-022; FR-023; DATA-16 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Non-destructive, recorded cleanup of the scan (remove regions, optional hole fill and decimation). Cleanup ops are parameterised operations applied to scan_mm in sequence producing scan_prepared; undo last, disable any. |
| Input Data | op type ∈ {cleanup.remove_faces, cleanup.fill_holes, cleanup.decimate}, params · Preconditions: Gate passed or warn overridden; unit and case confirmed. |
| Input Data Structures | POST /scans/{id}/cleanup-ops; PATCH …/{seq} {enabled}; POST …/undo · module baseline DS |
| Processing Algorithm | 1. Validate op params (FN-KRP-04).<br>2. Append op with seq; enqueue replay of cleanup chain (FN-KRP-01) → scan_prepared artifact.<br>3. remove_faces params reference face IDs of the *input* of that op; the removed set is retained (DATA-16).<br>4. Disable/enable/undo regenerate scan_prepared; dependent landmark sets/frames/designs become superseded (FN-ANA-05).<br>5. Emit cleanup.op_changed.<br>Algorithms: ALG-22 Mesh repair policy (explicit recorded repair only); ALG-15 Recorded face removal and compaction (mesh cleaning); ALG-43 Region segmentation (MVP: technician-defined regions); ALG-53 Op-log replay engine with content-addressed cache |
| Mathematical Model | ALG-22: No silent repair (05 §6.2). Repair = composition of recorded ops chosen by the technician: remove faces/components (ALG-15), fill selected holes (ALG-16), optional orientation normalisation (ALG-10, OQ-FS-37). Each op is versioned, replayable and visible … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-22)<br>ALG-15: Remove a set of face ids (from UI selection or component labels) and compact vertices keeping relative order; record (op type, op_version, face_ids on input mesh) so replay is exact (FR-020, FR-023).<br>ALG-43: MVP regions are explicit: (a) face sets from UI brush/lasso selection resolved on the server against full-resolution face ids; (b) disc/ellipse regions defined by an anchored centre and Euclidean radius (A-15); (c) angular sectors in F_anat (ALG-34). No … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-43) |
| Geometry Operations | ALG-22 Mesh repair policy (explicit recorded repair only) [mesh repair]; ALG-15 Recorded face removal and compaction (mesh cleaning) [mesh cleaning / mesh repair]; ALG-43 Region segmentation (MVP: technician-defined regions) [region segmentation]; ALG-53 Op-log replay engine with content-addressed cache [design versions / reproducibility] |
| Output Data | scan_prepared artifact. |
| Output Data Structures | npz + op list · module baseline DS |
| Error Handling | GATE_NOT_PASSED; UNIT_NOT_CONFIRMED; op rejected by kernel → op status rejected, previous scan_prepared kept.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-22: Sum of ops; ALG-15: O(m + n); ALG-43: O(selection · log m); ALG-53: Σ op costs; edit of op k recomputes ops k…n only |
| Dependencies | Functions: FN-KOP-01; FN-KOP-02; FN-KOP-03; FN-KRP-01; FN-ANA-05 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-22: Automatic repair (pymeshfix — AGPL-3.0 per PyPI, rejected; MeshLab filters — GPL).; ALG-15: Region growing by curvature (post-MVP segmentation, ALG-43).; ALG-43: Geodesic distance regions (potpourri3d MIT heat method, libigl exact geodesics MPL-2.0) — post-MVP. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-16; TC-FR-020; TC-FR-021; TC-FR-022; TC-FR-023 · suites: VER-07, VER-08, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-SCN-11 (proposed id)<br>Acceptance criteria as unit/component assertions: Disabling all cleanup ops reproduces the scan_mm hash; re-application yields identical hash.<br>ALG-22: Op list replay equality. Invariants: Disable all ops → original hash.<br>ALG-15: Remove one face; remove a component. Invariants: Remaining face coordinates bit-identical.<br>ALG-43: Disc membership on plane. Invariants: Selection resolved on full mesh is the stored truth.<br>One negative test per error code: GATE_NOT_PASSED, UNIT_NOT_CONFIRMED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-16; TC-FR-020; TC-FR-021; TC-FR-022; TC-FR-023 |
| Open Technical Questions | OQ-FS-16; OQ-FS-17 |

##### FN-SCN-11.1 — Region selection to face IDs

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-11.1 |
| Function Name | Region selection to face IDs  (subfunction of FN-SCN-11 Manage cleanup operations) |
| Related Requirement IDs | Inherited from parent FN-SCN-11: FR-020; FR-021; FR-022; FR-023; DATA-16 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | UI selection resolved to face IDs on the full-resolution input (FN-UIX-05). |
| Input Data | Inherited from FN-SCN-11 |
| Input Data Structures | Inherited from FN-SCN-11 (File bytes; DS-01; DS-16 gate thresholds) |
| Processing Algorithm | UI selection resolved to face IDs on the full-resolution input (FN-UIX-05). — implemented by ALG-15, ALG-43 |
| Mathematical Model | ALG-15: Remove a set of face ids (from UI selection or component labels) and compact vertices keeping relative order; record (op type, op_version, face_ids on input mesh) so replay is exact (FR-020, FR-023).<br>ALG-43: MVP regions are explicit: (a) face sets from UI brush/lasso selection resolved on the server against full-resolution face ids; (b) disc/ellipse regions defined by an anchored centre and Euclidean radius (A-15); (c) angular sectors in F_anat (ALG-34). No … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-43) |
| Geometry Operations | ALG-15 Recorded face removal and compaction (mesh cleaning) [mesh cleaning / mesh repair]; ALG-43 Region segmentation (MVP: technician-defined regions) [region segmentation] |
| Output Data | Inherited from FN-SCN-11 |
| Output Data Structures | Inherited from FN-SCN-11 |
| Error Handling | Inherited from FN-SCN-11 |
| Performance Requirements | Inherited from FN-SCN-11 — complexity: ALG-15: O(m + n); ALG-43: O(selection · log m) |
| Dependencies | Inherited from FN-SCN-11 |
| External Libraries | Inherited from FN-SCN-11 |
| Alternative Implementations | ALG-15: Region growing by curvature (post-MVP segmentation, ALG-43).; ALG-43: Geodesic distance regions (potpourri3d MIT heat method, libigl exact geodesics MPL-2.0) — post-MVP. |
| Security Considerations | Inherited from FN-SCN-11 |
| Verification Strategy | T — verified within FN-SCN-11 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-SCN-11.1 (proposed id)<br>Isolated test of this step with positive and negative cases: UI selection resolved to face IDs on the full-resolution input (FN-UIX-05).<br>ALG-15: Remove one face; remove a component. Invariants: Remaining face coordinates bit-identical.<br>ALG-43: Disc membership on plane. Invariants: Selection resolved on full mesh is the stored truth. |
| Integration Test Requirements | Inherited from FN-SCN-11 |
| Open Technical Questions | Inherited from FN-SCN-11 |

##### FN-SCN-11.2 — Cleanup replay

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-11.2 |
| Function Name | Cleanup replay  (subfunction of FN-SCN-11 Manage cleanup operations) |
| Related Requirement IDs | Inherited from parent FN-SCN-11: FR-020; FR-021; FR-022; FR-023; DATA-16 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Deterministic evaluation of enabled ops. |
| Input Data | Inherited from FN-SCN-11 |
| Input Data Structures | Inherited from FN-SCN-11 (File bytes; DS-01; DS-16 gate thresholds) |
| Processing Algorithm | Deterministic evaluation of enabled ops. — implemented by ALG-15, ALG-53 |
| Mathematical Model | ALG-15: Remove a set of face ids (from UI selection or component labels) and compact vertices keeping relative order; record (op type, op_version, face_ids on input mesh) so replay is exact (FR-020, FR-023).<br>ALG-53: Geometry = fold(ops, scan_original): stage 1 original → units.to_mm → enabled cleanup ops → scan_prepared; stage 2 enabled design ops in order (closure as pinned terminal op if OQ-FS-01 = b). Cache key per op = SHA-256(input geometry sha ‖ op type ‖ … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-53) |
| Geometry Operations | ALG-15 Recorded face removal and compaction (mesh cleaning) [mesh cleaning / mesh repair]; ALG-53 Op-log replay engine with content-addressed cache [design versions / reproducibility] |
| Output Data | Inherited from FN-SCN-11 |
| Output Data Structures | Inherited from FN-SCN-11 |
| Error Handling | Inherited from FN-SCN-11 |
| Performance Requirements | Inherited from FN-SCN-11 — complexity: ALG-15: O(m + n); ALG-53: Σ op costs; edit of op k recomputes ops k…n only |
| Dependencies | Inherited from FN-SCN-11 |
| External Libraries | Inherited from FN-SCN-11 |
| Alternative Implementations | ALG-15: Region growing by curvature (post-MVP segmentation, ALG-43).; ALG-53: Snapshot geometry per version only (loses replay). |
| Security Considerations | Inherited from FN-SCN-11 |
| Verification Strategy | T — verified within FN-SCN-11 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-SCN-11.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Deterministic evaluation of enabled ops.<br>ALG-15: Remove one face; remove a component. Invariants: Remaining face coordinates bit-identical.<br>ALG-53: Replay of fixture op lists. Invariants: Replay(ops) independent of cache state. |
| Integration Test Requirements | Inherited from FN-SCN-11 |
| Open Technical Questions | Inherited from FN-SCN-11 |

##### FN-SCN-11.3 — Undo/disable

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-11.3 |
| Function Name | Undo/disable  (subfunction of FN-SCN-11 Manage cleanup operations) |
| Related Requirement IDs | Inherited from parent FN-SCN-11: FR-020; FR-021; FR-022; FR-023; DATA-16 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Last op undo; per-op enable flag. |
| Input Data | Inherited from FN-SCN-11 |
| Input Data Structures | Inherited from FN-SCN-11 (File bytes; DS-01; DS-16 gate thresholds) |
| Processing Algorithm | Last op undo; per-op enable flag. |
| Mathematical Model | Inherited from FN-SCN-11 |
| Geometry Operations | Inherited from FN-SCN-11 |
| Output Data | Inherited from FN-SCN-11 |
| Output Data Structures | Inherited from FN-SCN-11 |
| Error Handling | Inherited from FN-SCN-11 |
| Performance Requirements | Inherited from FN-SCN-11 |
| Dependencies | Inherited from FN-SCN-11 |
| External Libraries | Inherited from FN-SCN-11 |
| Alternative Implementations | Inherited from FN-SCN-11 |
| Security Considerations | Inherited from FN-SCN-11 |
| Verification Strategy | T — verified within FN-SCN-11 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-SCN-11.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Last op undo; per-op enable flag. |
| Integration Test Requirements | Inherited from FN-SCN-11 |
| Open Technical Questions | Inherited from FN-SCN-11 |

#### FN-SCN-12 — Download original scan

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-SCN-12 |
| Function Name | Download original scan |
| Related Requirement IDs | FR-011; SEC-15; SEC-16 |
| Architecture Component | C3/M05, C4, C1/W02 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Return the byte-identical original (FR-011). Logged download. |
| Input Data | scan_id · Preconditions: Authorised. |
| Input Data Structures | GET /scans/{id}/original · module baseline DS |
| Processing Algorithm | 1. Authorise; log read; stream original with file name J-xxxxxxxx_scan_<n>.<ext>. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | File. |
| Output Data Structures | Original bytes · module baseline DS |
| Error Handling | 403 if not accessible.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-BLB-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Client-side parsing (rejected ADR-001) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-011; TC-SEC-15; TC-SEC-16 · suites: VER-12, VER-13, VER-20, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-SCN-12 (proposed id)<br>Acceptance criteria as unit/component assertions: Byte-identical download; hash shown in case view.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-011; TC-SEC-15; TC-SEC-16 |
| Open Technical Questions | None registered |

## SS-04 — Geometry kernel (pure operations)

### Module KIO — Kernel I/O

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Import/Export Layer / Geometry Engine |
| Runtime and execution | C4 worker process (pure function, single-threaded numerics); never in C3 request threads except hashing helpers · Pure function called by jobs |
| Input data structures | DS-01 + typed params (DS-03 schema) |
| Output data structures | DS-05 (outputs + report) |
| Interfaces | IF-03 |
| External libraries | LIB-NUMPY; LIB-SCIPY |
| Performance | Complexity per ALG; wall-time budgets TBD via BM-01/BM-02 (PM-04…08) |
| Security | No I/O, network, clock or randomness (07 §4.3); input caps enforced by callers; parsers bounded in memory and tokens (SEC-07) |
| Integration tests | Called through the job runner on fixture designs; results persisted and re-read; determinism over 100 runs (VER-07) |
| Alternatives | See ALGORITHM_CATALOG alternatives |
| Versioning | op_version per op; kernel_version + image digest per result |

#### FN-KIO-01 — Detect file format by signature

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KIO-01 |
| Function Name | Detect file format by signature |
| Related Requirement IDs | FR-010; FR-015; INT-01; INT-02; INT-03 |
| Architecture Component | C4/K01 · Import/Export Layer · Separate sandboxed child process of the worker (rlimits CPU/memory, read-only FS, no network) — TD-16 |
| Technical Purpose | Choose the parser from file content, not from the extension. Pure function over the first bytes and the file size. |
| Input Data | bytes (≤ S MB), file extension (tie-breaker only) · Preconditions: Bytes available in sandbox. |
| Input Data Structures | Binary · module baseline DS |
| Processing Algorithm | 1. If bytes start with 'ply' + LF/CRLF → PLY (format line decides ascii / binary_little_endian / binary_big_endian).<br>2. If size ≥ 84 and size = 84 + 50·n with n = uint32 LE at offset 80 → binary STL (even if the header starts with 'solid').<br>3. Else if the first non-blank token is 'solid' and the text contains 'facet' → ASCII STL.<br>4. Else if text lines start with OBJ keywords (v, vt, vn, f, o, g, s, usemtl, mtllib, #) and at least one 'v' and one 'f' → OBJ.<br>5. Else → FILE_UNREADABLE (unknown format).<br>Algorithms: ALG-01 File format detection by signature |
| Mathematical Model | Binary STL size identity: \|file\| = 80 + 4 + 50·n.<br>ALG-01: Content sniffing: PLY magic "ply\n" + format line; binary STL iff 84 + 50*n == file size where n = uint32 at offset 80; ASCII STL iff first non-blank token "solid" AND a "facet" token within the first 4 KiB AND the size rule fails; OBJ iff lines begin with … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-01) |
| Geometry Operations | ALG-01 File format detection by signature [mesh import] |
| Output Data | format ∈ {stl_binary, stl_ascii, obj, ply_ascii, ply_bin_le, ply_bin_be} |
| Output Data Structures | enum · module baseline DS |
| Error Handling | Unknown → FILE_UNREADABLE.<br>Extension disagrees with content → notice 'extension mismatch' (not an error).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-01: O(1) on the 4 KiB prefix |
| Dependencies | Functions: none |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-TRIMESH trimesh (MIT; ORACLE); module baseline |
| Alternative Implementations | ALG-01: Trust extension (rejected: FR-010); libmagic (adds C dependency, no mesh rules). |
| Security Considerations | Module baseline · Constraint: ASCII STL files whose header word is 'solid' but whose size matches the binary identity are treated as binary (known STL ambiguity, 05 §1.1). · Untrusted input path (SEC-07) |
| Verification Strategy | Method T · test cases: TC-FR-010; TC-FR-015; TC-INT-01; TC-INT-02; TC-INT-03; UT-FN-KIO-01 (proposed) · suites: VER-08, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KIO-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Format set T4 (same object in 5 encodings) is classified 100% correctly; a binary STL with header 'solid…' is classified binary.<br>ALG-01: One fixture per format incl. binary STL with "solid" header; empty and random-bytes files. Invariants: Detection independent of file name.<br>One negative test per error code: FILE_UNREADABLE |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-010; TC-FR-015; TC-INT-01; TC-INT-02; TC-INT-03; UT-FN-KIO-01 (proposed) |
| Open Technical Questions | None registered |

#### FN-KIO-02 — Parse STL (binary and ASCII)

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KIO-02 |
| Function Name | Parse STL (binary and ASCII) |
| Related Requirement IDs | INT-01; FR-010; FR-015; SEC-07 |
| Architecture Component | C4/K01 · Import/Export Layer · Separate sandboxed child process of the worker (rlimits CPU/memory, read-only FS, no network) — TD-16 |
| Technical Purpose | Read STL triangle soup. Binary: 80-byte header, uint32 count, n records of 50 bytes (normal float32[3], vertices float32[9], uint16 attribute). ASCII: facet/outer loop/vertex×3/endloop/endfacet grammar. |
| Input Data | bytes · Preconditions: Format = stl_*. |
| Input Data Structures | STL (de-facto format, INT-01) · module baseline DS |
| Processing Algorithm | 1. Binary: read with a fixed little-endian structured dtype; ignore stored normals and attribute bytes.<br>2. ASCII: streaming tokenizer; accept any whitespace; numbers parsed as float64; ignore 'facet normal' values.<br>3. Emit triangle soup T (3n × 3 float64) in file order.<br>Algorithms: ALG-02 STL parsing (binary and ASCII) |
| Mathematical Model | ALG-02: Binary: 80-byte header, uint32 n, n records of 12 float32 + uint16 attribute (little-endian), parsed with a numpy structured dtype; ASCII: streaming tokenizer over "facet normal / outer loop / vertex x y z / endloop / endfacet". Stored normals are ignored … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-02) |
| Geometry Operations | ALG-02 STL parsing (binary and ASCII) [mesh import] |
| Output Data | Triangle soup. |
| Output Data Structures | float64[3n,3] · module baseline DS |
| Error Handling | Count/size mismatch → FILE_UNREADABLE (truncated).<br>n = 0 → FILE_EMPTY.<br>n > max_faces → FACE_LIMIT.<br>Malformed ASCII token → FILE_UNREADABLE with line number.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-02: Binary O(n) vectorised; ASCII O(bytes) tokenizer-bound [H] |
| Dependencies | Functions: FN-KIO-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-02: trimesh.load (merges vertices by default, must pass process=False [N]); numpy-stl (BSD-3). |
| Security Considerations | Module baseline · Constraint: Stored STL normals are never used (often wrong, 05 §1.5). float32 input precision is retained as float64 values. · Untrusted input path (SEC-07) |
| Verification Strategy | Method T · test cases: TC-FR-010; TC-FR-015; TC-INT-01; TC-SEC-07; UT-FN-KIO-02 (proposed) · suites: VER-08, VER-20, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KIO-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Binary and ASCII reference files give V/F counts equal to the reference parser after FN-KIO-05.<br>ALG-02: Hand-built 1- and 2-facet files; header with "solid"; attribute bytes non-zero. Invariants: Facet count = n; soup order = file order.<br>One negative test per error code: FACE_LIMIT, FILE_EMPTY, FILE_UNREADABLE |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-010; TC-FR-015; TC-INT-01; TC-SEC-07; UT-FN-KIO-02 (proposed) |
| Open Technical Questions | None registered |

#### FN-KIO-03 — Parse OBJ (geometry only)

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KIO-03 |
| Function Name | Parse OBJ (geometry only) |
| Related Requirement IDs | INT-02; FR-010 |
| Architecture Component | C4/K01 · Import/Export Layer · Separate sandboxed child process of the worker (rlimits CPU/memory, read-only FS, no network) — TD-16 |
| Technical Purpose | Read OBJ vertices and faces; triangulate polygons; ignore textures/materials with notice. Supports f records v, v/vt, v/vt/vn, v//vn; positive and negative (relative) indices. |
| Input Data | bytes (UTF-8 or ASCII) · Preconditions: Format = obj. |
| Input Data Structures | Wavefront OBJ (INT-02) · module baseline DS |
| Processing Algorithm | 1. Collect 'v x y z [w]' (w ignored; if w ≠ 1 → notice).<br>2. For each 'f': resolve indices: i > 0 → i−1; i < 0 → n_v_so_far + i (relative, valid per spec); 0 → error.<br>3. Polygon with k = 3 → keep; k > 3 → triangulate by ear clipping in the polygon's best-fit plane (Newell normal) to avoid fan inversion on non-convex polygons; record count of polygons triangulated.<br>4. Ignore vt, vn, usemtl, mtllib, l, p, curves/surfaces with notices listing counts.<br>Algorithms: ALG-03 OBJ parsing with polygon triangulation; ALG-25 Polygon simplicity test and ear-clipping triangulation |
| Mathematical Model | Newell normal n = Σ_i (y_i − y_{i+1})(z_i + z_{i+1}), … over polygon edges; projection onto plane ⟂ n for ear clipping.<br>ALG-03: Line grammar: "v x y z [w]" and "f a[/t][/n] …" with 1-based and negative (relative) indices; vt/vn/mtllib/usemtl/o/g ignored with notice. Polygons with k > 3 vertices are triangulated in their best-fit plane (Newell normal) by ear clipping (ALG-25) — fan … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-03)<br>ALG-25: Project contour to plane coordinates (orthonormal basis of Π). Simplicity: no two non-adjacent segments intersect (exact orient2d; O(k log k) Shamos–Hoey sweep or O(k²) brute force for k ≤ k_max). Ear clipping: repeatedly cut a convex vertex whose triangle … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-25) |
| Geometry Operations | ALG-03 OBJ parsing with polygon triangulation [mesh import]; ALG-25 Polygon simplicity test and ear-clipping triangulation [open mesh to closed mesh conversion] |
| Output Data | Vertex array + triangle index array. |
| Output Data Structures | float64[N,3], int64[M,3] · module baseline DS |
| Error Handling | Index out of range or 0 → FILE_UNREADABLE (line).<br>Degenerate polygon (all collinear) → triangles kept, reported as degenerate later by FN-KVL-02.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-03: O(bytes) + Σ O(k²) for ear clipping of k-gons; ALG-25: Simplicity O(k log k) (sweep) or O(k²); ear clipping O(k²) worst case |
| Dependencies | Functions: FN-KIO-01 · Technical decisions: TD-04, TD-12 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-03: Fan triangulation only (wrong on concave polygons); trimesh loader (behaviour on concave polygons to verify [H]).; ALG-25: Constrained Delaunay (Shewchuk Triangle — non-free commercial use, rejected); CDT in CGAL (GPL). |
| Security Considerations | Module baseline · Untrusted input path (SEC-07) |
| Verification Strategy | Method T · test cases: TC-FR-010; TC-INT-02; UT-FN-KIO-03 (proposed) · suites: VER-08, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KIO-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Textured OBJ imports geometry with notice; quads triangulated and reported; negative indices resolved.<br>ALG-03: Quads (convex/concave), negative indices, texture coords ignored with notice. Invariants: Triangulated faces keep polygon orientation.<br>ALG-25: Convex, concave, comb, spiral polygons. Invariants: k − 2 triangles; all CCW; union = polygon.<br>One negative test per error code: FILE_UNREADABLE |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-010; TC-INT-02; UT-FN-KIO-03 (proposed) |
| Open Technical Questions | TQ-17 |

#### FN-KIO-04 — Parse PLY (ASCII and binary)

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KIO-04 |
| Function Name | Parse PLY (ASCII and binary) |
| Related Requirement IDs | INT-03; FR-010 |
| Architecture Component | C4/K01 · Import/Export Layer · Separate sandboxed child process of the worker (rlimits CPU/memory, read-only FS, no network) — TD-16 |
| Technical Purpose | Read PLY vertex/face elements; ignore colour and other properties with notice. Header-driven parser: element declarations, scalar and list properties, both endiannesses. |
| Input Data | bytes · Preconditions: Format = ply_*. |
| Input Data Structures | PLY (Turk/Bourke spec, INT-03) · module baseline DS |
| Processing Algorithm | 1. Parse header until 'end_header'; record elements in order with counts and property types.<br>2. Vertex element must have x, y, z (float or double); face element must have list property 'vertex_indices' or 'vertex_index' (count uchar/ushort/uint, index int/uint).<br>3. Skip unknown elements using declared sizes (binary) or line counts (ASCII).<br>4. Triangulate polygons as in FN-KIO-03; notice for ignored properties (colour, quality, normals).<br>Algorithms: ALG-04 PLY parsing (ASCII, binary LE/BE) |
| Mathematical Model | ALG-04: Header grammar (element/property/list); body parsed per declared element; vertex x,y,z (float/double), face list (uchar/int count + int indices); other properties skipped by declared size. Binary bodies via numpy dtypes with declared endianness. |
| Geometry Operations | ALG-04 PLY parsing (ASCII, binary LE/BE) [mesh import] |
| Output Data | Vertex + triangle arrays. |
| Output Data Structures | float64[N,3], int64[M,3] · module baseline DS |
| Error Handling | Missing x/y/z or face list → FILE_UNREADABLE.<br>Declared counts exceed data → FILE_UNREADABLE (truncated).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-04: O(bytes) |
| Dependencies | Functions: FN-KIO-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-04: plyfile (GPL, rejected); trimesh PLY loader (MIT) as production fallback [H]. |
| Security Considerations | Module baseline · Untrusted input path (SEC-07) |
| Verification Strategy | Method T · test cases: TC-FR-010; TC-INT-03; UT-FN-KIO-04 (proposed) · suites: VER-08, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KIO-04 (proposed id)<br>Acceptance criteria as unit/component assertions: ASCII, binary LE and binary BE encodings of the same object yield identical arrays.<br>ALG-04: ASCII, binary LE, binary BE fixtures; extra properties. Invariants: Same V/F as STL import of the same object after ALG-05.<br>One negative test per error code: FILE_UNREADABLE |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-010; TC-INT-03; UT-FN-KIO-04 (proposed) |
| Open Technical Questions | None registered |

#### FN-KIO-05 — Build and validate indexed mesh

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KIO-05 |
| Function Name | Build and validate indexed mesh |
| Related Requirement IDs | FR-010; FR-015; SEC-07 |
| Architecture Component | C4/K01 · Import/Export Layer · Separate sandboxed child process of the worker (rlimits CPU/memory, read-only FS, no network) — TD-16 |
| Technical Purpose | Turn parser output into a canonical indexed triangle mesh in deterministic order. Exact-duplicate vertex merge (bitwise equality of float64 triples); no epsilon merge (05 §1.1). |
| Input Data | Triangle soup or (V, F); limits · Preconditions: Parser output. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Canonicalise −0.0 → +0.0.<br>2. Merge exactly equal vertex triples; vertex order = first occurrence order; remap faces.<br>3. Validate: all coordinates finite; indices in range; ≥ 1 face; F ≤ max_faces.<br>4. Keep faces in file order (no sorting) so later face IDs are stable references.<br>Algorithms: ALG-05 Indexed mesh construction with exact vertex merge |
| Mathematical Model | ALG-05: Bitwise-exact vertex welding: identical float64 triples (after canonicalising −0.0 to +0.0) map to one index; no epsilon welding (05 §1.1, avoids silently changing topology). Implementation: np.unique on a void/structured view of the (n,3) array with … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-05) |
| Geometry Operations | ALG-05 Indexed mesh construction with exact vertex merge [mesh import / mesh validation] |
| Output Data | Mesh (V, F) + import stats. |
| Output Data Structures | float64[N,3], int32[M,3]; JSON {n_vertices_in, n_vertices_merged, polygons_triangulated, notices[]} · module baseline DS |
| Error Handling | NaN/Inf → NON_FINITE_COORDINATES.<br>0 faces → FILE_EMPTY.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-05: O(n log n) sort |
| Dependencies | Functions: FN-KIO-02; FN-KIO-03; FN-KIO-04 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-05: Epsilon welding (rejected: changes topology silently); trimesh merge_vertices (tolerance-based [N]). |
| Security Considerations | Module baseline · Constraint: Vertices differing by float rounding are not merged; resulting cracks are reported as boundary loops by FN-KVL-01 rather than silently welded. · Untrusted input path (SEC-07) |
| Verification Strategy | Method T · test cases: TC-FR-010; TC-FR-015; TC-SEC-07; UT-FN-KIO-05 (proposed) · suites: VER-08, VER-20, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KIO-05 (proposed id)<br>Acceptance criteria as unit/component assertions: Same object in all T4 encodings yields equal V/F counts; NaN fixture rejected.<br>ALG-05: Shared-vertex soup → expected V/F; −0.0 vs 0.0 merge. Invariants: len(V) ≤ 3m; F indices < len(V); geometry of every face unchanged bitwise.<br>One negative test per error code: FILE_EMPTY, NON_FINITE_COORDINATES |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-010; TC-FR-015; TC-SEC-07; UT-FN-KIO-05 (proposed) |
| Open Technical Questions | None registered |

#### FN-KIO-06 — Write binary STL

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KIO-06 |
| Function Name | Write binary STL |
| Related Requirement IDs | FR-100; INT-04; STK-04 |
| Architecture Component | C4/K01 · Import/Export Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Produce the manufacturing file in millimetres. Little-endian binary STL; face normals recomputed; float32 storage. |
| Input Data | V float64[N,3] (mm, F_export), F int32[M,3], header text · Preconditions: Approved geometry transformed to F_export. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Header: 80 bytes ASCII 'JUDE <build> <case_id> v<n> mm F_export', space-padded.<br>2. Count = M (uint32).<br>3. Per face: unit normal from float64 cross product cast to float32; three vertices cast to float32; attribute = 0.<br>4. Return bytes and SHA-256.<br>Algorithms: ALG-06 Binary STL writer and independent re-read comparison |
| Mathematical Model | Rounding error per coordinate ≤ ½·ulp_float32(\|x\|); for \|x\| ≤ 150 mm ≤ 7.6·10⁻⁶ mm (VERIFICATION_CRITERIA §3).<br>ALG-06: Write: float64 → float32 rounding (round-to-nearest), facet normal = normalised (b−a)×(c−a) in float64 then cast, attribute 0, little-endian, 80-byte ASCII header with schema id and design id (no patient data). Re-read: parse with an implementation … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-06) |
| Geometry Operations | ALG-06 Binary STL writer and independent re-read comparison [manufacturing geometry] |
| Output Data | STL bytes. |
| Output Data Structures | Binary STL, mm · module baseline DS |
| Error Handling | M > 2³²−1 → impossible within NFR-03 (assert).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-06: O(m) |
| Dependencies | Functions: none · Technical decisions: TD-21 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-06: ASCII STL (larger, decimal rounding); 3MF (post-MVP, FN-PMV-11). |
| Security Considerations | Module baseline · Untrusted input path (SEC-07) |
| Verification Strategy | Method T · test cases: TC-FR-100; TC-INT-04; UT-FN-KIO-06 (proposed) · suites: VER-06 · evidence level L1/L2 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KIO-06 (proposed id)<br>Acceptance criteria as unit/component assertions: File size = 84 + 50·M; triangle count equal; vertex deviation ≤ 1e-4 mm on re-read.<br>ALG-06: Known triangle → known bytes; header content check. Invariants: Triangle count preserved; orientation preserved; laterality preserved (VER-03). |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-100; TC-INT-04; UT-FN-KIO-06 (proposed) |
| Open Technical Questions | None registered |

#### FN-KIO-07 — Re-read exported file and compare

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KIO-07 |
| Function Name | Re-read exported file and compare |
| Related Requirement IDs | FR-102; VER-06; DATA-06 |
| Architecture Component | C4/K01 · Import/Export Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Detect corrupted or wrongly written exports before release (FR-102). Independent reader (separate implementation from FN-KIO-02, e.g. numpy structured dtype) re-reads the written bytes from storage. |
| Input Data | STL bytes from storage, in-app arrays (F_export), tolerance τ = 1e-4 mm (DEC-025) · Preconditions: Export bytes stored. |
| Input Data Structures | Binary + arrays · module baseline DS |
| Processing Algorithm | 1. Re-read count and triangles.<br>2. Compare count with M.<br>3. For each face i and corner j: δ = ‖T_file[i,j] − V[F[i,j]]‖₂.<br>4. Pass ⇔ count equal ∧ max δ ≤ τ; record max δ.<br>5. Recompute SHA-256 of bytes and compare with the SHA recorded at write.<br>Algorithms: ALG-06 Binary STL writer and independent re-read comparison |
| Mathematical Model | max_{i,j} ‖p_file − p_app‖ ≤ τ; expected ≤ 1.3·10⁻⁵ mm for coordinates ≤ 150 mm.<br>ALG-06: Write: float64 → float32 rounding (round-to-nearest), facet normal = normalised (b−a)×(c−a) in float64 then cast, attribute 0, little-endian, 80-byte ASCII header with schema id and design id (no patient data). Re-read: parse with an implementation … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-06) |
| Geometry Operations | ALG-06 Binary STL writer and independent re-read comparison [manufacturing geometry] |
| Output Data | Re-import result. |
| Output Data Structures | JSON {passed, triangle_count_equal, max_vertex_deviation_mm, sha_equal} · module baseline DS |
| Error Handling | Any mismatch → passed=false; export marked failed, not released.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-06: O(m) |
| Dependencies | Functions: FN-KIO-06 · Technical decisions: TD-21 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-NUMPYSTL numpy-stl (BSD-3-Clause; CAND); module baseline |
| Alternative Implementations | ALG-06: ASCII STL (larger, decimal rounding); 3MF (post-MVP, FN-PMV-11). |
| Security Considerations | Module baseline · Untrusted input path (SEC-07) |
| Verification Strategy | Method T · test cases: TC-DATA-06; TC-FR-102; UT-FN-KIO-07 (proposed) · suites: VER-06, VER-20 · evidence level L0, L1/L2 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KIO-07 (proposed id)<br>Acceptance criteria as unit/component assertions: Corrupted-write injection test marks export failed; normal exports pass with max deviation ≤ 1e-4 mm.<br>ALG-06: Known triangle → known bytes; header content check. Invariants: Triangle count preserved; orientation preserved; laterality preserved (VER-03). |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-06; TC-FR-102; UT-FN-KIO-07 (proposed) |
| Open Technical Questions | None registered |

### Module KVL — Kernel validation

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Validation Layer / Geometry Engine |
| Runtime and execution | C4 worker process (pure function, single-threaded numerics); never in C3 request threads except hashing helpers · Pure function called by jobs |
| Input data structures | DS-01 + typed params (DS-03 schema) |
| Output data structures | DS-05 (outputs + report) |
| Interfaces | IF-03 |
| External libraries | LIB-NUMPY; LIB-SCIPY |
| Performance | Complexity per ALG; wall-time budgets TBD via BM-01/BM-02 (PM-04…08) |
| Security | Pure function: no I/O, no clock, no randomness; inputs validated by OpSpec schemas; display_only inputs rejected (INV-10) |
| Integration tests | Called through the job runner on fixture designs; results persisted and re-read; determinism over 100 runs (VER-07) |
| Alternatives | See ALGORITHM_CATALOG alternatives |
| Versioning | op_version per op; kernel_version + image digest per result |

#### FN-KVL-01 — Edge topology, boundary loops and non-manifold elements

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KVL-01 |
| Function Name | Edge topology, boundary loops and non-manifold elements |
| Related Requirement IDs | FR-013; FR-080 |
| Architecture Component | C4/K02 · Validation Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Compute boundary and manifoldness metrics. Edge-incidence analysis on the indexed mesh. |
| Input Data | V, F · Preconditions: Indexed mesh in mm. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Build directed half-edges (f, i→j); undirected key (min(i,j), max(i,j)); count incident faces per key via sort.<br>2. Boundary edge: count = 1. Non-manifold edge: count > 2.<br>3. Boundary loops: link boundary half-edges head-to-tail; loops = cycles; perimeter_mm = Σ ‖v_{k+1} − v_k‖.<br>4. Non-manifold vertex: the faces around the vertex form more than one edge-connected fan (count fans via local union-find).<br>5. Report counts, loop list (id, n_vertices, perimeter_mm, centroid) sorted by perimeter desc; longest perimeter.<br>Algorithms: ALG-07 Edge topology, boundary loops and non-manifold detection |
| Mathematical Model | Loop perimeter P = Σ_k ‖v_{k+1} − v_k‖₂ (closed polyline).<br>ALG-07: Undirected edge key k = (min(a,b), max(a,b)) per face edge; incidence count c(k) by sort + run-length. c = 1 → boundary edge, c = 2 → interior, c > 2 → non-manifold edge. Boundary loops: directed boundary half-edges form a functional graph; trace cycles … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-07) |
| Geometry Operations | ALG-07 Edge topology, boundary loops and non-manifold detection [mesh validation / boundary detection / hole detection / manifold validation] |
| Output Data | Topology report. |
| Output Data Structures | JSON {boundary_edges, boundary_loops[], longest_loop_mm, non_manifold_edges, non_manifold_vertices} · module baseline DS |
| Error Handling | Boundary vertex visited twice in loop tracing (bow-tie) → loop split at the vertex; counted once as non-manifold vertex.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-07: O(m log m) |
| Dependencies | Functions: FN-KIO-05 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-07: Half-edge data structure (OpenMesh BSD, LIB-OPENMESH) — cannot represent non-manifold input, so metrics must be computed before it. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-013; TC-FR-080; UT-FN-KVL-01 (proposed) · suites: VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KVL-01 (proposed id)<br>Acceptance criteria as unit/component assertions: VER-08 holes of known perimeter: loop count and perimeter (± perimeter tolerance 0.032 mm on R=75 phantoms) correct; non-manifold edge fixture counted exactly.<br>ALG-07: Single triangle (3 boundary edges, 1 loop); two triangles sharing an edge; three faces on one edge (non-manifold). Invariants: Σ c(k) = 3m; χ = V − E + F; loops partition boundary edges. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-013; TC-FR-080; UT-FN-KVL-01 (proposed) |
| Open Technical Questions | None registered |

#### FN-KVL-02 — Degenerate face detection

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KVL-02 |
| Function Name | Degenerate face detection |
| Related Requirement IDs | FR-013 |
| Architecture Component | C4/K02 · Validation Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Count faces of (near-)zero area. Index-degenerate faces (repeated vertex index) and faces with area < ε_area. |
| Input Data | V, F, ε_area (kernel constant) · Preconditions: Indexed mesh. |
| Input Data Structures | Arrays + float · module baseline DS |
| Processing Algorithm | 1. Index-degenerate: F[i,0]=F[i,1] ∨ F[i,1]=F[i,2] ∨ F[i,0]=F[i,2].<br>2. Area A = ½‖(b − a) × (c − a)‖; degenerate if A < ε_area.<br>3. Report count and ε_area used.<br>Algorithms: ALG-08 Degenerate face detection |
| Mathematical Model | A_f = ½‖(v_b − v_a) × (v_c − v_a)‖₂.<br>ALG-08: Face area A = ½‖(b−a)×(c−a)‖ (float64). Degenerate iff A ≤ ε_area OR exact collinearity (orient-type test on the three points in their best plane) OR repeated vertex index. Needle/cap faces reported separately by min angle (diagnostic only). |
| Geometry Operations | ALG-08 Degenerate face detection [mesh validation] |
| Output Data | Count. |
| Output Data Structures | JSON {degenerate_faces, epsilon_area_mm2} · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-08: O(m) |
| Dependencies | Functions: FN-KIO-05 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-08: Relative ε (fraction of median face area) — proposed alternative in OQ-FS-13. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-013; UT-FN-KVL-02 (proposed) · suites: VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KVL-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Seeded zero-area and repeated-index faces counted exactly; clean phantoms report 0.<br>ALG-08: Zero-area, collinear, repeated-index, valid faces. Invariants: Count independent of face order. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-013; UT-FN-KVL-02 (proposed) |
| Open Technical Questions | OQ-FS-13; Missing data: ε_area value not yet set (FR-013 delegates it to the VER-01 numerical analysis). |

#### FN-KVL-03 — Connected components

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KVL-03 |
| Function Name | Connected components |
| Related Requirement IDs | FR-013; FR-080 |
| Architecture Component | C4/K02 · Validation Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Count separate mesh pieces (fragments, hair, cap, background). Edge-connected face components. |
| Input Data | F, edge incidence from FN-KVL-01 · Preconditions: Indexed mesh. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Union-find over faces sharing an undirected edge.<br>2. Report count and per-component face count, area and bbox (for the cleanup UI).<br>Algorithms: ALG-09 Connected components |
| Mathematical Model | ALG-09: Graph on faces with an edge for each shared undirected edge (manifold or not) → scipy.sparse.csgraph.connected_components; components ordered by (−face count, min face id) for deterministic labels. |
| Geometry Operations | ALG-09 Connected components [connected components] |
| Output Data | Components. |
| Output Data Structures | JSON {components, items[{id, faces, area_mm2, bbox}]} · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-09: O(m) |
| Dependencies | Functions: FN-KVL-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-SCIPY scipy (BSD-3-Clause (classifier: BSD License); R-MVP); module baseline |
| Alternative Implementations | ALG-09: Vertex-connectivity (merges bow-ties); union-find own. |
| Security Considerations | Module baseline · Constraint: Pieces touching only at a vertex count as separate components (they are also reported as non-manifold vertices). |
| Verification Strategy | Method T · test cases: TC-FR-013; TC-FR-080; UT-FN-KVL-03 (proposed) · suites: VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KVL-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Fixture with k extra fragments reports k+1 components.<br>ALG-09: Two disjoint spheres → 2; bow-tie → 2 (edge rule). Invariants: Σ faces = m; labels independent of input face permutation up to the documented order rule. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-013; TC-FR-080; UT-FN-KVL-03 (proposed) |
| Open Technical Questions | None registered |

#### FN-KVL-04 — Orientation consistency and outward test

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KVL-04 |
| Function Name | Orientation consistency and outward test |
| Related Requirement IDs | FR-080; FR-013 |
| Architecture Component | C4/K02 · Validation Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Detect inconsistent winding and determine whether normals point outward. Consistency from half-edge directions; outwardness from signed volume (closed) or a centroid heuristic (open, reported only). |
| Input Data | V, F, edge incidence · Preconditions: Indexed mesh. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Inconsistent edge: a manifold edge traversed in the same direction by both faces; count them.<br>2. Closed mesh: signed volume V = (1/6) Σ_f a·(b × c); outward ⇔ V > 0.<br>3. Open mesh: s = Σ_f A_f · n̂_f · (c_f − c̄) with c̄ the area-weighted centroid; report outward_hint = (s > 0) — informational, never auto-corrected.<br>Algorithms: ALG-10 Orientation consistency, outward test and recorded re-orientation; ALG-22 Mesh repair policy (explicit recorded repair only) |
| Mathematical Model | Signed volume by the divergence theorem; s is an area-weighted radial alignment score.<br>ALG-10: Consistency: for every manifold interior edge the two incident faces must traverse it in opposite directions (directed half-edge appears once in each direction). Outward test: closed component → signed volume V = (1/6) Σ a·(b×c) > 0; open scan → hint only: … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-10)<br>ALG-22: No silent repair (05 §6.2). Repair = composition of recorded ops chosen by the technician: remove faces/components (ALG-15), fill selected holes (ALG-16), optional orientation normalisation (ALG-10, OQ-FS-37). Each op is versioned, replayable and visible … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-22) |
| Geometry Operations | ALG-10 Orientation consistency, outward test and recorded re-orientation [normal correction]; ALG-22 Mesh repair policy (explicit recorded repair only) [mesh repair] |
| Output Data | Orientation report. |
| Output Data Structures | JSON {inconsistent_edges, closed, signed_volume_mm3?, outward_hint} · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-10: O(m); ALG-22: Sum of ops |
| Dependencies | Functions: FN-KVL-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-10: trimesh fix_normals (applies changes; not allowed silently); ray-parity outward test (fails on open meshes).; ALG-22: Automatic repair (pymeshfix — AGPL-3.0 per PyPI, rejected; MeshLab filters — GPL). |
| Security Considerations | Module baseline · Constraint: The open-mesh hint can be wrong on strongly non-convex scans; outwardness is only guaranteed on the closed positive. |
| Verification Strategy | Method T · test cases: TC-FR-013; TC-FR-080; UT-FN-KVL-04 (proposed) · suites: VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KVL-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Flipped-face fixture reports exact inconsistent-edge count; closed phantom V > 0; flipped closed phantom V < 0.<br>ALG-10: Sphere with one flipped face → 3 inconsistent edges; inverted sphere → negative volume. Invariants: Flipping all faces negates volume; translation leaves volume unchanged.<br>ALG-22: Op list replay equality. Invariants: Disable all ops → original hash. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-013; TC-FR-080; UT-FN-KVL-04 (proposed) |
| Open Technical Questions | OQ-FS-37 |

#### FN-KVL-05 — Self-intersection detection

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KVL-05 |
| Function Name | Self-intersection detection |
| Related Requirement IDs | FR-171; FR-080; FR-013 |
| Architecture Component | C4/K02 · Validation Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Count pairs of triangles that intersect improperly (input ghost layers, post-op folds). BVH broad phase + exact triangle–triangle narrow phase. |
| Input Data | V, F; optional subset of faces to test against all (incremental mode) · Preconditions: Indexed mesh. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Build AABB tree (or sweep-and-prune on sorted boxes) over faces.<br>2. Candidate pairs: overlapping boxes, i < j.<br>3. Pairs sharing 2 vertices (edge-adjacent): intersect only if the two opposite vertices lie on the same side and the triangles are coplanar-overlapping (fold) → test with exact orientation predicates.<br>4. Pairs sharing 1 vertex: test whether the opposite edge of either triangle crosses the other triangle.<br>5. Disjoint pairs: Möller (1997) or Guigue–Devillers (2003) interval test using exact/adaptive orientation predicates (Shewchuk) to avoid false results on near-degenerate configurations.<br>6. Return count of intersecting pairs and up to 100 pair locations (centroids) for display.<br>Algorithms: ALG-11 Self-intersection detection with exact predicates |
| Mathematical Model | orient3d(a,b,c,d) = sign det[[b−a],[c−a],[d−a]] evaluated exactly (adaptive precision).<br>ALG-11: Broad phase: AABB BVH (median split on centroid, deterministic) or sweep-and-prune over sorted boxes; candidate pairs i < j with overlapping boxes. Narrow phase: Guigue–Devillers triangle–triangle overlap built only from orient3d/orient2d signs; signs … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-11) |
| Geometry Operations | ALG-11 Self-intersection detection with exact predicates [self-intersection detection] |
| Output Data | Self-intersection report. |
| Output Data Structures | JSON {self_intersecting_pairs, samples[≤100]} · module baseline DS |
| Error Handling | Time budget exceeded → job failed SELF_INTERSECTION_TIMEOUT (never reported as 0).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-11: O(m log m + k) expected for BVH with k candidate pairs [N]; worst case O(m²) for pathological overlap (ghost layers produce many candidates) [H] |
| Dependencies | Functions: FN-KIO-05 · Technical decisions: TD-02, TD-04, TD-05 |
| External Libraries | LIB-CPP C++ (17/20) (—; RESERVE); LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-NUMBA numba (BSD-2-Clause (PyPI: "BSD"); CAND); LIB-CGAL CGAL (PMP, Alpha Wrap, corefinement) (GPL-3.0+ for most algorithm packages, LGPL-3.0+ for kernel/support; commercial licence from GeometryFactory; ORACLE); LIB-MESHLIB MeshLib SDK (LicenseRef-MeshLib: free for non-commercial/educational use; commercial licence required for business use; REJECT); LIB-PREDICATES Shewchuk robust predicates (own port) (Public domain (original); JS port robust-predicates under Unlicense; R-MVP); module baseline |
| Alternative Implementations | ALG-11: CGAL (GPL/commercial, OQ-G5); libigl copyleft/cgal (GPL); MeshLib (commercial licence, LIB-MESHLIB); Möller float test (rejected alone). |
| Security Considerations | Module baseline · Constraint: Exact predicates required; floating-point-only tests produce false positives/negatives on touching layers. |
| Verification Strategy | Method T · test cases: TC-FR-013; TC-FR-080; TC-FR-171; UT-FN-KVL-05 (proposed) · suites: VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KVL-05 (proposed id)<br>Acceptance criteria as unit/component assertions: VER-08 self-intersection and ghost-layer fixtures report count > 0 equal to the oracle count; clean phantoms report 0.<br>ALG-11: Hand-built pairs: crossing, touching edge, touching vertex, coplanar overlap, coplanar disjoint, shared-edge fold, shared-vertex crossing. Invariants: Count invariant under face permutation and exact rigid motions (permutations of axes).<br>One negative test per error code: SELF_INTERSECTION_TIMEOUT |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-013; TC-FR-080; TC-FR-171; UT-FN-KVL-05 (proposed) |
| Open Technical Questions | TQ-11 |

##### FN-KVL-05.1 — Broad phase

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KVL-05.1 |
| Function Name | Broad phase  (subfunction of FN-KVL-05 Self-intersection detection) |
| Related Requirement IDs | Inherited from parent FN-KVL-05: FR-171; FR-080; FR-013 |
| Architecture Component | C4/K02 · Validation Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | AABB tree / sweep-and-prune candidate pairs. |
| Input Data | Inherited from FN-KVL-05 |
| Input Data Structures | Inherited from FN-KVL-05 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | AABB tree / sweep-and-prune candidate pairs. — implemented by ALG-11 |
| Mathematical Model | ALG-11: Broad phase: AABB BVH (median split on centroid, deterministic) or sweep-and-prune over sorted boxes; candidate pairs i < j with overlapping boxes. Narrow phase: Guigue–Devillers triangle–triangle overlap built only from orient3d/orient2d signs; signs … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-11) |
| Geometry Operations | ALG-11 Self-intersection detection with exact predicates [self-intersection detection] |
| Output Data | Inherited from FN-KVL-05 |
| Output Data Structures | Inherited from FN-KVL-05 |
| Error Handling | Inherited from FN-KVL-05 |
| Performance Requirements | Inherited from FN-KVL-05 — complexity: ALG-11: O(m log m + k) expected for BVH with k candidate pairs [N]; worst case O(m²) for pathological overlap (ghost layers produce many candidates) [H] |
| Dependencies | Inherited from FN-KVL-05 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-CPP C++ (17/20) (—; RESERVE); LIB-NUMBA numba (BSD-2-Clause (PyPI: "BSD"); CAND); LIB-CGAL CGAL (PMP, Alpha Wrap, corefinement) (GPL-3.0+ for most algorithm packages, LGPL-3.0+ for kernel/support; commercial licence from GeometryFactory; ORACLE); LIB-MESHLIB MeshLib SDK (LicenseRef-MeshLib: free for non-commercial/educational use; commercial licence required for business use; REJECT); LIB-PREDICATES Shewchuk robust predicates (own port) (Public domain (original); JS port robust-predicates under Unlicense; R-MVP); module baseline |
| Alternative Implementations | ALG-11: CGAL (GPL/commercial, OQ-G5); libigl copyleft/cgal (GPL); MeshLib (commercial licence, LIB-MESHLIB); Möller float test (rejected alone). |
| Security Considerations | Inherited from FN-KVL-05 |
| Verification Strategy | T — verified within FN-KVL-05 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-KVL-05.1 (proposed id)<br>Isolated test of this step with positive and negative cases: AABB tree / sweep-and-prune candidate pairs.<br>ALG-11: Hand-built pairs: crossing, touching edge, touching vertex, coplanar overlap, coplanar disjoint, shared-edge fold, shared-vertex crossing. Invariants: Count invariant under face permutation and exact rigid motions (permutations of axes). |
| Integration Test Requirements | Inherited from FN-KVL-05 |
| Open Technical Questions | TQ-11 |

##### FN-KVL-05.2 — Adjacent-pair tests

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KVL-05.2 |
| Function Name | Adjacent-pair tests  (subfunction of FN-KVL-05 Self-intersection detection) |
| Related Requirement IDs | Inherited from parent FN-KVL-05: FR-171; FR-080; FR-013 |
| Architecture Component | C4/K02 · Validation Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Shared-edge fold and shared-vertex crossing tests. |
| Input Data | Inherited from FN-KVL-05 |
| Input Data Structures | Inherited from FN-KVL-05 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Shared-edge fold and shared-vertex crossing tests. — implemented by ALG-11 |
| Mathematical Model | ALG-11: Broad phase: AABB BVH (median split on centroid, deterministic) or sweep-and-prune over sorted boxes; candidate pairs i < j with overlapping boxes. Narrow phase: Guigue–Devillers triangle–triangle overlap built only from orient3d/orient2d signs; signs … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-11) |
| Geometry Operations | ALG-11 Self-intersection detection with exact predicates [self-intersection detection] |
| Output Data | Inherited from FN-KVL-05 |
| Output Data Structures | Inherited from FN-KVL-05 |
| Error Handling | Inherited from FN-KVL-05 |
| Performance Requirements | Inherited from FN-KVL-05 — complexity: ALG-11: O(m log m + k) expected for BVH with k candidate pairs [N]; worst case O(m²) for pathological overlap (ghost layers produce many candidates) [H] |
| Dependencies | Inherited from FN-KVL-05 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-CPP C++ (17/20) (—; RESERVE); LIB-NUMBA numba (BSD-2-Clause (PyPI: "BSD"); CAND); LIB-CGAL CGAL (PMP, Alpha Wrap, corefinement) (GPL-3.0+ for most algorithm packages, LGPL-3.0+ for kernel/support; commercial licence from GeometryFactory; ORACLE); LIB-MESHLIB MeshLib SDK (LicenseRef-MeshLib: free for non-commercial/educational use; commercial licence required for business use; REJECT); LIB-PREDICATES Shewchuk robust predicates (own port) (Public domain (original); JS port robust-predicates under Unlicense; R-MVP); module baseline |
| Alternative Implementations | ALG-11: CGAL (GPL/commercial, OQ-G5); libigl copyleft/cgal (GPL); MeshLib (commercial licence, LIB-MESHLIB); Möller float test (rejected alone). |
| Security Considerations | Inherited from FN-KVL-05 |
| Verification Strategy | T — verified within FN-KVL-05 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-KVL-05.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Shared-edge fold and shared-vertex crossing tests.<br>ALG-11: Hand-built pairs: crossing, touching edge, touching vertex, coplanar overlap, coplanar disjoint, shared-edge fold, shared-vertex crossing. Invariants: Count invariant under face permutation and exact rigid motions (permutations of axes). |
| Integration Test Requirements | Inherited from FN-KVL-05 |
| Open Technical Questions | TQ-11 |

##### FN-KVL-05.3 — Exact narrow phase

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KVL-05.3 |
| Function Name | Exact narrow phase  (subfunction of FN-KVL-05 Self-intersection detection) |
| Related Requirement IDs | Inherited from parent FN-KVL-05: FR-171; FR-080; FR-013 |
| Architecture Component | C4/K02 · Validation Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Triangle–triangle test on orientation predicates. |
| Input Data | Inherited from FN-KVL-05 |
| Input Data Structures | Inherited from FN-KVL-05 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Triangle–triangle test on orientation predicates. — implemented by ALG-11 |
| Mathematical Model | ALG-11: Broad phase: AABB BVH (median split on centroid, deterministic) or sweep-and-prune over sorted boxes; candidate pairs i < j with overlapping boxes. Narrow phase: Guigue–Devillers triangle–triangle overlap built only from orient3d/orient2d signs; signs … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-11) |
| Geometry Operations | ALG-11 Self-intersection detection with exact predicates [self-intersection detection] |
| Output Data | Inherited from FN-KVL-05 |
| Output Data Structures | Inherited from FN-KVL-05 |
| Error Handling | Inherited from FN-KVL-05 |
| Performance Requirements | Inherited from FN-KVL-05 — complexity: ALG-11: O(m log m + k) expected for BVH with k candidate pairs [N]; worst case O(m²) for pathological overlap (ghost layers produce many candidates) [H] |
| Dependencies | Inherited from FN-KVL-05 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-CPP C++ (17/20) (—; RESERVE); LIB-NUMBA numba (BSD-2-Clause (PyPI: "BSD"); CAND); LIB-CGAL CGAL (PMP, Alpha Wrap, corefinement) (GPL-3.0+ for most algorithm packages, LGPL-3.0+ for kernel/support; commercial licence from GeometryFactory; ORACLE); LIB-MESHLIB MeshLib SDK (LicenseRef-MeshLib: free for non-commercial/educational use; commercial licence required for business use; REJECT); LIB-PREDICATES Shewchuk robust predicates (own port) (Public domain (original); JS port robust-predicates under Unlicense; R-MVP); module baseline |
| Alternative Implementations | ALG-11: CGAL (GPL/commercial, OQ-G5); libigl copyleft/cgal (GPL); MeshLib (commercial licence, LIB-MESHLIB); Möller float test (rejected alone). |
| Security Considerations | Inherited from FN-KVL-05 |
| Verification Strategy | T — verified within FN-KVL-05 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-KVL-05.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Triangle–triangle test on orientation predicates.<br>ALG-11: Hand-built pairs: crossing, touching edge, touching vertex, coplanar overlap, coplanar disjoint, shared-edge fold, shared-vertex crossing. Invariants: Count invariant under face permutation and exact rigid motions (permutations of axes). |
| Integration Test Requirements | Inherited from FN-KVL-05 |
| Open Technical Questions | TQ-11 |

##### FN-KVL-05.4 — Incremental mode

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KVL-05.4 |
| Function Name | Incremental mode  (subfunction of FN-KVL-05 Self-intersection detection) |
| Related Requirement IDs | Inherited from parent FN-KVL-05: FR-171; FR-080; FR-013 |
| Architecture Component | C4/K02 · Validation Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Only faces touching moved vertices vs all faces (FN-KOP-13). |
| Input Data | Inherited from FN-KVL-05 |
| Input Data Structures | Inherited from FN-KVL-05 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Only faces touching moved vertices vs all faces (FN-KOP-13). — implemented by ALG-11 |
| Mathematical Model | ALG-11: Broad phase: AABB BVH (median split on centroid, deterministic) or sweep-and-prune over sorted boxes; candidate pairs i < j with overlapping boxes. Narrow phase: Guigue–Devillers triangle–triangle overlap built only from orient3d/orient2d signs; signs … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-11) |
| Geometry Operations | ALG-11 Self-intersection detection with exact predicates [self-intersection detection] |
| Output Data | Inherited from FN-KVL-05 |
| Output Data Structures | Inherited from FN-KVL-05 |
| Error Handling | Inherited from FN-KVL-05 |
| Performance Requirements | Inherited from FN-KVL-05 — complexity: ALG-11: O(m log m + k) expected for BVH with k candidate pairs [N]; worst case O(m²) for pathological overlap (ghost layers produce many candidates) [H] |
| Dependencies | Inherited from FN-KVL-05 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-CPP C++ (17/20) (—; RESERVE); LIB-NUMBA numba (BSD-2-Clause (PyPI: "BSD"); CAND); LIB-CGAL CGAL (PMP, Alpha Wrap, corefinement) (GPL-3.0+ for most algorithm packages, LGPL-3.0+ for kernel/support; commercial licence from GeometryFactory; ORACLE); LIB-MESHLIB MeshLib SDK (LicenseRef-MeshLib: free for non-commercial/educational use; commercial licence required for business use; REJECT); LIB-PREDICATES Shewchuk robust predicates (own port) (Public domain (original); JS port robust-predicates under Unlicense; R-MVP); module baseline |
| Alternative Implementations | ALG-11: CGAL (GPL/commercial, OQ-G5); libigl copyleft/cgal (GPL); MeshLib (commercial licence, LIB-MESHLIB); Möller float test (rejected alone). |
| Security Considerations | Inherited from FN-KVL-05 |
| Verification Strategy | T — verified within FN-KVL-05 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-KVL-05.4 (proposed id)<br>Isolated test of this step with positive and negative cases: Only faces touching moved vertices vs all faces (FN-KOP-13).<br>ALG-11: Hand-built pairs: crossing, touching edge, touching vertex, coplanar overlap, coplanar disjoint, shared-edge fold, shared-vertex crossing. Invariants: Count invariant under face permutation and exact rigid motions (permutations of axes). |
| Integration Test Requirements | Inherited from FN-KVL-05 |
| Open Technical Questions | TQ-11 |

#### FN-KVL-06 — Watertightness, volume and bounding box

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KVL-06 |
| Function Name | Watertightness, volume and bounding box |
| Related Requirement IDs | FR-013; FR-080; FR-100 |
| Architecture Component | C4/K02 · Validation Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Size and closure metrics. Derived from FN-KVL-01 and coordinates. |
| Input Data | V, F · Preconditions: Indexed mesh in mm. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. watertight ⇔ boundary_edges = 0 ∧ non_manifold_edges = 0.<br>2. Volume V as in FN-KVL-04 when watertight.<br>3. bbox = (min_k V[:,k], max_k V[:,k]), extents in mm.<br>Algorithms: ALG-12 Watertightness, signed volume and bounding box |
| Mathematical Model | ALG-12: Watertight iff no boundary edges and no non-manifold edges (ALG-07). Volume by divergence theorem V = (1/6) Σ (a−o)·((b−o)×(c−o)) with o = bbox centre (reduces cancellation). Axis-aligned bbox in the current frame. |
| Geometry Operations | ALG-12 Watertightness, signed volume and bounding box [watertightness] |
| Output Data | Metrics. |
| Output Data Structures | JSON {watertight, volume_mm3?, bbox_min, bbox_max, extents_mm} · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-12: O(m) |
| Dependencies | Functions: FN-KVL-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-12: trimesh.volume (same formula [N]). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-013; TC-FR-080; TC-FR-100; UT-FN-KVL-06 (proposed) · suites: VER-06, VER-08 · evidence level L0, L1/L2 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KVL-06 (proposed id)<br>Acceptance criteria as unit/component assertions: Sphere phantom R=75 mm subdivision 6: relative volume error ≈ −1.4·10⁻⁴ (DEC-025 table) reproduced.<br>ALG-12: Unit cube = 1; tetrahedron analytic. Invariants: Rigid motion invariance of V; bbox of union ⊇ parts. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-013; TC-FR-080; TC-FR-100; UT-FN-KVL-06 (proposed) |
| Open Technical Questions | None registered |

#### FN-KVL-07 — Solid validity check (validate.solid)

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KVL-07 |
| Function Name | Solid validity check (validate.solid) |
| Related Requirement IDs | FR-080; FR-081; FR-082 |
| Architecture Component | C4/K02 · Validation Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Decide whether the generated positive is a valid closed solid (FR-080). Composite check over FN-KVL-01…06; geometry-only result (FR-082). |
| Input Data | V, F · Preconditions: Positive candidate. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Checks: C1 boundary_edges = 0; C2 non_manifold_edges = 0 ∧ non_manifold_vertices = 0; C3 self_intersecting_pairs = 0; C4 components = 1; C5 inconsistent_edges = 0 ∧ signed volume > 0.<br>2. Also report (non-blocking) degenerate_faces.<br>3. passed = C1 ∧ C2 ∧ C3 ∧ C4 ∧ C5.<br>Algorithms: ALG-13 Composite solid validity (validate.solid) |
| Mathematical Model | ALG-13: Conjunction of geometric checks: boundary edges = 0; non-manifold edges = 0; non-manifold vertices = 0; self-intersections = 0 (ALG-11); components = 1; inconsistent edges = 0; signed volume > 0 (outward); degenerate faces = 0. Each check reported … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-13) |
| Geometry Operations | ALG-13 Composite solid validity (validate.solid) [watertightness / manifold validation / solid validity] |
| Output Data | Validity report. |
| Output Data Structures | JSON {passed, checks[{id, name, count, passed}], kernel_version} · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-13: Dominated by ALG-11 |
| Dependencies | Functions: FN-KVL-01; FN-KVL-03; FN-KVL-04; FN-KVL-05; FN-KVL-06 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-MANIFOLD manifold3d (Manifold) (Apache-2.0; RESERVE); module baseline |
| Alternative Implementations | ALG-13: manifold3d constructor as validity oracle (reports error status for non-manifold input [N]). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-080; TC-FR-081; TC-FR-082; UT-FN-KVL-07 (proposed) · suites: VER-08, VER-09 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KVL-07 (proposed id)<br>Acceptance criteria as unit/component assertions: Each VER-08 defect type fails the matching check; valid phantoms pass all.<br>ALG-13: Each defect type fails exactly its check. Invariants: All checks pass on analytic closed phantoms. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-080; TC-FR-081; TC-FR-082; UT-FN-KVL-07 (proposed) |
| Open Technical Questions | None registered |

### Module KFR — Kernel frames and units

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Geometry Engine / — |
| Runtime and execution | C4 worker process (pure function, single-threaded numerics); never in C3 request threads except hashing helpers · Pure function called by jobs |
| Input data structures | DS-01 + typed params (DS-03 schema) |
| Output data structures | DS-05 (outputs + report) |
| Interfaces | IF-03 |
| External libraries | LIB-NUMPY; LIB-SCIPY |
| Performance | Complexity per ALG; wall-time budgets TBD via BM-01/BM-02 (PM-04…08) |
| Security | Pure function: no I/O, no clock, no randomness; inputs validated by OpSpec schemas; display_only inputs rejected (INV-10) |
| Integration tests | Called through the job runner on fixture designs; results persisted and re-read; determinism over 100 runs (VER-07) |
| Alternatives | See ALGORITHM_CATALOG alternatives |
| Versioning | op_version per op; kernel_version + image digest per result |

#### FN-KFR-01 — Scale to millimetres

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KFR-01 |
| Function Name | Scale to millimetres |
| Related Requirement IDs | FR-012 |
| Architecture Component | C4/K03 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Convert file units once to mm. Exact scaling; recorded as op units.to_mm. |
| Input Data | V, factor s ∈ {1, 10, 1000, 25.4} · Preconditions: Unit confirmed. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. V_mm = s·V.<br>2. Faces unchanged.<br>Algorithms: ALG-30 Unit scaling to millimetres |
| Mathematical Model | v' = s·v.<br>ALG-30: V_mm = s·V with s ∈ {1 (mm), 10 (cm), 1000 (m), 25.4 (inch)} from the technician-confirmed unit; recorded as op units.to_mm; frame F_scan = F_file scaled, same axes. |
| Geometry Operations | ALG-30 Unit scaling to millimetres [coordinate systems] |
| Output Data | scan_mm. |
| Output Data Structures | Arrays · module baseline DS |
| Error Handling | s not in the allowed set → PARAM_INVALID.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-30: O(n) |
| Dependencies | Functions: FN-KIO-05 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-30: Unit heuristic from bbox (rejected for silent use; FR-012 shows all four bboxes, OQ-FS-15). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-012; UT-FN-KFR-01 (proposed) · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KFR-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Conversions exact (bitwise equal to numpy multiplication); metamorphic test: cm file confirmed 'cm' yields the same mm values as the mm file.<br>ALG-30: Each unit factor. Invariants: Angles and topology unchanged.<br>One negative test per error code: PARAM_INVALID |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-012; UT-FN-KFR-01 (proposed) |
| Open Technical Questions | None registered |

#### FN-KFR-02 — Construct anatomical frame from landmarks

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KFR-02 |
| Function Name | Construct anatomical frame from landmarks |
| Related Requirement IDs | FR-031; SAF-03; FR-033 |
| Architecture Component | C4/K03 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Compute the right-handed F_anat transform per the active frame definition. Executes the enumerated construction rule of FN-CFG-06 on snapped landmark positions; asserts det = +1. |
| Input Data | Landmark positions p_k (mm, F_scan), frame definition (origin rule, axis rules, side labels) · Preconditions: All landmarks of the definition placed. |
| Input Data Structures | Arrays + JSON · module baseline DS |
| Processing Algorithm | 1. Origin o per rule (point, midpoint of pair, centroid, or projection of a point onto a landmark plane).<br>2. Primary axis â = normalize(q_b − q_a) where q are landmarks/midpoints named by the rule; if ‖q_b − q_a‖ < b_min = 1 mm → FRAME_DEGENERATE.<br>3. Plane normal ĝ from ≥ 3 landmarks: SVD of centred points, singular vector of the smallest singular value; sign chosen so ĝ · (rule reference vector) > 0.<br>4. Second axis b̂ = normalize(ĝ × â) (if ‖ĝ × â‖ < 1e-6 → FRAME_DEGENERATE); third ĉ = â × b̂.<br>5. Assign (â, b̂, ĉ) to (A-P, M-L, vertical) as the definition states; R = [axes as rows]; t = −R·o; T = [[R, t],[0, 1]].<br>6. Assert ‖RᵀR − I‖_F < 1e-9 and \|det R − 1\| < 1e-9; else FRAME_INVALID (never accept a reflection).<br>7. Mid-sagittal plane = plane through o with normal = M-L axis.<br>8. Laterality: patient-left = positive M-L side as declared in the definition; verify that each L-labelled landmark has positive M-L coordinate in F_anat; violation → warning LATERALITY_LABEL_MISMATCH shown at confirmation.<br>Algorithms: ALG-31 Anatomical frame construction from named landmarks |
| Mathematical Model | Right-handed orthonormal basis, det R = +1; F_anat coordinates x' = R(x − o).<br>ALG-31: Clinic frame definition (DEC-027) names landmarks and rules: origin o (point \| midpoint \| centroid \| projection); primary axis a₁ = normalise(p_j − p_i); reference plane normal from least-squares plane through ≥ 3 landmarks (SVD of centred points, smallest … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-31) |
| Geometry Operations | ALG-31 Anatomical frame construction from named landmarks [coordinate systems / anatomical landmarks] |
| Output Data | Frame. |
| Output Data Structures | JSON {matrix4x4 float64[16], det, origin, axes, msp_plane, warnings[]} · module baseline DS |
| Error Handling | FRAME_DEGENERATE (collinear/coincident landmarks).<br>FRAME_INVALID (det ≠ +1).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-31: O(k) for k landmarks |
| Dependencies | Functions: FN-KAN-02; FN-KFR-03 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-31: Kabsch/Umeyama template fit (post-MVP visit registration, F-SRC-07); PCA of scan (rejected: depends on scan extent). |
| Security Considerations | Module baseline · Constraint: Frame accuracy is bounded by landmark placement variability (literature: ±1.2–1.5 CVAI points from landmarking, SRC-004); the kernel does not estimate it. |
| Verification Strategy | Method T · test cases: TC-FR-031; TC-FR-033; TC-SAF-03; UT-FN-KFR-02 (proposed) · suites: VER-01, VER-03, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KFR-02 (proposed id)<br>Acceptance criteria as unit/component assertions: On VER-01 phantoms each axis within atan(2e/b) and origin within e = 0.011 mm of the analytic frame; det = +1 on all; laterality object keeps its side (VER-03).<br>ALG-31: Analytic landmark sets → exact axes; swapped labels → warning. Invariants: RᵀR = I; det = +1; frame equivariance under rigid motion of input.<br>One negative test per error code: FRAME_DEGENERATE, FRAME_INVALID |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-031; TC-FR-033; TC-SAF-03; UT-FN-KFR-02 (proposed) |
| Open Technical Questions | OQ-FS-03 |

##### FN-KFR-02.1 — Origin rule

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KFR-02.1 |
| Function Name | Origin rule  (subfunction of FN-KFR-02 Construct anatomical frame from landmarks) |
| Related Requirement IDs | Inherited from parent FN-KFR-02: FR-031; SAF-03; FR-033 |
| Architecture Component | C4/K03 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Point, midpoint, centroid or projection. |
| Input Data | Inherited from FN-KFR-02 |
| Input Data Structures | Inherited from FN-KFR-02 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Point, midpoint, centroid or projection. — implemented by ALG-31 |
| Mathematical Model | ALG-31: Clinic frame definition (DEC-027) names landmarks and rules: origin o (point \| midpoint \| centroid \| projection); primary axis a₁ = normalise(p_j − p_i); reference plane normal from least-squares plane through ≥ 3 landmarks (SVD of centred points, smallest … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-31) |
| Geometry Operations | ALG-31 Anatomical frame construction from named landmarks [coordinate systems / anatomical landmarks] |
| Output Data | Inherited from FN-KFR-02 |
| Output Data Structures | Inherited from FN-KFR-02 |
| Error Handling | Inherited from FN-KFR-02 |
| Performance Requirements | Inherited from FN-KFR-02 — complexity: ALG-31: O(k) for k landmarks |
| Dependencies | Inherited from FN-KFR-02 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-31: Kabsch/Umeyama template fit (post-MVP visit registration, F-SRC-07); PCA of scan (rejected: depends on scan extent). |
| Security Considerations | Inherited from FN-KFR-02 |
| Verification Strategy | T — verified within FN-KFR-02 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KFR-02.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Point, midpoint, centroid or projection.<br>ALG-31: Analytic landmark sets → exact axes; swapped labels → warning. Invariants: RᵀR = I; det = +1; frame equivariance under rigid motion of input. |
| Integration Test Requirements | Inherited from FN-KFR-02 |
| Open Technical Questions | Inherited from FN-KFR-02 |

##### FN-KFR-02.2 — Axis construction

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KFR-02.2 |
| Function Name | Axis construction  (subfunction of FN-KFR-02 Construct anatomical frame from landmarks) |
| Related Requirement IDs | Inherited from parent FN-KFR-02: FR-031; SAF-03; FR-033 |
| Architecture Component | C4/K03 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Primary axis, plane normal by SVD, Gram–Schmidt, det check. |
| Input Data | Inherited from FN-KFR-02 |
| Input Data Structures | Inherited from FN-KFR-02 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Primary axis, plane normal by SVD, Gram–Schmidt, det check. — implemented by ALG-31 |
| Mathematical Model | ALG-31: Clinic frame definition (DEC-027) names landmarks and rules: origin o (point \| midpoint \| centroid \| projection); primary axis a₁ = normalise(p_j − p_i); reference plane normal from least-squares plane through ≥ 3 landmarks (SVD of centred points, smallest … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-31) |
| Geometry Operations | ALG-31 Anatomical frame construction from named landmarks [coordinate systems / anatomical landmarks] |
| Output Data | Inherited from FN-KFR-02 |
| Output Data Structures | Inherited from FN-KFR-02 |
| Error Handling | Inherited from FN-KFR-02 |
| Performance Requirements | Inherited from FN-KFR-02 — complexity: ALG-31: O(k) for k landmarks |
| Dependencies | Inherited from FN-KFR-02 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-31: Kabsch/Umeyama template fit (post-MVP visit registration, F-SRC-07); PCA of scan (rejected: depends on scan extent). |
| Security Considerations | Inherited from FN-KFR-02 |
| Verification Strategy | T — verified within FN-KFR-02 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KFR-02.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Primary axis, plane normal by SVD, Gram–Schmidt, det check.<br>ALG-31: Analytic landmark sets → exact axes; swapped labels → warning. Invariants: RᵀR = I; det = +1; frame equivariance under rigid motion of input. |
| Integration Test Requirements | Inherited from FN-KFR-02 |
| Open Technical Questions | Inherited from FN-KFR-02 |

##### FN-KFR-02.3 — Laterality labelling

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KFR-02.3 |
| Function Name | Laterality labelling  (subfunction of FN-KFR-02 Construct anatomical frame from landmarks) |
| Related Requirement IDs | Inherited from parent FN-KFR-02: FR-031; SAF-03; FR-033 |
| Architecture Component | C4/K03 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | L/R side signs and label-mismatch warnings. |
| Input Data | Inherited from FN-KFR-02 |
| Input Data Structures | Inherited from FN-KFR-02 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | L/R side signs and label-mismatch warnings. — implemented by ALG-31 |
| Mathematical Model | ALG-31: Clinic frame definition (DEC-027) names landmarks and rules: origin o (point \| midpoint \| centroid \| projection); primary axis a₁ = normalise(p_j − p_i); reference plane normal from least-squares plane through ≥ 3 landmarks (SVD of centred points, smallest … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-31) |
| Geometry Operations | ALG-31 Anatomical frame construction from named landmarks [coordinate systems / anatomical landmarks] |
| Output Data | Inherited from FN-KFR-02 |
| Output Data Structures | Inherited from FN-KFR-02 |
| Error Handling | Inherited from FN-KFR-02 |
| Performance Requirements | Inherited from FN-KFR-02 — complexity: ALG-31: O(k) for k landmarks |
| Dependencies | Inherited from FN-KFR-02 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-31: Kabsch/Umeyama template fit (post-MVP visit registration, F-SRC-07); PCA of scan (rejected: depends on scan extent). |
| Security Considerations | Inherited from FN-KFR-02 |
| Verification Strategy | T — verified within FN-KFR-02 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KFR-02.3 (proposed id)<br>Isolated test of this step with positive and negative cases: L/R side signs and label-mismatch warnings.<br>ALG-31: Analytic landmark sets → exact axes; swapped labels → warning. Invariants: RᵀR = I; det = +1; frame equivariance under rigid motion of input. |
| Integration Test Requirements | Inherited from FN-KFR-02 |
| Open Technical Questions | Inherited from FN-KFR-02 |

#### FN-KFR-03 — Transform algebra and reflection guard

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KFR-03 |
| Function Name | Transform algebra and reflection guard |
| Related Requirement IDs | SAF-03; FR-031 |
| Architecture Component | C4/K03 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Single implementation of 4×4 rigid transforms with explicit from/to frames. Compose, invert, apply; every stored transform passes the reflection guard (INV-06). |
| Input Data | Matrices with frame tags · Preconditions: — |
| Input Data Structures | float64[4,4] + {from, to} · module baseline DS |
| Processing Algorithm | 1. compose(A:F1→F2, B:F2→F3) checks tags; inverse uses Rᵀ; apply to points (homogeneous) and to directions (R only).<br>2. guard: orthonormality and det within 1e-9 of +1.<br>Algorithms: ALG-32 Rigid transform algebra and reflection guard |
| Mathematical Model | T⁻¹ = [[Rᵀ, −Rᵀt],[0,1]].<br>ALG-32: 4×4 homogeneous matrices with explicit (from, to) frame tags; composition checks tag compatibility; inverse via [Rᵀ, −Rᵀt]; validity: ‖RᵀR − I‖_F ≤ 1e-9 and det R = +1 ± 1e-9; any reflection (det −1) is rejected (SAF-03, ADR-009). Export frame F_export … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-32) |
| Geometry Operations | ALG-32 Rigid transform algebra and reflection guard [coordinate systems] |
| Output Data | Matrices / transformed arrays. |
| Output Data Structures | Arrays · module baseline DS |
| Error Handling | Frame tag mismatch → programming error.<br>Reflection → REFLECTION_REJECTED.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-32: O(n) to apply |
| Dependencies | Functions: none |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-32: Quaternion storage (no advantage for audit; matrices are what manifests carry). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-031; TC-SAF-03; UT-FN-KFR-03 (proposed) · suites: VER-01, VER-03 · evidence level L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KFR-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Property test: random rigid transforms round-trip within 1e-12 mm; a reflection matrix is rejected.<br>ALG-32: Compose/inverse identities; mirror rejected. Invariants: T∘T⁻¹ = I; det preserved.<br>One negative test per error code: REFLECTION_REJECTED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-031; TC-SAF-03; UT-FN-KFR-03 (proposed) |
| Open Technical Questions | None registered |

#### FN-KFR-04 — Export frame transform

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KFR-04 |
| Function Name | Export frame transform |
| Related Requirement IDs | FR-100; SAF-03; STK-04 |
| Architecture Component | C4/K03 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Place the approved positive in the documented export frame F_export (DEC-015). F_export is defined relative to F_anat by the configured export_frame rule (clinic value). |
| Input Data | V (F_anat), export_frame {origin_rule, axes} · Preconditions: export_frame configured. |
| Input Data Structures | Arrays + config · module baseline DS |
| Processing Algorithm | 1. Build T_anat→export from the rule (permutation/sign of anatomical axes + origin offset); guard det = +1.<br>2. Apply to vertices; record matrix in manifest.<br>Algorithms: ALG-32 Rigid transform algebra and reflection guard; ALG-52 Export frame transform and manufacturing geometry hand-off |
| Mathematical Model | ALG-32: 4×4 homogeneous matrices with explicit (from, to) frame tags; composition checks tag compatibility; inverse via [Rᵀ, −Rᵀt]; validity: ‖RᵀR − I‖_F ≤ 1e-9 and det R = +1 ± 1e-9; any reflection (det −1) is rejected (SAF-03, ADR-009). Export frame F_export … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-32)<br>ALG-52: F_export = rule(F_anat) from configuration (origin, axes; DEC-015, UD-16); export geometry = approved positive (re-generated by replay, hash re-checked) transformed by T_anat→export (det +1); written as binary STL mm (ALG-06) with manifest … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-52) |
| Geometry Operations | ALG-32 Rigid transform algebra and reflection guard [coordinate systems]; ALG-52 Export frame transform and manufacturing geometry hand-off [manufacturing geometry / head surface input] |
| Output Data | V in F_export. |
| Output Data Structures | Arrays · module baseline DS |
| Error Handling | NOT_SET → CONFIG_NOT_SET (export gate E2).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-32: O(n) to apply; ALG-52: O(m) |
| Dependencies | Functions: FN-KFR-03; FN-CFG-04 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-32: Quaternion storage (no advantage for audit; matrices are what manifests carry).; ALG-52: 3MF with embedded units (post-MVP). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-100; TC-SAF-03; UT-FN-KFR-04 (proposed) · suites: VER-03, VER-06 · evidence level L1, L1/L2 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KFR-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Laterality object: feature centroid on the same side of the mid-sagittal plane in the exported STL (VER-03).<br>ALG-32: Compose/inverse identities; mirror rejected. Invariants: T∘T⁻¹ = I; det preserved.<br>ALG-52: Manifest schema validation. Invariants: Exported geometry = approved geometry within 1e-4 mm.<br>One negative test per error code: CONFIG_NOT_SET, NOT_SET |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-100; TC-SAF-03; UT-FN-KFR-04 (proposed) |
| Open Technical Questions | None registered |

### Module KAN — Kernel anchors and coverage

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Geometry Engine / — |
| Runtime and execution | C4 worker process (pure function, single-threaded numerics); never in C3 request threads except hashing helpers · Pure function called by jobs |
| Input data structures | DS-01 + typed params (DS-03 schema) |
| Output data structures | DS-05 (outputs + report) |
| Interfaces | IF-03 |
| External libraries | LIB-NUMPY; LIB-SCIPY |
| Performance | Complexity per ALG; wall-time budgets TBD via BM-01/BM-02 (PM-04…08) |
| Security | Pure function: no I/O, no clock, no randomness; inputs validated by OpSpec schemas; display_only inputs rejected (INV-10) |
| Integration tests | Called through the job runner on fixture designs; results persisted and re-read; determinism over 100 runs (VER-07) |
| Alternatives | See ALGORITHM_CATALOG alternatives |
| Versioning | op_version per op; kernel_version + image digest per result |

#### FN-KAN-01 — Closest-point snap to surface

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KAN-01 |
| Function Name | Closest-point snap to surface |
| Related Requirement IDs | FR-030; DATA-15; FR-071 |
| Architecture Component | C4/K04 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Turn a picked hint into an exact surface anchor. BVH closest-point query on the full-resolution scan_prepared (07 §6.4). |
| Input Data | hint_xyz_mm (F_scan), V, F, BVH · Preconditions: scan_prepared exists. |
| Input Data Structures | float64[3] + arrays · module baseline DS |
| Processing Algorithm | 1. Query BVH for the nearest triangle; exact point–triangle closest point by Voronoi-region classification (Ericson 2005).<br>2. Ties (\|Δd\| < 1e-12 mm) → smallest face_id.<br>3. Return face_id, barycentric (u, v, w) with u+v+w = 1, xyz = u·a + v·b + w·c, distance d.<br>Algorithms: ALG-33 BVH closest point, anchor snap and anchor evaluation |
| Mathematical Model | min over triangles of ‖h − q(f)‖; q(f) via region tests on (a, b, c).<br>ALG-33: AABB BVH over faces; closest point on triangle by Voronoi-region classification (Ericson) → (face_id, barycentric, feature type {face, edge, vertex}); ties (equal distance) broken by smallest face_id. Anchor evaluation x = b₀v_{f0} + b₁v_{f1} + b₂v_{f2} on … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-33) |
| Geometry Operations | ALG-33 BVH closest point, anchor snap and anchor evaluation [anatomical landmarks / geometric comparison] |
| Output Data | Anchor. |
| Output Data Structures | JSON {face_id, bary[3], xyz_mm[3], snap_distance_mm} · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-33: Build O(m log m); query O(log m) expected [N] |
| Dependencies | Functions: FN-KIO-05 · Technical decisions: TD-02 |
| External Libraries | LIB-CPP C++ (17/20) (—; RESERVE); LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-NUMBA numba (BSD-2-Clause (PyPI: "BSD"); CAND); LIB-TRIMESH trimesh (MIT; ORACLE); LIB-OPEN3D Open3D (MIT; CAND); LIB-LIBIGL libigl (Python bindings "libigl") (MPL-2.0 (core); include/igl/copyleft/* under GPL/AGPL of wrapped libraries; CAND); module baseline |
| Alternative Implementations | ALG-33: KD-tree on vertices only (wrong: closest vertex ≠ closest point). |
| Security Considerations | Module baseline · Constraint: Hint from a display LOD may be up to the LOD deviation away; the snap distance is reported and compared with the configured limit (OQ-FS-14). |
| Verification Strategy | Method T · test cases: TC-DATA-15; TC-FR-030; TC-FR-071; UT-FN-KAN-01 (proposed) · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KAN-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Stored anchors lie on the surface (distance < 1e-6 mm); brute-force comparison on 10⁴ random hints gives identical face/bary.<br>ALG-33: Point above face centre, edge, vertex regions. Invariants: Snap of an on-surface point returns itself. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-15; TC-FR-030; TC-FR-071; UT-FN-KAN-01 (proposed) |
| Open Technical Questions | TQ-05; TQ-11 |

#### FN-KAN-02 — Evaluate anchor on a mesh

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KAN-02 |
| Function Name | Evaluate anchor on a mesh |
| Related Requirement IDs | FR-030; FR-050; SAF-08 |
| Architecture Component | C4/K04 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Recover 3D positions of (face_id, bary) anchors on a mesh with the same topology. Used by frame construction, zones and smoothing regions; anchors are defined on scan_prepared. |
| Input Data | anchor, V, F, reference topology hash · Preconditions: Target mesh has the topology of the anchor's reference mesh (same F). |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Check topology hash (SHA of F) equals the anchor's reference; else ANCHOR_TOPOLOGY_CHANGED.<br>2. xyz = u·V[a] + v·V[b] + w·V[c].<br>Algorithms: ALG-33 BVH closest point, anchor snap and anchor evaluation |
| Mathematical Model | ALG-33: AABB BVH over faces; closest point on triangle by Voronoi-region classification (Ericson) → (face_id, barycentric, feature type {face, edge, vertex}); ties (equal distance) broken by smallest face_id. Anchor evaluation x = b₀v_{f0} + b₁v_{f1} + b₂v_{f2} on … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-33) |
| Geometry Operations | ALG-33 BVH closest point, anchor snap and anchor evaluation [anatomical landmarks / geometric comparison] |
| Output Data | xyz_mm. |
| Output Data Structures | float64[3] · module baseline DS |
| Error Handling | ANCHOR_TOPOLOGY_CHANGED → dependants superseded (SAF-08), no silent transfer (05 §3.7).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-33: Build O(m log m); query O(log m) expected [N] |
| Dependencies | Functions: FN-KAN-01 · Technical decisions: TD-02 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-33: KD-tree on vertices only (wrong: closest vertex ≠ closest point). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-030; TC-FR-050; TC-SAF-08; UT-FN-KAN-02 (proposed) · suites: VER-01, VER-08, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KAN-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Anchor evaluated after topology-preserving ops moves with the surface; after a cleanup change it is refused.<br>ALG-33: Point above face centre, edge, vertex regions. Invariants: Snap of an on-surface point returns itself.<br>One negative test per error code: ANCHOR_TOPOLOGY_CHANGED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-030; TC-FR-050; TC-SAF-08; UT-FN-KAN-02 (proposed) |
| Open Technical Questions | None registered |

#### FN-KAN-03 — Sector coverage analysis

*Kernel operation (pure function) · MVP · Should · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KAN-03 |
| Function Name | Sector coverage analysis |
| Related Requirement IDs | FR-172 |
| Architecture Component | C4/K04 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Report, per configured angular sector above the reference plane, whether surface data are present (FR-172). Ray-sampling around the vertical axis from the frame origin (engineering proposal; presence criterion OQ-FS-18). |
| Input Data | Mesh in F_anat, reference plane (from config rule), sector count k, elevation range, sampling density, presence threshold c_min · Preconditions: Frame confirmed; coverage_check configured. |
| Input Data Structures | Arrays + config · module baseline DS |
| Processing Algorithm | 1. For sector s (azimuth [2πs/k, 2π(s+1)/k)) sample directions on a regular azimuth × elevation grid above the reference plane (deterministic grid).<br>2. Cast each ray from the frame origin (BVH ray-triangle, Möller–Trumbore); hit if it intersects the surface.<br>3. coverage_s = hits / samples; present_s ⇔ coverage_s ≥ c_min.<br>4. Apply configured action block\|warn for any absent sector.<br>Algorithms: ALG-34 Sector coverage by ray casting; ALG-43 Region segmentation (MVP: technician-defined regions) |
| Mathematical Model | coverage_s = (1/N_s) Σ_rays 𝟙[ray hits surface].<br>ALG-34: In F_anat, above the reference plane, cast rays from the origin on a deterministic spherical grid (Fibonacci lattice with fixed count) grouped into configured angular sectors; ray–triangle intersection by Möller–Trumbore against the BVH; sector "present" … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-34)<br>ALG-43: MVP regions are explicit: (a) face sets from UI brush/lasso selection resolved on the server against full-resolution face ids; (b) disc/ellipse regions defined by an anchored centre and Euclidean radius (A-15); (c) angular sectors in F_anat (ALG-34). No … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-43) |
| Geometry Operations | ALG-34 Sector coverage by ray casting [cranial surface analysis]; ALG-43 Region segmentation (MVP: technician-defined regions) [region segmentation] |
| Output Data | Coverage report. |
| Output Data Structures | JSON {sectors[{id, coverage, present}], action} · module baseline DS |
| Error Handling | NOT_SET → CONFIG_NOT_SET.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-34: O(r log m) for r rays; ALG-43: O(selection · log m) |
| Dependencies | Functions: FN-KFR-02 · Technical decisions: TD-02 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-NUMBA numba (BSD-2-Clause (PyPI: "BSD"); CAND); LIB-OPEN3D Open3D (MIT; CAND); LIB-EMBREE Intel Embree (Python: embreex) (Apache-2.0 (Embree); embreex wrapper BSD-style (copyright notice in PyPI metadata — verify); CAND); module baseline |
| Alternative Implementations | ALG-34: Area-based criterion (projected area per sector).; ALG-43: Geodesic distance regions (potpourri3d MIT heat method, libigl exact geodesics MPL-2.0) — post-MVP. |
| Security Considerations | Module baseline · Constraint: Rays from the origin miss surfaces occluded by other surface (rare on convex-like heads); hair/cap layers count as surface. |
| Verification Strategy | Method T · test cases: TC-FR-172; UT-FN-KAN-03 (proposed) · suites: VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KAN-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Phantom with one sector removed is reported for that sector only.<br>ALG-34: Sphere full coverage; sphere with removed sector. Invariants: Rotation of mesh and sectors together leaves results unchanged.<br>ALG-43: Disc membership on plane. Invariants: Selection resolved on full mesh is the stored truth.<br>One negative test per error code: CONFIG_NOT_SET, NOT_SET |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-172; UT-FN-KAN-03 (proposed) |
| Open Technical Questions | OQ-FS-18; TQ-05; Missing data: FR-172 does not define 'surface data present'; c_min and sampling density are proposed configuration keys (OQ-FS-18). |

### Module KMS — Kernel measurement geometry

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Geometry Engine / — |
| Runtime and execution | C4 worker process (pure function, single-threaded numerics); never in C3 request threads except hashing helpers · Pure function called by jobs |
| Input data structures | DS-01 + typed params (DS-03 schema) |
| Output data structures | DS-05 (outputs + report) |
| Interfaces | IF-03 |
| External libraries | LIB-NUMPY; LIB-SCIPY |
| Performance | Complexity per ALG; wall-time budgets TBD via BM-01/BM-02 (PM-04…08) |
| Security | Pure function: no I/O, no clock, no randomness; inputs validated by OpSpec schemas; display_only inputs rejected (INV-10) |
| Integration tests | Called through the job runner on fixture designs; results persisted and re-read; determinism over 100 runs (VER-07) |
| Alternatives | See ALGORITHM_CATALOG alternatives |
| Versioning | op_version per op; kernel_version + image digest per result |

#### FN-KMS-01 — Plane section to contours

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KMS-01 |
| Function Name | Plane section to contours |
| Related Requirement IDs | FR-040; FR-047; FR-173; FR-051 |
| Architecture Component | C4/K05 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Intersect a mesh with a plane and return polylines. Robust edge-crossing extraction with a symbolic tie rule. |
| Input Data | V, F, plane (point p₀, unit normal n̂) · Preconditions: Mesh and plane in the same frame. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. d_i = n̂·(v_i − p₀); sign σ_i = +1 if d_i ≥ 0 else −1 (d_i = 0 treated as positive: equivalent to an infinitesimal shift along +n̂; no geometry is moved).<br>2. For each edge with σ_a ≠ σ_b: point x = v_a + t(v_b − v_a), t = d_a/(d_a − d_b), computed once per undirected edge.<br>3. Each crossed triangle yields one segment between its two crossing edges; chain segments via shared edge keys.<br>4. Closed contour ⇔ chain returns to start; else open polyline (ends on boundary edges).<br>5. Express contour points in plane coordinates (ê₁, ê₂) given by the caller (projected frame axes).<br>Algorithms: ALG-23 Plane section to contours with symbolic tie rule |
| Mathematical Model | Linear interpolation on edges; contours are exact intersections of the piecewise-linear surface with the plane.<br>ALG-23: Signed distances d_i = n̂·(v_i − p). Symbolic perturbation: d = 0 is treated as positive, so no vertex lies on the plane and every crossed edge (sign change) yields exactly one point x = v_a + d_a/(d_a − d_b)(v_b − v_a). Each crossed face contributes one … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-23) |
| Geometry Operations | ALG-23 Plane section to contours with symbolic tie rule [cranial measurements / closure] |
| Output Data | Contours. |
| Output Data Structures | JSON {closed[[x,y]…], open[[x,y]…]} (mm, plane coordinates) + 3D points · module baseline DS |
| Error Handling | No crossing → empty result.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-23: O(m) |
| Dependencies | Functions: FN-KIO-05 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-TRIMESH trimesh (MIT; ORACLE); module baseline |
| Alternative Implementations | ALG-23: trimesh section (tie handling and order not specified for our contract [N]); VTK vtkCutter (BSD). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-040; TC-FR-047; TC-FR-051; TC-FR-173; UT-FN-KMS-01 (proposed) · suites: VER-01, VER-02, VER-08, VER-15, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KMS-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Sphere R section perimeter within 0.032 mm of 2π√(R² − h²) on subdivision-6 phantom; plane through a vertex produces no duplicate points.<br>ALG-23: Cube cut through vertices; tetrahedron cut through edge. Invariants: Each crossed edge produces exactly one point; closed contours on closed meshes. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-040; TC-FR-047; TC-FR-051; TC-FR-173; UT-FN-KMS-01 (proposed) |
| Open Technical Questions | None registered |

##### FN-KMS-01.1 — Signed distances and tie rule

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KMS-01.1 |
| Function Name | Signed distances and tie rule  (subfunction of FN-KMS-01 Plane section to contours) |
| Related Requirement IDs | Inherited from parent FN-KMS-01: FR-040; FR-047; FR-173; FR-051 |
| Architecture Component | C4/K05 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | d_i with d = 0 treated as positive. |
| Input Data | Inherited from FN-KMS-01 |
| Input Data Structures | Inherited from FN-KMS-01 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | d_i with d = 0 treated as positive. — implemented by ALG-23 |
| Mathematical Model | ALG-23: Signed distances d_i = n̂·(v_i − p). Symbolic perturbation: d = 0 is treated as positive, so no vertex lies on the plane and every crossed edge (sign change) yields exactly one point x = v_a + d_a/(d_a − d_b)(v_b − v_a). Each crossed face contributes one … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-23) |
| Geometry Operations | ALG-23 Plane section to contours with symbolic tie rule [cranial measurements / closure] |
| Output Data | Inherited from FN-KMS-01 |
| Output Data Structures | Inherited from FN-KMS-01 |
| Error Handling | Inherited from FN-KMS-01 |
| Performance Requirements | Inherited from FN-KMS-01 — complexity: ALG-23: O(m) |
| Dependencies | Inherited from FN-KMS-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-TRIMESH trimesh (MIT; ORACLE); module baseline |
| Alternative Implementations | ALG-23: trimesh section (tie handling and order not specified for our contract [N]); VTK vtkCutter (BSD). |
| Security Considerations | Inherited from FN-KMS-01 |
| Verification Strategy | T — verified within FN-KMS-01 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KMS-01.1 (proposed id)<br>Isolated test of this step with positive and negative cases: d_i with d = 0 treated as positive.<br>ALG-23: Cube cut through vertices; tetrahedron cut through edge. Invariants: Each crossed edge produces exactly one point; closed contours on closed meshes. |
| Integration Test Requirements | Inherited from FN-KMS-01 |
| Open Technical Questions | Inherited from FN-KMS-01 |

##### FN-KMS-01.2 — Edge crossings

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KMS-01.2 |
| Function Name | Edge crossings  (subfunction of FN-KMS-01 Plane section to contours) |
| Related Requirement IDs | Inherited from parent FN-KMS-01: FR-040; FR-047; FR-173; FR-051 |
| Architecture Component | C4/K05 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | One interpolated point per crossed edge. |
| Input Data | Inherited from FN-KMS-01 |
| Input Data Structures | Inherited from FN-KMS-01 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | One interpolated point per crossed edge. — implemented by ALG-23 |
| Mathematical Model | ALG-23: Signed distances d_i = n̂·(v_i − p). Symbolic perturbation: d = 0 is treated as positive, so no vertex lies on the plane and every crossed edge (sign change) yields exactly one point x = v_a + d_a/(d_a − d_b)(v_b − v_a). Each crossed face contributes one … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-23) |
| Geometry Operations | ALG-23 Plane section to contours with symbolic tie rule [cranial measurements / closure] |
| Output Data | Inherited from FN-KMS-01 |
| Output Data Structures | Inherited from FN-KMS-01 |
| Error Handling | Inherited from FN-KMS-01 |
| Performance Requirements | Inherited from FN-KMS-01 — complexity: ALG-23: O(m) |
| Dependencies | Inherited from FN-KMS-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-TRIMESH trimesh (MIT; ORACLE); module baseline |
| Alternative Implementations | ALG-23: trimesh section (tie handling and order not specified for our contract [N]); VTK vtkCutter (BSD). |
| Security Considerations | Inherited from FN-KMS-01 |
| Verification Strategy | T — verified within FN-KMS-01 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KMS-01.2 (proposed id)<br>Isolated test of this step with positive and negative cases: One interpolated point per crossed edge.<br>ALG-23: Cube cut through vertices; tetrahedron cut through edge. Invariants: Each crossed edge produces exactly one point; closed contours on closed meshes. |
| Integration Test Requirements | Inherited from FN-KMS-01 |
| Open Technical Questions | Inherited from FN-KMS-01 |

##### FN-KMS-01.3 — Segment chaining

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KMS-01.3 |
| Function Name | Segment chaining  (subfunction of FN-KMS-01 Plane section to contours) |
| Related Requirement IDs | Inherited from parent FN-KMS-01: FR-040; FR-047; FR-173; FR-051 |
| Architecture Component | C4/K05 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Closed contours and open polylines. |
| Input Data | Inherited from FN-KMS-01 |
| Input Data Structures | Inherited from FN-KMS-01 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Closed contours and open polylines. — implemented by ALG-23 |
| Mathematical Model | ALG-23: Signed distances d_i = n̂·(v_i − p). Symbolic perturbation: d = 0 is treated as positive, so no vertex lies on the plane and every crossed edge (sign change) yields exactly one point x = v_a + d_a/(d_a − d_b)(v_b − v_a). Each crossed face contributes one … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-23) |
| Geometry Operations | ALG-23 Plane section to contours with symbolic tie rule [cranial measurements / closure] |
| Output Data | Inherited from FN-KMS-01 |
| Output Data Structures | Inherited from FN-KMS-01 |
| Error Handling | Inherited from FN-KMS-01 |
| Performance Requirements | Inherited from FN-KMS-01 — complexity: ALG-23: O(m) |
| Dependencies | Inherited from FN-KMS-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-TRIMESH trimesh (MIT; ORACLE); module baseline |
| Alternative Implementations | ALG-23: trimesh section (tie handling and order not specified for our contract [N]); VTK vtkCutter (BSD). |
| Security Considerations | Inherited from FN-KMS-01 |
| Verification Strategy | T — verified within FN-KMS-01 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KMS-01.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Closed contours and open polylines.<br>ALG-23: Cube cut through vertices; tetrahedron cut through edge. Invariants: Each crossed edge produces exactly one point; closed contours on closed meshes. |
| Integration Test Requirements | Inherited from FN-KMS-01 |
| Open Technical Questions | Inherited from FN-KMS-01 |

#### FN-KMS-02 — Select measurement contour

*Kernel operation (pure function) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-KMS-02 |
| Function Name | Select measurement contour |
| Related Requirement IDs | FR-040; FR-047 |
| Architecture Component | C4/K05 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Choose the head cross-section among section contours deterministically. Proposed rule (OQ-FS-03): the closed contour that encloses the projection of the frame origin onto the plane. |
| Input Data | Closed and open contours, point c (origin projection) · Preconditions: Contours from FN-KMS-01. |
| Input Data Structures | Plane coordinates · module baseline DS |
| Processing Algorithm | 1. Candidates = closed contours containing c (even–odd point-in-polygon).<br>2. Exactly one → selected.<br>3. Zero closed contours → NOT_COMPUTED reason CONTOUR_NOT_CLOSED.<br>4. None containing c or more than one → NOT_COMPUTED reason CONTOUR_AMBIGUOUS (shown with all contours drawn, FR-047).<br>Algorithms: ALG-35 Measurement contour selection |
| Mathematical Model | ALG-35: Among closed contours of the measurement section: rule ∈ {enclosing origin projection (point-in-polygon, exact orient2d), largest perimeter, technician pick}. Open polylines are never measured (FR-040 error flow). |
| Geometry Operations | ALG-35 Measurement contour selection [cranial measurements] |
| Output Data | Selected contour or reason. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | See logic (value not computed, reason shown — FR-040 error behaviour).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-35: O(Σk) |
| Dependencies | Functions: FN-KMS-01 · Technical decisions: TD-04 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-PREDICATES Shewchuk robust predicates (own port) (Public domain (original); JS port robust-predicates under Unlicense; R-MVP); module baseline |
| Alternative Implementations | ALG-35: See OQ-FS-03. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-040; TC-FR-047; UT-FN-KMS-02 (proposed) · suites: VER-01, VER-02, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KMS-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Phantom with an extra disjoint closed contour (e.g. ear) selects the head contour; two nested candidates → CONTOUR_AMBIGUOUS.<br>ALG-35: Two contours (head + ear artefact). Invariants: Selection independent of contour order. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-040; TC-FR-047; UT-FN-KMS-02 (proposed) |
| Open Technical Questions | OQ-FS-03; Missing data: FR-040/DATA-02 do not specify contour selection when several closed contours exist (GAP-M11). |

#### FN-KMS-03 — Compute cranial index (CI)

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KMS-03 |
| Function Name | Compute cranial index (CI) |
| Related Requirement IDs | FR-040 |
| Architecture Component | C4/K05 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Width/length ratio on the selected contour. Axis-parallel maximal extents in the measurement plane. |
| Input Data | Contour points (plane coordinates aligned with projected A-P and M-L axes) · Preconditions: Selected contour; definition CI. |
| Input Data Structures | mm · module baseline DS |
| Processing Algorithm | 1. L = max_i x_i − min_i x_i along projected A-P axis; W = max_i y_i − min_i y_i along projected M-L axis.<br>2. CI = 100·W/L.<br>3. Return W, L, CI and the extreme points (for FR-047 display).<br>Algorithms: ALG-36 Cranial index (CI) on a contour |
| Mathematical Model | CI = 100·W/L; extremes of a polygon along a direction occur at vertices, so the computation is exact for the contour.<br>ALG-36: L = extent of the contour along the A-P axis, W = extent along the M-L axis (both in F_anat, measured within the section plane); CI = 100·W/L. Extents from projections of contour points (piecewise-linear contour → extremes at vertices). |
| Geometry Operations | ALG-36 Cranial index (CI) on a contour [cranial measurements] |
| Output Data | Value + geometry. |
| Output Data Structures | JSON {CI, W_mm, L_mm, extreme_points} · module baseline DS |
| Error Handling | L = 0 → NOT_COMPUTED (degenerate).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-36: O(k) |
| Dependencies | Functions: FN-KMS-02 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-36: Caliper on point cloud (same result on vertices). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-040; UT-FN-KMS-03 (proposed) · suites: VER-01, VER-02 · evidence level L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KMS-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Ellipsoid phantom W=130, L=150 mm: \|δCI\| ≤ 100·(e/L + W·e/L²) with e = 0.011 mm.<br>ALG-36: Ellipse contour analytic CI. Invariants: Scale invariance of CI.<br>One negative test per error code: NOT_COMPUTED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-040; UT-FN-KMS-03 (proposed) |
| Open Technical Questions | None registered |

#### FN-KMS-04 — Compute diagonals, CVA and CVAI variants

*Kernel operation (pure function) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-KMS-04 |
| Function Name | Compute diagonals, CVA and CVAI variants |
| Related Requirement IDs | FR-040; FR-042 |
| Architecture Component | C4/K05 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Diagonal difference measures under the selected definition (angle θ, denominator rule). Two diagonals at ±θ from the projected A-P axis through the definition's centre point. |
| Input Data | Contour, θ (deg), centre rule (OQ-FS-03), denominator ∈ {shorter, longer} · Preconditions: Selected contour; CVA/CVAI definition. |
| Input Data Structures | mm, deg · module baseline DS |
| Processing Algorithm | 1. Directions d₁ = Rot(+θ)·x̂, d₂ = Rot(−θ)·x̂ in the plane (x̂ = projected A-P axis).<br>2. Centre c per definition rule (proposed options: projection of frame origin, or area centroid of the contour).<br>3. For each direction: intersect line c + t·d with all contour segments; D = t_max(>0) − t_min(<0) (outermost crossings).<br>4. CVA = \|D₁ − D₂\|; CVAI = 100·\|D₁ − D₂\| / (min or max of D₁, D₂).<br>5. Also return which diagonal is longer, labelled by side from the frame (for display only, no interpretation).<br>Algorithms: ALG-37 Diagonals, CVA and CVAI variants |
| Mathematical Model | Line–segment intersection in 2D; CVA = \|D₁ − D₂\|; CVAI_short = 100·CVA/min(D₁,D₂); CVAI_long = 100·CVA/max(D₁,D₂).<br>ALG-37: Two diagonals at ±θ (θ = 30° or 40° presets, DEC-027) from the reference axis, through centre c (rule OQ-FS-03); each diagonal length D = distance between the two intersections of the line with the contour (ray–polygon intersection in plane coordinates, … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-37) |
| Geometry Operations | ALG-37 Diagonals, CVA and CVAI variants [cranial measurements / symmetry analysis] |
| Output Data | Values + diagonal segments. |
| Output Data Structures | JSON {D1_mm, D2_mm, CVA_mm, CVAI, diagonals[2][2 points]} · module baseline DS |
| Error Handling | Line misses contour on one side (c outside contour) → NOT_COMPUTED DIAGONAL_UNDEFINED.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-37: O(k) |
| Dependencies | Functions: FN-KMS-02 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-37: Diagonal through contour centroid vs origin projection (OQ-FS-03). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-040; TC-FR-042; UT-FN-KMS-04 (proposed) · suites: VER-01, VER-02 · evidence level L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KMS-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Asymmetric ellipsoid phantom: values equal analytic values within propagated VER-01 tolerance for 30° and 40°, both denominators.<br>ALG-37: Asymmetric ellipse with known diagonal difference. Invariants: Mirror of contour swaps D₁, D₂ and leaves CVA unchanged.<br>One negative test per error code: DIAGONAL_UNDEFINED, NOT_COMPUTED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-040; TC-FR-042; UT-FN-KMS-04 (proposed) |
| Open Technical Questions | OQ-FS-03; TQ-18; Missing data: DATA-02 lacks the diagonal centre rule and the reference axis of the angle (GAP-M12). |

#### FN-KMS-05 — Compute head circumference (HC)

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KMS-05 |
| Function Name | Compute head circumference (HC) |
| Related Requirement IDs | FR-040 |
| Architecture Component | C4/K05 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Perimeter of the selected contour at the definition's plane/level. Polyline length. |
| Input Data | Contour · Preconditions: Selected contour; HC definition. |
| Input Data Structures | mm · module baseline DS |
| Processing Algorithm | 1. HC = Σ ‖p_{i+1} − p_i‖ over the closed contour.<br>Algorithms: ALG-38 Head circumference (HC) as contour perimeter |
| Mathematical Model | Chord-polygon perimeter; underestimates the smooth curve by O(h²) (DEC-025 table).<br>ALG-38: HC = Σ‖p_{i+1} − p_i‖ over the closed selected contour at the definition plane/level. Chord error vs a smooth head is a property of the mesh (DEC-025 perimeter tolerance 0.032 mm at s = 6). |
| Geometry Operations | ALG-38 Head circumference (HC) as contour perimeter [cranial measurements] |
| Output Data | HC (mm). |
| Output Data Structures | float64 · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-38: O(k) |
| Dependencies | Functions: FN-KMS-02 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-38: Tape-measure emulation (convex hull perimeter) — differs on concavities; definition choice for the clinic (record in definition). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-040; UT-FN-KMS-05 (proposed) · suites: VER-01, VER-02 · evidence level L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KMS-05 (proposed id)<br>Acceptance criteria as unit/component assertions: Sphere phantom section perimeter within 0.032 mm (DEC-025).<br>ALG-38: Square contour perimeter. Invariants: Rigid motion invariance. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-040; UT-FN-KMS-05 (proposed) |
| Open Technical Questions | None registered |

#### FN-KMS-06 — Synthetic-surface contact flag

*Kernel operation (pure function) · MVP · Should · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KMS-06 |
| Function Name | Synthetic-surface contact flag |
| Related Requirement IDs | FR-021 |
| Architecture Component | C4/K05 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Warn when a measurement passes over hole-filled (synthetic) surface. Checks the faces crossed by the selected contour and diagonal endpoints. |
| Input Data | Face IDs of contour segments; synthetic attribute · Preconditions: Faces carry synthetic flag (FN-KOP-02). |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. If any crossed face is synthetic → flag synthetic_contact=true with the count of segments.<br>Algorithms: ALG-39 Synthetic-surface contact flag |
| Mathematical Model | ALG-39: A measurement is flagged if its contour passes through any face tagged synthetic (hole fill) — via source edge keys of contour points → incident faces → tags. |
| Geometry Operations | ALG-39 Synthetic-surface contact flag [cranial measurements] |
| Output Data | Flag. |
| Output Data Structures | JSON {synthetic_contact, segments} · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-39: O(k) |
| Dependencies | Functions: FN-KMS-01; FN-KOP-02 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-39: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-021; UT-FN-KMS-06 (proposed) · suites: VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KMS-06 (proposed id)<br>Acceptance criteria as unit/component assertions: Contour across a filled hole is flagged; otherwise not.<br>ALG-39: Contour across filled hole → flag. Invariants: No synthetic faces → never flagged. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-021; UT-FN-KMS-06 (proposed) |
| Open Technical Questions | OQ-FS-27; Missing data: Required only by backlog BL-028 acceptance, not by an RTM row (GAP-M17). |

### Module KOP — Kernel modelling operations

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Geometry Engine / Validation Layer (guards) |
| Runtime and execution | C4 worker process (pure function, single-threaded numerics); never in C3 request threads except hashing helpers · Pure function called by jobs |
| Input data structures | DS-01 + typed params (DS-03 schema) |
| Output data structures | DS-05 (outputs + report) |
| Interfaces | IF-03 |
| External libraries | LIB-NUMPY; LIB-SCIPY |
| Performance | Complexity per ALG; wall-time budgets TBD via BM-01/BM-02 (PM-04…08) |
| Security | Pure function: no I/O, no clock, no randomness; inputs validated by OpSpec schemas; display_only inputs rejected (INV-10) |
| Integration tests | Called through the job runner on fixture designs; results persisted and re-read; determinism over 100 runs (VER-07) |
| Alternatives | See ALGORITHM_CATALOG alternatives |
| Versioning | op_version per op; kernel_version + image digest per result |

#### FN-KOP-01 — Remove faces (cleanup.remove_faces)

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-01 |
| Function Name | Remove faces (cleanup.remove_faces) |
| Related Requirement IDs | FR-020; FR-023; DATA-16 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Delete selected non-head regions as a recorded, reproducible operation. Removes faces by ID from the op input and compacts vertices. |
| Input Data | V, F, face_ids (sorted unique) · Preconditions: Face IDs refer to this op's input. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. keep = all faces not in face_ids (order preserved).<br>2. Compact vertices referenced by kept faces (order preserved).<br>3. Return removed face set (input indices) for DATA-16.<br>Algorithms: ALG-09 Connected components; ALG-15 Recorded face removal and compaction (mesh cleaning); ALG-22 Mesh repair policy (explicit recorded repair only) |
| Mathematical Model | ALG-09: Graph on faces with an edge for each shared undirected edge (manifold or not) → scipy.sparse.csgraph.connected_components; components ordered by (−face count, min face id) for deterministic labels.<br>ALG-15: Remove a set of face ids (from UI selection or component labels) and compact vertices keeping relative order; record (op type, op_version, face_ids on input mesh) so replay is exact (FR-020, FR-023).<br>ALG-22: No silent repair (05 §6.2). Repair = composition of recorded ops chosen by the technician: remove faces/components (ALG-15), fill selected holes (ALG-16), optional orientation normalisation (ALG-10, OQ-FS-37). Each op is versioned, replayable and visible … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-22) |
| Geometry Operations | ALG-09 Connected components [connected components]; ALG-15 Recorded face removal and compaction (mesh cleaning) [mesh cleaning / mesh repair]; ALG-22 Mesh repair policy (explicit recorded repair only) [mesh repair] |
| Output Data | Mesh + removed set. |
| Output Data Structures | Arrays + int32[] · module baseline DS |
| Error Handling | Face ID out of range → PARAM_INVALID.<br>All faces removed → OP_REJECTED_EMPTY.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-09: O(m); ALG-15: O(m + n); ALG-22: Sum of ops |
| Dependencies | Functions: FN-KRP-04; FN-KIO-05 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-09: Vertex-connectivity (merges bow-ties); union-find own.; ALG-15: Region growing by curvature (post-MVP segmentation, ALG-43).; ALG-22: Automatic repair (pymeshfix — AGPL-3.0 per PyPI, rejected; MeshLab filters — GPL). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-16; TC-FR-020; TC-FR-023; UT-FN-KOP-01 (proposed) · suites: VER-07, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Re-application on the same input yields identical geometry hash; removed count = len(face_ids).<br>ALG-09: Two disjoint spheres → 2; bow-tie → 2 (edge rule). Invariants: Σ faces = m; labels independent of input face permutation up to the documented order rule.<br>ALG-15: Remove one face; remove a component. Invariants: Remaining face coordinates bit-identical.<br>ALG-22: Op list replay equality. Invariants: Disable all ops → original hash.<br>One negative test per error code: OP_REJECTED_EMPTY, PARAM_INVALID |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-16; TC-FR-020; TC-FR-023; UT-FN-KOP-01 (proposed) |
| Open Technical Questions | None registered |

#### FN-KOP-02 — Fill selected holes (cleanup.fill_holes)

*Kernel operation (pure function) · MVP · Should · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-02 |
| Function Name | Fill selected holes (cleanup.fill_holes) |
| Related Requirement IDs | FR-021 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Close technician-chosen boundary loops up to a perimeter limit; new faces flagged synthetic. Liepa (2003) pipeline: minimum-weight triangulation of the loop, refinement to local edge density, optional fairing. |
| Input Data | V, F, loop_ids, max_perimeter_mm, refine (bool), fair (bool) · Preconditions: Loop IDs from FN-KVL-01 on this op's input; each loop simple. |
| Input Data Structures | Arrays + params · module baseline DS |
| Processing Algorithm | 1. Reject loops with perimeter > max_perimeter_mm (FR-021).<br>2. Minimum-weight triangulation by dynamic programming over loop vertices with weight (max dihedral angle to neighbours, area) compared lexicographically.<br>3. Refinement: split triangles whose edges exceed the mean adjacent boundary edge length × √2, relax.<br>4. Fairing (if enabled): solve the discrete Laplace (umbrella) system for interior patch vertices with boundary fixed (sparse direct solve).<br>5. Mark new faces synthetic=1; run FN-KOP-13 guard.<br>Algorithms: ALG-16 Hole filling: minimum-weight triangulation + refinement (+ optional fairing); ALG-22 Mesh repair policy (explicit recorded repair only); ALG-50 Post-operation geometric guard |
| Mathematical Model | DP: W(i,k) = min_{i<m<k} W(i,m) + W(m,k) + w(i,m,k), O(n³); fairing: L x = 0 on patch interior.<br>ALG-16: Liepa (2003): (1) triangulate the boundary polygon by dynamic programming minimising (max dihedral angle, then area) — O(n³); (2) refine patch so triangle sizes match the boundary edge density (σ-density criterion, Delaunay-like edge swaps); (3) optional … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-16)<br>ALG-22: No silent repair (05 §6.2). Repair = composition of recorded ops chosen by the technician: remove faces/components (ALG-15), fill selected holes (ALG-16), optional orientation normalisation (ALG-10, OQ-FS-37). Each op is versioned, replayable and visible … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-22)<br>ALG-50: After every design op: (1) incremental self-intersection test on faces touching moved vertices (ALG-11 incremental); (2) face normal flip test: n_f'·n_f ≤ 0 for any face → reject; (3) sign check: for ops with signed magnitude, sign of displacement along n̂ … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-50) |
| Geometry Operations | ALG-16 Hole filling: minimum-weight triangulation + refinement (+ optional fairing) [hole filling]; ALG-22 Mesh repair policy (explicit recorded repair only) [mesh repair]; ALG-50 Post-operation geometric guard [geometric constraints] |
| Output Data | Mesh with filled loops. |
| Output Data Structures | Arrays + synthetic face mask · module baseline DS |
| Error Handling | Loop with n > n_max (proposed 2000 vertices) → OP_REJECTED_LOOP_TOO_LARGE.<br>Self-intersection created → op rejected (FN-KOP-13).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-16: O(n³) per loop (DP) + sparse solve O(p^1.5) typical for p patch vertices [N]; ALG-22: Sum of ops; ALG-50: Incremental: O(k log m) for k affected faces [H] |
| Dependencies | Functions: FN-KVL-01; FN-KOP-13 · Technical decisions: TD-06 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-SCIPY scipy (BSD-3-Clause (classifier: BSD License); R-MVP); LIB-CGAL CGAL (PMP, Alpha Wrap, corefinement) (GPL-3.0+ for most algorithm packages, LGPL-3.0+ for kernel/support; commercial licence from GeometryFactory; ORACLE); LIB-MESHLIB MeshLib SDK (LicenseRef-MeshLib: free for non-commercial/educational use; commercial licence required for business use; REJECT); module baseline |
| Alternative Implementations | ALG-16: trimesh fill_holes (trivial holes only [N]); alpha wrap (moves whole surface, rejected); screened Poisson (replaces surface).; ALG-22: Automatic repair (pymeshfix — AGPL-3.0 per PyPI, rejected; MeshLab filters — GPL).; ALG-50: Full validation after every op (slower). |
| Security Considerations | Module baseline · Constraint: Patches are invented surface (RG-04); measurements crossing them are flagged (FN-KMS-06). |
| Verification Strategy | Method T · test cases: TC-FR-021; UT-FN-KOP-02 (proposed) · suites: VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-02 (proposed id)<br>Acceptance criteria as unit/component assertions: VER-08 holed meshes: all selected loops ≤ limit closed, larger untouched; synthetic flag set on new faces only.<br>ALG-16: Planar circular hole → patch planar; triangle count ~ boundary density. Invariants: Faces outside patch bit-identical; boundary vertices fixed; result loop count decreases by number of filled loops.<br>ALG-22: Op list replay equality. Invariants: Disable all ops → original hash.<br>ALG-50: Fold-inducing zone → rejected; benign zone → accepted. Invariants: Rejected op leaves geometry hash unchanged (TC-SAF-09).<br>One negative test per error code: OP_REJECTED_LOOP_TOO_LARGE |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-021; UT-FN-KOP-02 (proposed) |
| Open Technical Questions | OQ-FS-16; OQ-FS-28; TQ-12 |

#### FN-KOP-03 — Decimate as recorded operation (cleanup.decimate)

*Kernel operation (pure function) · MVP · Should · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-03 |
| Function Name | Decimate as recorded operation (cleanup.decimate) |
| Related Requirement IDs | FR-022; NFR-03 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Reduce triangle count to a target when meshes exceed NFR-03, with displacement reported. Topology-preserving quadric-error edge collapse (Garland–Heckbert) with link-condition check and boundary preservation. |
| Input Data | V, F, target_faces · Preconditions: Mesh manifold in the region of collapses. |
| Input Data Structures | Arrays + int · module baseline DS |
| Processing Algorithm | 1. Compute quadrics per vertex; priority queue of edge collapses by error.<br>2. Skip collapses violating the link condition, flipping a face normal by > 90°, or touching boundary vertices.<br>3. Stop at target_faces (±1%).<br>4. Report one-sided Hausdorff from output vertices to input surface (FN-KCP-04).<br>5. Run manifold check.<br>Algorithms: ALG-17 Quadric error metric decimation with topology constraints; ALG-41 Deviation statistics and one-sided vertex-to-surface Hausdorff |
| Mathematical Model | Q_v = Σ_planes p pᵀ; collapse cost vᵀ(Q₁+Q₂)v; optimal v̄ solves the 3×3 system (fallback to best of endpoints/midpoint).<br>ALG-17: Garland–Heckbert: each vertex accumulates Q = Σ p pᵀ over incident face planes; edge collapse cost = v̄ᵀ(Q₁+Q₂)v̄ at the optimal or endpoint position; greedy by priority queue. Constraints: link condition (prevents non-manifold), boundary-edge lock (or … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-17)<br>ALG-41: Per region (zone id from op parameters, or whole mesh): min, max, mean, RMS of a per-vertex distance field; one-sided Hausdorff h(A→B) = max_{a∈V_A} d(a, B) using vertex samples (documented as vertex-sampled, a lower bound of the continuous Hausdorff). |
| Geometry Operations | ALG-17 Quadric error metric decimation with topology constraints [mesh decimation]; ALG-41 Deviation statistics and one-sided vertex-to-surface Hausdorff [geometric comparison] |
| Output Data | Decimated mesh + report. |
| Output Data Structures | Arrays + JSON {faces, max_displacement_mm} · module baseline DS |
| Error Handling | Cannot reach target without violating constraints → result at best reachable count with warning TARGET_NOT_REACHED.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-17: O(m log m); ALG-41: O(n) |
| Dependencies | Functions: FN-KCP-04; FN-KVL-01 · Technical decisions: TD-11 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-VTK VTK (BSD-3-Clause; CAND); module baseline |
| Alternative Implementations | ALG-17: Vertex clustering (fast, poor quality); edge-length based; remeshing (ALG-20).; ALG-41: Face-sampled Hausdorff (Metro-style) — post-MVP. |
| Security Considerations | Module baseline · Constraint: Changes topology; landmarks/zones anchored before it are invalidated (FN-KAN-02); hence cleanup-only. |
| Verification Strategy | Method T · test cases: TC-FR-022; UT-FN-KOP-03 (proposed) · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Output count within ±1% of target; displacement reported; output manifold.<br>ALG-17: Planar grid decimates to 2 triangles with zero error. Invariants: Output manifold if input manifold; Euler characteristic preserved (genus kept).<br>ALG-41: Hand fields. Invariants: Stats of field + c shift by c.<br>One negative test per error code: TARGET_NOT_REACHED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-022; UT-FN-KOP-03 (proposed) |
| Open Technical Questions | OQ-FS-17 |

#### FN-KOP-04 — Display LOD generation

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-04 |
| Function Name | Display LOD generation |
| Related Requirement IDs | NFR-03; NFR-02 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Produce browser-sized meshes for viewing only (INV-10). Same decimation family; output flagged display_only and encoded as jude-mesh/1. |
| Input Data | V, F, optional scalar field, target_faces_display · Preconditions: Source artifact. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. If F ≤ target → no decimation.<br>2. Else decimate; carry scalar field by nearest source vertex.<br>3. Encode jude-mesh/1 (mm, F_anat if frame exists).<br>Algorithms: ALG-17 Quadric error metric decimation with topology constraints; ALG-56 Display LOD payload (jude-mesh/1) |
| Mathematical Model | ALG-17: Garland–Heckbert: each vertex accumulates Q = Σ p pᵀ over incident face planes; edge collapse cost = v̄ᵀ(Q₁+Q₂)v̄ at the optimal or endpoint position; greedy by priority queue. Constraints: link condition (prevents non-manifold), boundary-edge lock (or … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-17)<br>ALG-56: Decimate (ALG-17) to a face budget for the client (TBD, NFR-02/03), quantise nothing (float32 positions in mm, F_anat), optional per-vertex scalar; flag display_only (INV-10). |
| Geometry Operations | ALG-17 Quadric error metric decimation with topology constraints [mesh decimation]; ALG-56 Display LOD payload (jude-mesh/1) [interactive display] |
| Output Data | display_lod artifact. |
| Output Data Structures | jude-mesh/1 binary · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-17: O(m log m); ALG-56: O(m log m) |
| Dependencies | Functions: FN-KOP-03 · Technical decisions: TD-11 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-FASTSIMP fast-simplification (MIT; CAND); LIB-MESHOPT meshoptimizer (MIT; CAND); module baseline |
| Alternative Implementations | ALG-17: Vertex clustering (fast, poor quality); edge-length based; remeshing (ALG-20).; ALG-56: glTF + Draco (metres/Y-up, extra conversion — rejected ADR-006). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-KOP-04 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Kernel input validator rejects display_only artifacts (INV-10 test).<br>ALG-17: Planar grid decimates to 2 triangles with zero error. Invariants: Output manifold if input manifold; Euler characteristic preserved (genus kept).<br>ALG-56: Pack/unpack round-trip. Invariants: LOD never accepted as kernel input. |
| Integration Test Requirements | Module baseline · catalogue cases: UT-FN-KOP-04 (proposed) |
| Open Technical Questions | TQ-07 |

#### FN-KOP-05 — Vertex normals

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-05 |
| Function Name | Vertex normals |
| Related Requirement IDs | FR-177; FR-050; SAF-10 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | One deterministic definition of vertex normals for offsets, zones and signs. Angle-weighted vertex normals (Thürmer–Wüthrich) computed in float64 in face order (proposal, OQ-FS-11). |
| Input Data | V, F · Preconditions: Consistently oriented mesh. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Face normals n_f = (b−a)×(c−a)/‖·‖ (degenerate faces contribute 0).<br>2. n_v = Σ_{f∋v} α_{f,v} n_f in face order; normalise.<br>3. Vertices with ‖n_v‖ < 1e-12 → NORMAL_UNDEFINED (op rejected).<br>Algorithms: ALG-14 Vertex normal estimation (angle-weighted) |
| Mathematical Model | n_v = normalize(Σ_f α_{f,v} n̂_f), α = interior angle at v.<br>ALG-14: n_v = normalise(Σ_f α_{f,v} n_f) with α the interior angle of face f at v (Thürmer–Wüthrich); face normal from winding. Summation in face order for determinism. Zero-length result (cancellation) → fallback to area-weighted, flagged. |
| Geometry Operations | ALG-14 Vertex normal estimation (angle-weighted) [normal estimation] |
| Output Data | Normals. |
| Output Data Structures | float64[N,3] · module baseline DS |
| Error Handling | NORMAL_UNDEFINED.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-14: O(m) |
| Dependencies | Functions: FN-KVL-04 · Technical decisions: TD-10 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-14: Area-weighted (default in many libraries); uniform; PCA normals for point clouds (Open3D) — not needed for meshes. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-050; TC-FR-177; TC-SAF-10; UT-FN-KOP-05 (proposed) · suites: VER-01, VER-08, VER-14 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-05 (proposed id)<br>Acceptance criteria as unit/component assertions: Icosphere: normals radial within 1e-6 rad; computation bit-identical across 100 runs.<br>ALG-14: Cube corner normal = (1,1,1)/√3; sphere vertex normal vs radial direction. Invariants: Normals flip when all faces flip.<br>One negative test per error code: NORMAL_UNDEFINED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-050; TC-FR-177; TC-SAF-10; UT-FN-KOP-05 (proposed) |
| Open Technical Questions | OQ-FS-11 |

#### FN-KOP-06 — Positive closure and base (positive.close_base)

*Kernel operation (pure function) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-06 |
| Function Name | Positive closure and base (positive.close_base) |
| Related Requirement IDs | FR-173; FR-080; VER-15; STK-04 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Turn the open head surface into a closed solid positive with a base (FR-173). Option A of 05 §3.4: cut at base plane, extrude contour by the extension distance along the base normal, cap with a planar triangulation. |
| Input Data | V, F, base plane Π (point + unit normal n̂ pointing away from the head), extension_mm e ≥ 0 · Preconditions: Surface in F_anat; positive_base configured (clinic value, DEC-029). |
| Input Data Structures | Arrays + params · module baseline DS |
| Processing Algorithm | 1. Cut with Π (FN-KMS-01 tie rule); discard the part on the +n̂ side; vertices with d < 0 are copied bitwise.<br>2. Collect boundary loops of the kept part: exactly one loop must lie on Π (cut contour C); any other boundary loop → OP_REJECTED_OPEN_BOUNDARY (list loops).<br>3. C must be a simple polygon in plane coordinates (segment-intersection sweep); else OP_REJECTED_NON_SIMPLE_CONTOUR; multiple contours on Π → OP_REJECTED_MULTIPLE_CONTOURS.<br>4. If e > 0: C' = C + e·n̂; side wall = quads (C_i, C_{i+1}, C'_{i+1}, C'_i) split into 2 triangles each.<br>5. Cap C' (or C if e = 0) by constrained ear clipping in plane coordinates without Steiner points (earcut-type), winding chosen so normals point along +n̂.<br>6. Make orientation consistent; signed volume must be > 0 (else flip all, recorded in report).<br>7. Validate with FN-KVL-07; failure → op rejected (SAF-09).<br>Algorithms: ALG-24 Positive closure: plane cut + prism wall + planar cap (option A); ALG-28 Mesh Boolean operations (union, difference, intersection); ALG-23 Plane section to contours with symbolic tie rule; ALG-25 Polygon simplicity test and ear-clipping triangulation; ALG-10 Orientation consistency, outward test and recorded re-orientation; ALG-13 Composite solid validity (validate.solid) |
| Mathematical Model | Plane cut as FN-KMS-01; base prism side faces; polygon triangulation with n−2 triangles for an n-gon.<br>ALG-24: Cut the open head surface with the configured base plane Π (ALG-23), keep the head side, require exactly one simple boundary contour C on Π and no other boundary, extrude C by e along the base normal n̂ (prism quads split into triangles), cap C' with a … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-24)<br>ALG-28: Manifold library: exact-topology Boolean on manifold triangle meshes with guaranteed manifold output (symbolic perturbation) [P G-SRC-11].<br>ALG-23: Signed distances d_i = n̂·(v_i − p). Symbolic perturbation: d = 0 is treated as positive, so no vertex lies on the plane and every crossed edge (sign change) yields exactly one point x = v_a + d_a/(d_a − d_b)(v_b − v_a). Each crossed face contributes one … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-23) |
| Geometry Operations | ALG-24 Positive closure: plane cut + prism wall + planar cap (option A) [open mesh to closed mesh conversion]; ALG-28 Mesh Boolean operations (union, difference, intersection) [Boolean union / difference / intersection]; ALG-23 Plane section to contours with symbolic tie rule [cranial measurements / closure]; ALG-25 Polygon simplicity test and ear-clipping triangulation [open mesh to closed mesh conversion]; ALG-10 Orientation consistency, outward test and recorded re-orientation [normal correction]; ALG-13 Composite solid validity (validate.solid) [watertightness / manifold validation / solid validity] |
| Output Data | Closed positive. |
| Output Data Structures | Arrays + face origin tags {scan, cut, wall, cap} · module baseline DS |
| Error Handling | OP_REJECTED_OPEN_BOUNDARY, OP_REJECTED_NON_SIMPLE_CONTOUR, OP_REJECTED_MULTIPLE_CONTOURS, VALIDITY_FAILED.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-24: O(m) cut + O(k²) cap for k contour vertices (ear clipping); ALG-28: Output-sensitive; parallel by default in C++ (must be pinned single-thread for determinism [H]); ALG-23: O(m); ALG-25: Simplicity O(k log k) (sweep) or O(k²); ear clipping O(k²) worst case; ALG-10: O(m); ALG-13: Dominated by ALG-11 |
| Dependencies | Functions: FN-KRP-04; FN-KMS-01; FN-KVL-07; FN-KVL-04 · Technical decisions: TD-07 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-MANIFOLD manifold3d (Manifold) (Apache-2.0; RESERVE); module baseline |
| Alternative Implementations | ALG-24: Boolean union with base block via manifold3d (Apache-2.0) — reserve for fixture blocks (OQ-G1); alpha wrap (rejected: moves surface); hole filling of the opening (rejected: no flat base).; ALG-28: OCCT B-Rep Booleans (LGPL+exception; mesh→B-Rep conversion heavy); MeshLib (commercial).; ALG-23: trimesh section (tie handling and order not specified for our contract [N]); VTK vtkCutter (BSD). |
| Security Considerations | Module baseline · Constraint: Requires the scan to have no holes above the base plane; position in the op sequence is undecided (OQ-FS-01). |
| Verification Strategy | Method T · test cases: TC-FR-080; TC-FR-173; UT-FN-KOP-06 (proposed) · suites: VER-01, VER-08, VER-15 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-06 (proposed id)<br>Acceptance criteria as unit/component assertions: Open phantoms with varied boundaries yield valid closed solids; base plane within e = 0.011 mm of configured position; vertices on the head side bit-identical to input.<br>ALG-24: Hemisphere + plane → closed solid with analytic volume. Invariants: Head-side vertices bit-identical; watertight; volume > 0; 1 component.<br>ALG-28: Cube ∪ cube analytic volume. Invariants: Output manifold.<br>ALG-23: Cube cut through vertices; tetrahedron cut through edge. Invariants: Each crossed edge produces exactly one point; closed contours on closed meshes.<br>One negative test per error code: OP_REJECTED_MULTIPLE_CONTOURS, OP_REJECTED_NON_SIMPLE_CONTOUR, OP_REJECTED_OPEN_BOUNDARY, VALIDITY_FAILED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-080; TC-FR-173; UT-FN-KOP-06 (proposed) |
| Open Technical Questions | OQ-FS-01; OQ-FS-37 |

##### FN-KOP-06.1 — Base-plane cut

*Kernel operation (pure function) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-06.1 |
| Function Name | Base-plane cut  (subfunction of FN-KOP-06 Positive closure and base (positive.close_base)) |
| Related Requirement IDs | Inherited from parent FN-KOP-06: FR-173; FR-080; VER-15; STK-04 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Cut and discard the base side. |
| Input Data | Inherited from FN-KOP-06 |
| Input Data Structures | Inherited from FN-KOP-06 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Cut and discard the base side. — implemented by ALG-23, ALG-24 |
| Mathematical Model | ALG-23: Signed distances d_i = n̂·(v_i − p). Symbolic perturbation: d = 0 is treated as positive, so no vertex lies on the plane and every crossed edge (sign change) yields exactly one point x = v_a + d_a/(d_a − d_b)(v_b − v_a). Each crossed face contributes one … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-23)<br>ALG-24: Cut the open head surface with the configured base plane Π (ALG-23), keep the head side, require exactly one simple boundary contour C on Π and no other boundary, extrude C by e along the base normal n̂ (prism quads split into triangles), cap C' with a … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-24) |
| Geometry Operations | ALG-23 Plane section to contours with symbolic tie rule [cranial measurements / closure]; ALG-24 Positive closure: plane cut + prism wall + planar cap (option A) [open mesh to closed mesh conversion] |
| Output Data | Inherited from FN-KOP-06 |
| Output Data Structures | Inherited from FN-KOP-06 |
| Error Handling | Inherited from FN-KOP-06 |
| Performance Requirements | Inherited from FN-KOP-06 — complexity: ALG-23: O(m); ALG-24: O(m) cut + O(k²) cap for k contour vertices (ear clipping) |
| Dependencies | Inherited from FN-KOP-06 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-MANIFOLD manifold3d (Manifold) (Apache-2.0; RESERVE); module baseline |
| Alternative Implementations | ALG-23: trimesh section (tie handling and order not specified for our contract [N]); VTK vtkCutter (BSD).; ALG-24: Boolean union with base block via manifold3d (Apache-2.0) — reserve for fixture blocks (OQ-G1); alpha wrap (rejected: moves surface); hole filling of the opening (rejected: no flat base). |
| Security Considerations | Inherited from FN-KOP-06 |
| Verification Strategy | T — verified within FN-KOP-06 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KOP-06.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Cut and discard the base side.<br>ALG-23: Cube cut through vertices; tetrahedron cut through edge. Invariants: Each crossed edge produces exactly one point; closed contours on closed meshes.<br>ALG-24: Hemisphere + plane → closed solid with analytic volume. Invariants: Head-side vertices bit-identical; watertight; volume > 0; 1 component. |
| Integration Test Requirements | Inherited from FN-KOP-06 |
| Open Technical Questions | Inherited from FN-KOP-06 |

##### FN-KOP-06.2 — Contour checks

*Kernel operation (pure function) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-06.2 |
| Function Name | Contour checks  (subfunction of FN-KOP-06 Positive closure and base (positive.close_base)) |
| Related Requirement IDs | Inherited from parent FN-KOP-06: FR-173; FR-080; VER-15; STK-04 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Single, simple contour on the plane; no other open boundary. |
| Input Data | Inherited from FN-KOP-06 |
| Input Data Structures | Inherited from FN-KOP-06 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Single, simple contour on the plane; no other open boundary. — implemented by ALG-24, ALG-25 |
| Mathematical Model | ALG-24: Cut the open head surface with the configured base plane Π (ALG-23), keep the head side, require exactly one simple boundary contour C on Π and no other boundary, extrude C by e along the base normal n̂ (prism quads split into triangles), cap C' with a … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-24)<br>ALG-25: Project contour to plane coordinates (orthonormal basis of Π). Simplicity: no two non-adjacent segments intersect (exact orient2d; O(k log k) Shamos–Hoey sweep or O(k²) brute force for k ≤ k_max). Ear clipping: repeatedly cut a convex vertex whose triangle … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-25) |
| Geometry Operations | ALG-24 Positive closure: plane cut + prism wall + planar cap (option A) [open mesh to closed mesh conversion]; ALG-25 Polygon simplicity test and ear-clipping triangulation [open mesh to closed mesh conversion] |
| Output Data | Inherited from FN-KOP-06 |
| Output Data Structures | Inherited from FN-KOP-06 |
| Error Handling | Inherited from FN-KOP-06 |
| Performance Requirements | Inherited from FN-KOP-06 — complexity: ALG-24: O(m) cut + O(k²) cap for k contour vertices (ear clipping); ALG-25: Simplicity O(k log k) (sweep) or O(k²); ear clipping O(k²) worst case |
| Dependencies | Inherited from FN-KOP-06 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-PREDICATES Shewchuk robust predicates (own port) (Public domain (original); JS port robust-predicates under Unlicense; R-MVP); LIB-MANIFOLD manifold3d (Manifold) (Apache-2.0; RESERVE); module baseline |
| Alternative Implementations | ALG-24: Boolean union with base block via manifold3d (Apache-2.0) — reserve for fixture blocks (OQ-G1); alpha wrap (rejected: moves surface); hole filling of the opening (rejected: no flat base).; ALG-25: Constrained Delaunay (Shewchuk Triangle — non-free commercial use, rejected); CDT in CGAL (GPL). |
| Security Considerations | Inherited from FN-KOP-06 |
| Verification Strategy | T — verified within FN-KOP-06 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KOP-06.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Single, simple contour on the plane; no other open boundary.<br>ALG-24: Hemisphere + plane → closed solid with analytic volume. Invariants: Head-side vertices bit-identical; watertight; volume > 0; 1 component.<br>ALG-25: Convex, concave, comb, spiral polygons. Invariants: k − 2 triangles; all CCW; union = polygon. |
| Integration Test Requirements | Inherited from FN-KOP-06 |
| Open Technical Questions | Inherited from FN-KOP-06 |

##### FN-KOP-06.3 — Prism wall

*Kernel operation (pure function) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-06.3 |
| Function Name | Prism wall  (subfunction of FN-KOP-06 Positive closure and base (positive.close_base)) |
| Related Requirement IDs | Inherited from parent FN-KOP-06: FR-173; FR-080; VER-15; STK-04 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Extrusion by extension_mm along the base normal. |
| Input Data | Inherited from FN-KOP-06 |
| Input Data Structures | Inherited from FN-KOP-06 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Extrusion by extension_mm along the base normal. — implemented by ALG-24 |
| Mathematical Model | ALG-24: Cut the open head surface with the configured base plane Π (ALG-23), keep the head side, require exactly one simple boundary contour C on Π and no other boundary, extrude C by e along the base normal n̂ (prism quads split into triangles), cap C' with a … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-24) |
| Geometry Operations | ALG-24 Positive closure: plane cut + prism wall + planar cap (option A) [open mesh to closed mesh conversion] |
| Output Data | Inherited from FN-KOP-06 |
| Output Data Structures | Inherited from FN-KOP-06 |
| Error Handling | Inherited from FN-KOP-06 |
| Performance Requirements | Inherited from FN-KOP-06 — complexity: ALG-24: O(m) cut + O(k²) cap for k contour vertices (ear clipping) |
| Dependencies | Inherited from FN-KOP-06 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-MANIFOLD manifold3d (Manifold) (Apache-2.0; RESERVE); module baseline |
| Alternative Implementations | ALG-24: Boolean union with base block via manifold3d (Apache-2.0) — reserve for fixture blocks (OQ-G1); alpha wrap (rejected: moves surface); hole filling of the opening (rejected: no flat base). |
| Security Considerations | Inherited from FN-KOP-06 |
| Verification Strategy | T — verified within FN-KOP-06 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KOP-06.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Extrusion by extension_mm along the base normal.<br>ALG-24: Hemisphere + plane → closed solid with analytic volume. Invariants: Head-side vertices bit-identical; watertight; volume > 0; 1 component. |
| Integration Test Requirements | Inherited from FN-KOP-06 |
| Open Technical Questions | Inherited from FN-KOP-06 |

##### FN-KOP-06.4 — Planar cap

*Kernel operation (pure function) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-06.4 |
| Function Name | Planar cap  (subfunction of FN-KOP-06 Positive closure and base (positive.close_base)) |
| Related Requirement IDs | Inherited from parent FN-KOP-06: FR-173; FR-080; VER-15; STK-04 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Ear-clipping triangulation without Steiner points. |
| Input Data | Inherited from FN-KOP-06 |
| Input Data Structures | Inherited from FN-KOP-06 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Ear-clipping triangulation without Steiner points. — implemented by ALG-24, ALG-25 |
| Mathematical Model | ALG-24: Cut the open head surface with the configured base plane Π (ALG-23), keep the head side, require exactly one simple boundary contour C on Π and no other boundary, extrude C by e along the base normal n̂ (prism quads split into triangles), cap C' with a … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-24)<br>ALG-25: Project contour to plane coordinates (orthonormal basis of Π). Simplicity: no two non-adjacent segments intersect (exact orient2d; O(k log k) Shamos–Hoey sweep or O(k²) brute force for k ≤ k_max). Ear clipping: repeatedly cut a convex vertex whose triangle … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-25) |
| Geometry Operations | ALG-24 Positive closure: plane cut + prism wall + planar cap (option A) [open mesh to closed mesh conversion]; ALG-25 Polygon simplicity test and ear-clipping triangulation [open mesh to closed mesh conversion] |
| Output Data | Inherited from FN-KOP-06 |
| Output Data Structures | Inherited from FN-KOP-06 |
| Error Handling | Inherited from FN-KOP-06 |
| Performance Requirements | Inherited from FN-KOP-06 — complexity: ALG-24: O(m) cut + O(k²) cap for k contour vertices (ear clipping); ALG-25: Simplicity O(k log k) (sweep) or O(k²); ear clipping O(k²) worst case |
| Dependencies | Inherited from FN-KOP-06 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-EARCUT mapbox-earcut (Python) / earcut (JS) (ISC; CAND); LIB-MANIFOLD manifold3d (Manifold) (Apache-2.0; RESERVE); module baseline |
| Alternative Implementations | ALG-24: Boolean union with base block via manifold3d (Apache-2.0) — reserve for fixture blocks (OQ-G1); alpha wrap (rejected: moves surface); hole filling of the opening (rejected: no flat base).; ALG-25: Constrained Delaunay (Shewchuk Triangle — non-free commercial use, rejected); CDT in CGAL (GPL). |
| Security Considerations | Inherited from FN-KOP-06 |
| Verification Strategy | T — verified within FN-KOP-06 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KOP-06.4 (proposed id)<br>Isolated test of this step with positive and negative cases: Ear-clipping triangulation without Steiner points.<br>ALG-24: Hemisphere + plane → closed solid with analytic volume. Invariants: Head-side vertices bit-identical; watertight; volume > 0; 1 component.<br>ALG-25: Convex, concave, comb, spiral polygons. Invariants: k − 2 triangles; all CCW; union = polygon. |
| Integration Test Requirements | Inherited from FN-KOP-06 |
| Open Technical Questions | TQ-08 |

##### FN-KOP-06.5 — Orientation and validation

*Kernel operation (pure function) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-06.5 |
| Function Name | Orientation and validation  (subfunction of FN-KOP-06 Positive closure and base (positive.close_base)) |
| Related Requirement IDs | Inherited from parent FN-KOP-06: FR-173; FR-080; VER-15; STK-04 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Consistent outward winding; FN-KVL-07. |
| Input Data | Inherited from FN-KOP-06 |
| Input Data Structures | Inherited from FN-KOP-06 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Consistent outward winding; FN-KVL-07. — implemented by ALG-10, ALG-13, ALG-24 |
| Mathematical Model | ALG-10: Consistency: for every manifold interior edge the two incident faces must traverse it in opposite directions (directed half-edge appears once in each direction). Outward test: closed component → signed volume V = (1/6) Σ a·(b×c) > 0; open scan → hint only: … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-10)<br>ALG-13: Conjunction of geometric checks: boundary edges = 0; non-manifold edges = 0; non-manifold vertices = 0; self-intersections = 0 (ALG-11); components = 1; inconsistent edges = 0; signed volume > 0 (outward); degenerate faces = 0. Each check reported … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-13)<br>ALG-24: Cut the open head surface with the configured base plane Π (ALG-23), keep the head side, require exactly one simple boundary contour C on Π and no other boundary, extrude C by e along the base normal n̂ (prism quads split into triangles), cap C' with a … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-24) |
| Geometry Operations | ALG-10 Orientation consistency, outward test and recorded re-orientation [normal correction]; ALG-13 Composite solid validity (validate.solid) [watertightness / manifold validation / solid validity]; ALG-24 Positive closure: plane cut + prism wall + planar cap (option A) [open mesh to closed mesh conversion] |
| Output Data | Inherited from FN-KOP-06 |
| Output Data Structures | Inherited from FN-KOP-06 |
| Error Handling | Inherited from FN-KOP-06 |
| Performance Requirements | Inherited from FN-KOP-06 — complexity: ALG-10: O(m); ALG-13: Dominated by ALG-11; ALG-24: O(m) cut + O(k²) cap for k contour vertices (ear clipping) |
| Dependencies | Inherited from FN-KOP-06 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-MANIFOLD manifold3d (Manifold) (Apache-2.0; RESERVE); module baseline |
| Alternative Implementations | ALG-10: trimesh fix_normals (applies changes; not allowed silently); ray-parity outward test (fails on open meshes).; ALG-13: manifold3d constructor as validity oracle (reports error status for non-manifold input [N]).; ALG-24: Boolean union with base block via manifold3d (Apache-2.0) — reserve for fixture blocks (OQ-G1); alpha wrap (rejected: moves surface); hole filling of the opening (rejected: no flat base). |
| Security Considerations | Inherited from FN-KOP-06 |
| Verification Strategy | T — verified within FN-KOP-06 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KOP-06.5 (proposed id)<br>Isolated test of this step with positive and negative cases: Consistent outward winding; FN-KVL-07.<br>ALG-10: Sphere with one flipped face → 3 inconsistent edges; inverted sphere → negative volume. Invariants: Flipping all faces negates volume; translation leaves volume unchanged.<br>ALG-13: Each defect type fails exactly its check. Invariants: All checks pass on analytic closed phantoms.<br>ALG-24: Hemisphere + plane → closed solid with analytic volume. Invariants: Head-side vertices bit-identical; watertight; volume > 0; 1 component. |
| Integration Test Requirements | Inherited from FN-KOP-06 |
| Open Technical Questions | Inherited from FN-KOP-06 |

#### FN-KOP-07 — Uniform normal offset (offset.uniform_normal)

*Kernel operation (pure function) · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-07 |
| Function Name | Uniform normal offset (offset.uniform_normal) |
| Related Requirement IDs | FR-177; SAF-10 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Apply a uniform allowance (cap compensation, liner, other) as a recorded op (FR-177). Vertex displacement along FN-KOP-05 normals. |
| Input Data | V, F, offset_mm d (signed), purpose ∈ {cap_compensation, liner_allowance, other} · Preconditions: Topology of scan_prepared; purpose label given; offset entered by technician (no default). |
| Input Data Structures | Arrays + params · module baseline DS |
| Processing Algorithm | 1. v' = v + d·n̂_v for all vertices of the scan-origin surface (faces tagged scan).<br>2. Run FN-KOP-13: new self-intersections → op rejected.<br>3. Report achieved distance statistics from FN-KCP-04 (min/max/mean of distance to the input surface).<br>Algorithms: ALG-26 Uniform vertex-normal offset with fold check; ALG-41 Deviation statistics and one-sided vertex-to-surface Hausdorff; ALG-45 Discrete curvature estimation; ALG-50 Post-operation geometric guard |
| Mathematical Model | v' = v + d n̂_v; fold risk where \|d\|·κ_max ≥ 1 on the side towards the curvature centre.<br>ALG-26: v' = v + d·n̂_v on scan-origin vertices (ALG-14 normals). Exact on spheres (r → r + d). Folds occur where \|d\|·κ_max ≥ 1 on the concave side; detected by post-op guard (self-intersection, inverted faces). Achieved distance to input surface reported … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-26)<br>ALG-41: Per region (zone id from op parameters, or whole mesh): min, max, mean, RMS of a per-vertex distance field; one-sided Hausdorff h(A→B) = max_{a∈V_A} d(a, B) using vertex samples (documented as vertex-sampled, a lower bound of the continuous Hausdorff).<br>ALG-45: Mean curvature from cotangent Laplacian; Gaussian curvature from angle defect (Meyer et al.). |
| Geometry Operations | ALG-26 Uniform vertex-normal offset with fold check [surface offset]; ALG-41 Deviation statistics and one-sided vertex-to-surface Hausdorff [geometric comparison]; ALG-45 Discrete curvature estimation [cranial surface analysis]; ALG-50 Post-operation geometric guard [geometric constraints] |
| Output Data | Offset surface + report. |
| Output Data Structures | Arrays + JSON {min, max, mean distance} · module baseline DS |
| Error Handling | SELF_INTERSECTION_CREATED → rejected; last valid geometry kept.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-26: O(n) + guard; ALG-41: O(n); ALG-45: O(m); ALG-50: Incremental: O(k log m) for k affected faces [H] |
| Dependencies | Functions: FN-KRP-04; FN-KOP-05; FN-KOP-13; FN-KCP-04 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-26: SDF offset (ALG-27) — exact distance, new topology (post-MVP shell).; ALG-41: Face-sampled Hausdorff (Metro-style) — post-MVP.; ALG-45: Quadric fitting. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-177; TC-SAF-10; UT-FN-KOP-07 (proposed) · suites: VER-01, VER-14 · evidence level L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-07 (proposed id)<br>Acceptance criteria as unit/component assertions: Sphere radius r offset by +d gives radius r+d within 0.011 mm; new design contains no offset op.<br>ALG-26: Sphere r → r + d within e = 0.011 mm. Invariants: Topology unchanged; anchors remain valid.<br>ALG-41: Hand fields. Invariants: Stats of field + c shift by c.<br>ALG-45: Outline — to be designed when the topic enters scope Invariants: Outline — to be designed when the topic enters scope<br>One negative test per error code: SELF_INTERSECTION_CREATED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-177; TC-SAF-10; UT-FN-KOP-07 (proposed) |
| Open Technical Questions | None registered |

#### FN-KOP-08 — Global axis length adjustment (adjust.global_axis, length)

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-08 |
| Function Name | Global axis length adjustment (adjust.global_axis, length) |
| Related Requirement IDs | FR-051 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Change length along one anatomical axis by Δ mm (FR-051a, A-22). Uniform scaling along the axis about the frame origin. |
| Input Data | V, axis â ∈ {AP, ML, V}, delta_mm Δ, origin o · Preconditions: Frame confirmed. |
| Input Data Structures | Arrays + params · module baseline DS |
| Processing Algorithm | 1. L = max_i â·(v_i − o) − min_i â·(v_i − o) over scan-origin vertices (reference length, OQ-FS-19).<br>2. k = (L + Δ)/L; require k > 0.<br>3. v' = o + (I + (k − 1) â âᵀ)(v − o).<br>Algorithms: ALG-48 Global axis length adjustment (anisotropic scaling about the frame origin) |
| Mathematical Model | Extent along â scales by k ⇒ new extent = L + Δ exactly; orthogonal coordinates unchanged.<br>ALG-48: Extent L along axis â over scan-origin vertices; k = (L + Δ)/L > 0; v' = o + (I + (k − 1)ââᵀ)(v − o). Extent changes by exactly Δ; orthogonal coordinates unchanged. |
| Geometry Operations | ALG-48 Global axis length adjustment (anisotropic scaling about the frame origin) [geometric constraints / correction] |
| Output Data | Adjusted surface. |
| Output Data Structures | Arrays · module baseline DS |
| Error Handling | k ≤ 0 → PARAM_INVALID.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-48: O(n) |
| Dependencies | Functions: FN-KRP-04; FN-KFR-02; FN-KOP-13 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-48: Tapered/banded scaling (as ALG-49). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-051; UT-FN-KOP-08 (proposed) · suites: VER-01 · evidence level L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-08 (proposed id)<br>Acceptance criteria as unit/component assertions: On VER-01 phantom +x mm A-P adjustment changes A-P extent by x within 2e.<br>ALG-48: Box extent change. Invariants: Orthogonal extents unchanged.<br>One negative test per error code: PARAM_INVALID |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-051; UT-FN-KOP-08 (proposed) |
| Open Technical Questions | OQ-FS-19 |

#### FN-KOP-09 — Circumference adjustment at level (adjust.global_axis, circumference)

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-09 |
| Function Name | Circumference adjustment at level (adjust.global_axis, circumference) |
| Related Requirement IDs | FR-051 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Change the circumference at a chosen level by Δ mm with a tapered band (FR-051b, A-22). Radial scaling about the vertical axis. |
| Input Data | V, level ℓ (mm along vertical axis), band_mm b, transition_mm t, circumference_delta_mm Δ · Preconditions: Frame confirmed. |
| Input Data Structures | Arrays + params · module baseline DS |
| Processing Algorithm | 1. C = perimeter of the contour at z = ℓ (FN-KMS-01 + FN-KMS-02 rule).<br>2. k = (C + Δ)/C.<br>3. For each vertex with height z and radial vector r (component ⟂ vertical axis through o): w = 1 if \|z − ℓ\| ≤ b; w = 1 − (\|z − ℓ\| − b)/t if b < \|z − ℓ\| < b + t; else 0.<br>4. r' = r·(1 + (k − 1)·w); vertices with w = 0 untouched (bitwise).<br>Algorithms: ALG-23 Plane section to contours with symbolic tie rule; ALG-49 Circumference adjustment at a level with tapered band |
| Mathematical Model | In the plane z = ℓ the map is a uniform 2D scaling by k about the axis ⇒ new perimeter = kC = C + Δ exactly.<br>ALG-23: Signed distances d_i = n̂·(v_i − p). Symbolic perturbation: d = 0 is treated as positive, so no vertex lies on the plane and every crossed edge (sign change) yields exactly one point x = v_a + d_a/(d_a − d_b)(v_b − v_a). Each crossed face contributes one … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-23)<br>ALG-49: Section at level h (ALG-23) gives perimeter C; radial scaling about the level axis by k = (C + Δ)/C applied with weight w(\|z − h\|) (plateau band + smoothstep transition); perimeter at h changes by Δ exactly for a star-shaped contour (radial scaling of a … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-49) |
| Geometry Operations | ALG-23 Plane section to contours with symbolic tie rule [cranial measurements / closure]; ALG-49 Circumference adjustment at a level with tapered band [geometric constraints / correction] |
| Output Data | Adjusted surface. |
| Output Data Structures | Arrays · module baseline DS |
| Error Handling | Contour at ℓ not selectable → OP_REJECTED_NO_CONTOUR.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-23: O(m); ALG-49: O(n) |
| Dependencies | Functions: FN-KRP-04; FN-KMS-01; FN-KMS-02; FN-KOP-13 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-23: trimesh section (tie handling and order not specified for our contract [N]); VTK vtkCutter (BSD).; ALG-49: Normal offset in band (changes perimeter by 2πd only for circles). |
| Security Considerations | Module baseline · Constraint: Linear taper is C⁰ at band edges (A-22 as written); smoother taper would need a requirement change. |
| Verification Strategy | Method T · test cases: TC-FR-051; UT-FN-KOP-09 (proposed) · suites: VER-01 · evidence level L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-09 (proposed id)<br>Acceptance criteria as unit/component assertions: Phantom: perimeter at ℓ changes by Δ within 0.032 mm; vertices beyond b + t bit-identical.<br>ALG-23: Cube cut through vertices; tetrahedron cut through edge. Invariants: Each crossed edge produces exactly one point; closed contours on closed meshes.<br>ALG-49: Cylinder band perimeter change. Invariants: Vertices outside band+transition unchanged.<br>One negative test per error code: OP_REJECTED_NO_CONTOUR |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-051; UT-FN-KOP-09 (proposed) |
| Open Technical Questions | OQ-FS-19 |

#### FN-KOP-10 — Correction zone displacement (zone.normal_falloff)

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-10 |
| Function Name | Correction zone displacement (zone.normal_falloff) |
| Related Requirement IDs | FR-050; FR-054; SAF-10; DATA-08 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Apply a technician-defined local displacement (contact, growth void, relief, build-up) on the positive (FR-050). Plateau of full magnitude within the extent, smoothstep fall-off across the transition width, displacement along vertex normals (05 §3.6, 07 §6.3; A-15). |
| Input Data | V, F, centre anchor, shape ∈ {circle(r), ellipse(r₁, r₂, α)}, magnitude_mm m (signed, + = outward on positive), transition_mm t ≥ 0 · Preconditions: Anchor centre valid (FN-KAN-02); category set; magnitude entered by technician. |
| Input Data Structures | Arrays + params · module baseline DS |
| Processing Algorithm | 1. c = anchor position on op input; n̂_c = vertex-normal interpolation at c.<br>2. Circle: ρ = ‖v − c‖/r. Ellipse: tangent basis t̂₁ = normalize(a − (a·n̂_c)n̂_c) with reference axis a (OQ-FS-10), rotated by α about n̂_c; t̂₂ = n̂_c × t̂₁; p = v − c; ρ = √((p·t̂₁/r₁)² + (p·t̂₂/r₂)² + (p·n̂_c/min(r₁,r₂))²).<br>3. Distance beyond extent along the ray from c: u = ‖p‖·(1 − 1/ρ) for ρ > 1.<br>4. Weight w = 1 if ρ ≤ 1; w = S(1 − u/t) with S(x) = 3x² − 2x³ if 0 < u < t; w = 0 otherwise.<br>5. v' = v + m·w·n̂_v for w > 0; vertices with w = 0 are not touched.<br>6. Run FN-KOP-13 (self-intersection, sign check).<br>Algorithms: ALG-46 Correction / relief zone displacement (plateau + smoothstep); ALG-43 Region segmentation (MVP: technician-defined regions); ALG-50 Post-operation geometric guard |
| Mathematical Model | w ∈ [0,1], C¹ at both ends of the transition; max displacement = \|m\| on the plateau.<br>ALG-46: Centre c from anchor (face_id, bary) evaluated on the current positive; tangent basis (t₁, t₂) from the projected reference direction (OQ-FS-10); p = v − c; normalised radius ρ = ‖p‖/r (circle) or ρ = √((p·t̂₁/r₁)² + (p·t̂₂/r₂)² + (p·n̂_c/min(r₁,r₂))²) … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-46)<br>ALG-43: MVP regions are explicit: (a) face sets from UI brush/lasso selection resolved on the server against full-resolution face ids; (b) disc/ellipse regions defined by an anchored centre and Euclidean radius (A-15); (c) angular sectors in F_anat (ALG-34). No … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-43)<br>ALG-50: After every design op: (1) incremental self-intersection test on faces touching moved vertices (ALG-11 incremental); (2) face normal flip test: n_f'·n_f ≤ 0 for any face → reject; (3) sign check: for ops with signed magnitude, sign of displacement along n̂ … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-50) |
| Geometry Operations | ALG-46 Correction / relief zone displacement (plateau + smoothstep) [correction zones / relief zones]; ALG-43 Region segmentation (MVP: technician-defined regions) [region segmentation]; ALG-50 Post-operation geometric guard [geometric constraints] |
| Output Data | Displaced surface + report. |
| Output Data Structures | Arrays + JSON {vertices_moved, max_displacement_mm, plateau_vertices} · module baseline DS |
| Error Handling | SELF_INTERSECTION_CREATED → rejected; SIGN_CHECK_FAILED → rejected (RG-03).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-46: O(n) (or O(n_affected) with BVH range query); ALG-43: O(selection · log m); ALG-50: Incremental: O(k log m) for k affected faces [H] |
| Dependencies | Functions: FN-KRP-04; FN-KAN-02; FN-KOP-05; FN-KOP-13 · Technical decisions: TD-08 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-46: Laplacian surface editing (F-SRC-19), ARAP (F-SRC-18), RBF fields — post-MVP/research.; ALG-43: Geodesic distance regions (potpourri3d MIT heat method, libigl exact geodesics MPL-2.0) — post-MVP.; ALG-50: Full validation after every op (slower). |
| Security Considerations | Module baseline · Constraint: Euclidean (not geodesic) distance can reach across thin regions (A-15); the plateau interpretation of 'extent' must be confirmed (OQ-FS-09). |
| Verification Strategy | Method T · test cases: TC-DATA-08; TC-FR-050; TC-FR-054; TC-SAF-10; UT-FN-KOP-10 (proposed) · suites: VER-01, VER-08, VER-14, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-10 (proposed id)<br>Acceptance criteria as unit/component assertions: Sphere phantom: max signed displacement = m ± 0.011 mm at centre; vertices outside extent + transition bit-identical; outward zone gives positive deviation (VER-14).<br>ALG-46: Plane with zone: displacement profile matches w analytically. Invariants: Vertices outside extent+T bit-identical; sign of m equals sign of deviation.<br>ALG-43: Disc membership on plane. Invariants: Selection resolved on full mesh is the stored truth.<br>ALG-50: Fold-inducing zone → rejected; benign zone → accepted. Invariants: Rejected op leaves geometry hash unchanged (TC-SAF-09).<br>One negative test per error code: SELF_INTERSECTION_CREATED, SIGN_CHECK_FAILED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-08; TC-FR-050; TC-FR-054; TC-SAF-10; UT-FN-KOP-10 (proposed) |
| Open Technical Questions | OQ-FS-09; OQ-FS-10; TQ-19 |

##### FN-KOP-10.1 — Centre and frame

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-10.1 |
| Function Name | Centre and frame  (subfunction of FN-KOP-10 Correction zone displacement (zone.normal_falloff)) |
| Related Requirement IDs | Inherited from parent FN-KOP-10: FR-050; FR-054; SAF-10; DATA-08 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Anchor evaluation and tangent basis. |
| Input Data | Inherited from FN-KOP-10 |
| Input Data Structures | Inherited from FN-KOP-10 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Anchor evaluation and tangent basis. — implemented by ALG-46 |
| Mathematical Model | ALG-46: Centre c from anchor (face_id, bary) evaluated on the current positive; tangent basis (t₁, t₂) from the projected reference direction (OQ-FS-10); p = v − c; normalised radius ρ = ‖p‖/r (circle) or ρ = √((p·t̂₁/r₁)² + (p·t̂₂/r₂)² + (p·n̂_c/min(r₁,r₂))²) … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-46) |
| Geometry Operations | ALG-46 Correction / relief zone displacement (plateau + smoothstep) [correction zones / relief zones] |
| Output Data | Inherited from FN-KOP-10 |
| Output Data Structures | Inherited from FN-KOP-10 |
| Error Handling | Inherited from FN-KOP-10 |
| Performance Requirements | Inherited from FN-KOP-10 — complexity: ALG-46: O(n) (or O(n_affected) with BVH range query) |
| Dependencies | Inherited from FN-KOP-10 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-46: Laplacian surface editing (F-SRC-19), ARAP (F-SRC-18), RBF fields — post-MVP/research. |
| Security Considerations | Inherited from FN-KOP-10 |
| Verification Strategy | T — verified within FN-KOP-10 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KOP-10.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Anchor evaluation and tangent basis.<br>ALG-46: Plane with zone: displacement profile matches w analytically. Invariants: Vertices outside extent+T bit-identical; sign of m equals sign of deviation. |
| Integration Test Requirements | Inherited from FN-KOP-10 |
| Open Technical Questions | TQ-19 |

##### FN-KOP-10.2 — Normalised radius

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-10.2 |
| Function Name | Normalised radius  (subfunction of FN-KOP-10 Correction zone displacement (zone.normal_falloff)) |
| Related Requirement IDs | Inherited from parent FN-KOP-10: FR-050; FR-054; SAF-10; DATA-08 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Circle or ellipse ρ and distance beyond extent u. |
| Input Data | Inherited from FN-KOP-10 |
| Input Data Structures | Inherited from FN-KOP-10 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Circle or ellipse ρ and distance beyond extent u. — implemented by ALG-43, ALG-46 |
| Mathematical Model | ALG-43: MVP regions are explicit: (a) face sets from UI brush/lasso selection resolved on the server against full-resolution face ids; (b) disc/ellipse regions defined by an anchored centre and Euclidean radius (A-15); (c) angular sectors in F_anat (ALG-34). No … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-43)<br>ALG-46: Centre c from anchor (face_id, bary) evaluated on the current positive; tangent basis (t₁, t₂) from the projected reference direction (OQ-FS-10); p = v − c; normalised radius ρ = ‖p‖/r (circle) or ρ = √((p·t̂₁/r₁)² + (p·t̂₂/r₂)² + (p·n̂_c/min(r₁,r₂))²) … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-46) |
| Geometry Operations | ALG-43 Region segmentation (MVP: technician-defined regions) [region segmentation]; ALG-46 Correction / relief zone displacement (plateau + smoothstep) [correction zones / relief zones] |
| Output Data | Inherited from FN-KOP-10 |
| Output Data Structures | Inherited from FN-KOP-10 |
| Error Handling | Inherited from FN-KOP-10 |
| Performance Requirements | Inherited from FN-KOP-10 — complexity: ALG-43: O(selection · log m); ALG-46: O(n) (or O(n_affected) with BVH range query) |
| Dependencies | Inherited from FN-KOP-10 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-43: Geodesic distance regions (potpourri3d MIT heat method, libigl exact geodesics MPL-2.0) — post-MVP.; ALG-46: Laplacian surface editing (F-SRC-19), ARAP (F-SRC-18), RBF fields — post-MVP/research. |
| Security Considerations | Inherited from FN-KOP-10 |
| Verification Strategy | T — verified within FN-KOP-10 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KOP-10.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Circle or ellipse ρ and distance beyond extent u.<br>ALG-43: Disc membership on plane. Invariants: Selection resolved on full mesh is the stored truth.<br>ALG-46: Plane with zone: displacement profile matches w analytically. Invariants: Vertices outside extent+T bit-identical; sign of m equals sign of deviation. |
| Integration Test Requirements | Inherited from FN-KOP-10 |
| Open Technical Questions | TQ-19 |

##### FN-KOP-10.3 — Weight profile

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-10.3 |
| Function Name | Weight profile  (subfunction of FN-KOP-10 Correction zone displacement (zone.normal_falloff)) |
| Related Requirement IDs | Inherited from parent FN-KOP-10: FR-050; FR-054; SAF-10; DATA-08 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Plateau + smoothstep transition. |
| Input Data | Inherited from FN-KOP-10 |
| Input Data Structures | Inherited from FN-KOP-10 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Plateau + smoothstep transition. — implemented by ALG-46 |
| Mathematical Model | ALG-46: Centre c from anchor (face_id, bary) evaluated on the current positive; tangent basis (t₁, t₂) from the projected reference direction (OQ-FS-10); p = v − c; normalised radius ρ = ‖p‖/r (circle) or ρ = √((p·t̂₁/r₁)² + (p·t̂₂/r₂)² + (p·n̂_c/min(r₁,r₂))²) … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-46) |
| Geometry Operations | ALG-46 Correction / relief zone displacement (plateau + smoothstep) [correction zones / relief zones] |
| Output Data | Inherited from FN-KOP-10 |
| Output Data Structures | Inherited from FN-KOP-10 |
| Error Handling | Inherited from FN-KOP-10 |
| Performance Requirements | Inherited from FN-KOP-10 — complexity: ALG-46: O(n) (or O(n_affected) with BVH range query) |
| Dependencies | Inherited from FN-KOP-10 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-46: Laplacian surface editing (F-SRC-19), ARAP (F-SRC-18), RBF fields — post-MVP/research. |
| Security Considerations | Inherited from FN-KOP-10 |
| Verification Strategy | T — verified within FN-KOP-10 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KOP-10.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Plateau + smoothstep transition.<br>ALG-46: Plane with zone: displacement profile matches w analytically. Invariants: Vertices outside extent+T bit-identical; sign of m equals sign of deviation. |
| Integration Test Requirements | Inherited from FN-KOP-10 |
| Open Technical Questions | TQ-19 |

##### FN-KOP-10.4 — Displacement and guard

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-10.4 |
| Function Name | Displacement and guard  (subfunction of FN-KOP-10 Correction zone displacement (zone.normal_falloff)) |
| Related Requirement IDs | Inherited from parent FN-KOP-10: FR-050; FR-054; SAF-10; DATA-08 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Normal displacement; FN-KOP-13. |
| Input Data | Inherited from FN-KOP-10 |
| Input Data Structures | Inherited from FN-KOP-10 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Normal displacement; FN-KOP-13. — implemented by ALG-46, ALG-50 |
| Mathematical Model | ALG-46: Centre c from anchor (face_id, bary) evaluated on the current positive; tangent basis (t₁, t₂) from the projected reference direction (OQ-FS-10); p = v − c; normalised radius ρ = ‖p‖/r (circle) or ρ = √((p·t̂₁/r₁)² + (p·t̂₂/r₂)² + (p·n̂_c/min(r₁,r₂))²) … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-46)<br>ALG-50: After every design op: (1) incremental self-intersection test on faces touching moved vertices (ALG-11 incremental); (2) face normal flip test: n_f'·n_f ≤ 0 for any face → reject; (3) sign check: for ops with signed magnitude, sign of displacement along n̂ … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-50) |
| Geometry Operations | ALG-46 Correction / relief zone displacement (plateau + smoothstep) [correction zones / relief zones]; ALG-50 Post-operation geometric guard [geometric constraints] |
| Output Data | Inherited from FN-KOP-10 |
| Output Data Structures | Inherited from FN-KOP-10 |
| Error Handling | Inherited from FN-KOP-10 |
| Performance Requirements | Inherited from FN-KOP-10 — complexity: ALG-46: O(n) (or O(n_affected) with BVH range query); ALG-50: Incremental: O(k log m) for k affected faces [H] |
| Dependencies | Inherited from FN-KOP-10 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-46: Laplacian surface editing (F-SRC-19), ARAP (F-SRC-18), RBF fields — post-MVP/research.; ALG-50: Full validation after every op (slower). |
| Security Considerations | Inherited from FN-KOP-10 |
| Verification Strategy | T — verified within FN-KOP-10 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-KOP-10.4 (proposed id)<br>Isolated test of this step with positive and negative cases: Normal displacement; FN-KOP-13.<br>ALG-46: Plane with zone: displacement profile matches w analytically. Invariants: Vertices outside extent+T bit-identical; sign of m equals sign of deviation.<br>ALG-50: Fold-inducing zone → rejected; benign zone → accepted. Invariants: Rejected op leaves geometry hash unchanged (TC-SAF-09). |
| Integration Test Requirements | Inherited from FN-KOP-10 |
| Open Technical Questions | TQ-19 |

#### FN-KOP-11 — Zone overlap detection

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-11 |
| Function Name | Zone overlap detection |
| Related Requirement IDs | FR-180 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Refuse overlapping enabled zones (FR-180, DEC-028). Support-set intersection evaluated on the scan_prepared positions (order-independent). |
| Input Data | Zone parameter list; scan_prepared V · Preconditions: ≥ 2 enabled zones. |
| Input Data Structures | Params + arrays · module baseline DS |
| Processing Algorithm | 1. Fast reject: ‖c_i − c_j‖ ≥ R_i + R_j with R = max radius + t.<br>2. Else compute support sets S_k = {v : w_k(v) > 0}; overlap ⇔ S_i ∩ S_j ≠ ∅.<br>3. Return all overlapping pairs (zone names).<br>Algorithms: ALG-47 Zone overlap detection |
| Mathematical Model | ALG-47: Two enabled zones overlap iff some vertex has w_i > 0 and w_j > 0 (support intersection on the mesh) — exact on the mesh actually displaced; cheap pre-test with bounding spheres (R + T). |
| Geometry Operations | ALG-47 Zone overlap detection [correction zones / geometric constraints] |
| Output Data | Overlap list. |
| Output Data Structures | JSON [{zone_a, zone_b}] · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-47: O(z²·n) worst, O(z·n) with masks |
| Dependencies | Functions: FN-KOP-10 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-47: Analytic disc intersection (ignores surface shape). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-180; UT-FN-KOP-11 (proposed) · suites: VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-11 (proposed id)<br>Acceptance criteria as unit/component assertions: Saving overlapping zones returns ZONE_OVERLAP_NOT_ALLOWED naming both; non-overlapping zones save.<br>ALG-47: Two discs distance < R₁+R₂+T₁+T₂ → overlap. Invariants: Symmetric relation. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-180; UT-FN-KOP-11 (proposed) |
| Open Technical Questions | OQ-FS-06 |

#### FN-KOP-12 — Local windowed-sinc smoothing (smooth.windowed_sinc)

*Kernel operation (pure function) · MVP · Should · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-12 |
| Function Name | Local windowed-sinc smoothing (smooth.windowed_sinc) |
| Related Requirement IDs | FR-179 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Optional smoothing of the positive only inside a technician-selected region (FR-179, DEC-028). Taubin-type windowed-sinc low-pass filter on the region submesh, blended to zero across the transition width. |
| Input Data | V, F, centre anchor, radius_mm R, transition_mm t, iterations N, passband k_PB · Preconditions: Region anchor valid; iterations and pass-band entered explicitly. |
| Input Data Structures | Arrays + params · module baseline DS |
| Processing Algorithm | 1. Region weight β(v) from Euclidean distance as FN-KOP-10 (plateau R, smoothstep transition t).<br>2. Submesh = faces with any vertex β > 0 plus one ring; run windowed-sinc filter (N, k_PB, boundary vertices of the submesh fixed, no feature-edge smoothing, coordinate normalisation on).<br>3. v' = v + β(v)·(v_s − v) for β > 0; others untouched (bitwise).<br>4. Report max and RMS of distance from moved vertices to the input surface (FN-KCP-04).<br>5. Output tagged 'smoothed'; measurement functions refuse smoothed artifacts.<br>Algorithms: ALG-18 Local windowed-sinc smoothing (Taubin/VTK style) with blended rim; ALG-41 Deviation statistics and one-sided vertex-to-surface Hausdorff; ALG-50 Post-operation geometric guard |
| Mathematical Model | Windowed-sinc filter = polynomial in the graph Laplacian approximating a low-pass with pass-band k_PB (Taubin 1995; VTK [G-SRC-12]).<br>ALG-18: Low-pass filter on the graph Laplacian approximated by a windowed Chebyshev expansion (windowed sinc, pass-band k_PB, N iterations) — negligible shrinkage compared with uniform Laplacian [P G-SRC-12]. Applied only to the technician region: submesh = … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-18)<br>ALG-41: Per region (zone id from op parameters, or whole mesh): min, max, mean, RMS of a per-vertex distance field; one-sided Hausdorff h(A→B) = max_{a∈V_A} d(a, B) using vertex samples (documented as vertex-sampled, a lower bound of the continuous Hausdorff).<br>ALG-50: After every design op: (1) incremental self-intersection test on faces touching moved vertices (ALG-11 incremental); (2) face normal flip test: n_f'·n_f ≤ 0 for any face → reject; (3) sign check: for ops with signed magnitude, sign of displacement along n̂ … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-50) |
| Geometry Operations | ALG-18 Local windowed-sinc smoothing (Taubin/VTK style) with blended rim [mesh smoothing]; ALG-41 Deviation statistics and one-sided vertex-to-surface Hausdorff [geometric comparison]; ALG-50 Post-operation geometric guard [geometric constraints] |
| Output Data | Smoothed surface + report. |
| Output Data Structures | Arrays + JSON {max_dev_mm, rms_dev_mm, vertices_moved} · module baseline DS |
| Error Handling | SELF_INTERSECTION_CREATED → rejected.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-18: O(N · edges in region); ALG-41: O(n); ALG-50: Incremental: O(k log m) for k affected faces [H] |
| Dependencies | Functions: FN-KRP-04; FN-KAN-02; FN-KCP-04; FN-KOP-13 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-SCIPY scipy (BSD-3-Clause (classifier: BSD License); R-MVP); LIB-VTK VTK (BSD-3-Clause; CAND); module baseline |
| Alternative Implementations | ALG-18: Taubin λ/μ (F-SRC-06); bilateral; Laplacian (rejected, shrinkage).; ALG-41: Face-sampled Hausdorff (Metro-style) — post-MVP.; ALG-50: Full validation after every op (slower). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-179; UT-FN-KOP-12 (proposed) · suites: VER-01 · evidence level L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-12 (proposed id)<br>Acceptance criteria as unit/component assertions: Vertices outside region + transition bit-identical; reported max/RMS equal an independent computation within 0.011 mm.<br>ALG-18: Plane stays plane; sphere radius change below tolerance for given N. Invariants: Vertices outside region+transition bit-identical (FR-179 AC).<br>ALG-41: Hand fields. Invariants: Stats of field + c shift by c.<br>ALG-50: Fold-inducing zone → rejected; benign zone → accepted. Invariants: Rejected op leaves geometry hash unchanged (TC-SAF-09).<br>One negative test per error code: SELF_INTERSECTION_CREATED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-179; UT-FN-KOP-12 (proposed) |
| Open Technical Questions | OQ-FS-20; TQ-06 |

#### FN-KOP-13 — Post-operation guard

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KOP-13 |
| Function Name | Post-operation guard |
| Related Requirement IDs | SAF-09; FR-080; SAF-10 |
| Architecture Component | C4/K06 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Reject any design op that creates invalid geometry or an inverted sign (SAF-09, RG-03, RG-07). Executed after every design op inside the kernel. |
| Input Data | Input mesh, output mesh, moved-vertex mask, op sign expectation · Preconditions: Op input and output. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Finite coordinates.<br>2. Self-intersections on faces touching moved vertices vs all faces (FN-KVL-05 incremental) must not exceed the input count.<br>3. For zone/offset ops: mean of n̂_v·(v' − v) over plateau vertices has the sign of m (or d).<br>4. Status ok \| rejected{code, details}.<br>Algorithms: ALG-11 Self-intersection detection with exact predicates; ALG-50 Post-operation geometric guard |
| Mathematical Model | ALG-11: Broad phase: AABB BVH (median split on centroid, deterministic) or sweep-and-prune over sorted boxes; candidate pairs i < j with overlapping boxes. Narrow phase: Guigue–Devillers triangle–triangle overlap built only from orient3d/orient2d signs; signs … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-11)<br>ALG-50: After every design op: (1) incremental self-intersection test on faces touching moved vertices (ALG-11 incremental); (2) face normal flip test: n_f'·n_f ≤ 0 for any face → reject; (3) sign check: for ops with signed magnitude, sign of displacement along n̂ … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-50) |
| Geometry Operations | ALG-11 Self-intersection detection with exact predicates [self-intersection detection]; ALG-50 Post-operation geometric guard [geometric constraints] |
| Output Data | Guard result. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | Rejection codes: NON_FINITE, SELF_INTERSECTION_CREATED, SIGN_CHECK_FAILED.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-11: O(m log m + k) expected for BVH with k candidate pairs [N]; worst case O(m²) for pathological overlap (ghost layers produce many candidates) [H]; ALG-50: Incremental: O(k log m) for k affected faces [H] |
| Dependencies | Functions: FN-KVL-05 · Technical decisions: TD-02, TD-04, TD-05 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-PREDICATES Shewchuk robust predicates (own port) (Public domain (original); JS port robust-predicates under Unlicense; R-MVP); module baseline |
| Alternative Implementations | ALG-11: CGAL (GPL/commercial, OQ-G5); libigl copyleft/cgal (GPL); MeshLib (commercial licence, LIB-MESHLIB); Möller float test (rejected alone).; ALG-50: Full validation after every op (slower). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-080; TC-SAF-09; TC-SAF-10; UT-FN-KOP-13 (proposed) · suites: VER-08, VER-14 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KOP-13 (proposed id)<br>Acceptance criteria as unit/component assertions: Property-based random zones: every output is valid or rejected with a reason (no silent repair).<br>ALG-11: Hand-built pairs: crossing, touching edge, touching vertex, coplanar overlap, coplanar disjoint, shared-edge fold, shared-vertex crossing. Invariants: Count invariant under face permutation and exact rigid motions (permutations of axes).<br>ALG-50: Fold-inducing zone → rejected; benign zone → accepted. Invariants: Rejected op leaves geometry hash unchanged (TC-SAF-09).<br>One negative test per error code: NON_FINITE, SELF_INTERSECTION_CREATED, SIGN_CHECK_FAILED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-080; TC-SAF-09; TC-SAF-10; UT-FN-KOP-13 (proposed) |
| Open Technical Questions | TQ-22; TQ-26 |

### Module KCP — Kernel comparison

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Geometry Engine / — |
| Runtime and execution | C4 worker process (pure function, single-threaded numerics); never in C3 request threads except hashing helpers · Pure function called by jobs |
| Input data structures | DS-01 + typed params (DS-03 schema) |
| Output data structures | DS-05 (outputs + report) |
| Interfaces | IF-03 |
| External libraries | LIB-NUMPY; LIB-SCIPY |
| Performance | Complexity per ALG; wall-time budgets TBD via BM-01/BM-02 (PM-04…08) |
| Security | Pure function: no I/O, no clock, no randomness; inputs validated by OpSpec schemas; display_only inputs rejected (INV-10) |
| Integration tests | Called through the job runner on fixture designs; results persisted and re-read; determinism over 100 runs (VER-07) |
| Alternatives | See ALGORITHM_CATALOG alternatives |
| Versioning | op_version per op; kernel_version + image digest per result |

#### FN-KCP-01 — Signed distance positive → scan

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KCP-01 |
| Function Name | Signed distance positive → scan |
| Related Requirement IDs | FR-070; UR-06; SAF-10 |
| Architecture Component | C4/K07 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Per-vertex signed deviation between the positive and the source scan (FR-070). BVH closest point on scan_prepared; sign from the angle-weighted pseudonormal of the closest feature. |
| Input Data | Positive V_P (scan-origin vertices), scan V_S, F_S · Preconditions: Both meshes in F_anat. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. For each positive vertex p: closest point q on S (FN-KAN-01 machinery) and closest feature (face/edge/vertex).<br>2. Sign = sign((p − q)·ψ) with ψ the angle-weighted pseudonormal of that feature (Bærentzen–Aanæs 2005).<br>3. If the closest feature is a boundary edge/vertex of the open scan → value flagged 'unsigned_boundary' and excluded from statistics.<br>4. Vertices of closure faces (wall/cap) → excluded (OQ-FS-12).<br>5. d(p) in mm; positive = positive surface outside the scan = more space inside the device (SAF-10).<br>Algorithms: ALG-40 Signed distance field with angle-weighted pseudonormal sign |
| Mathematical Model | d(p) = sign((p − q)·ψ)·‖p − q‖.<br>ALG-40: For each positive vertex q: closest point on the scan (ALG-33) with feature type; sign = sign((q − p)·N) where N is the angle-weighted pseudonormal of the closest feature (face normal, edge average, or vertex angle-weighted normal) — gives correct sign on … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-40) |
| Geometry Operations | ALG-40 Signed distance field with angle-weighted pseudonormal sign [geometric comparison / surface deviation maps] |
| Output Data | Deviation field. |
| Output Data Structures | float64[N] + mask {valid, boundary, closure} · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-40: O(n log m) |
| Dependencies | Functions: FN-KAN-01; FN-KOP-05 · Technical decisions: TD-02, TD-09 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-NUMBA numba (BSD-2-Clause (PyPI: "BSD"); CAND); LIB-OPEN3D Open3D (MIT; CAND); LIB-LIBIGL libigl (Python bindings "libigl") (MPL-2.0 (core); include/igl/copyleft/* under GPL/AGPL of wrapped libraries; CAND); module baseline |
| Alternative Implementations | ALG-40: Generalised winding number sign (F-SRC-11); ray parity (fails on open meshes). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-070; TC-SAF-10; UT-FN-KCP-01 (proposed) · suites: VER-01, VER-14 · evidence level L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KCP-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Sphere phantom with zone m: reported max = m ± 0.011 mm; legend equals stored field values.<br>ALG-40: Point outside/inside a sphere. Invariants: Identity design → field ≡ 0 on unmasked vertices. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-070; TC-SAF-10; UT-FN-KCP-01 (proposed) |
| Open Technical Questions | OQ-FS-12; TQ-05; TQ-11 |

##### FN-KCP-01.1 — Closest feature query

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KCP-01.1 |
| Function Name | Closest feature query  (subfunction of FN-KCP-01 Signed distance positive → scan) |
| Related Requirement IDs | Inherited from parent FN-KCP-01: FR-070; UR-06; SAF-10 |
| Architecture Component | C4/K07 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | BVH closest point and feature type. |
| Input Data | Inherited from FN-KCP-01 |
| Input Data Structures | Inherited from FN-KCP-01 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | BVH closest point and feature type. — implemented by ALG-40 |
| Mathematical Model | ALG-40: For each positive vertex q: closest point on the scan (ALG-33) with feature type; sign = sign((q − p)·N) where N is the angle-weighted pseudonormal of the closest feature (face normal, edge average, or vertex angle-weighted normal) — gives correct sign on … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-40) |
| Geometry Operations | ALG-40 Signed distance field with angle-weighted pseudonormal sign [geometric comparison / surface deviation maps] |
| Output Data | Inherited from FN-KCP-01 |
| Output Data Structures | Inherited from FN-KCP-01 |
| Error Handling | Inherited from FN-KCP-01 |
| Performance Requirements | Inherited from FN-KCP-01 — complexity: ALG-40: O(n log m) |
| Dependencies | Inherited from FN-KCP-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-NUMBA numba (BSD-2-Clause (PyPI: "BSD"); CAND); LIB-OPEN3D Open3D (MIT; CAND); LIB-LIBIGL libigl (Python bindings "libigl") (MPL-2.0 (core); include/igl/copyleft/* under GPL/AGPL of wrapped libraries; CAND); module baseline |
| Alternative Implementations | ALG-40: Generalised winding number sign (F-SRC-11); ray parity (fails on open meshes). |
| Security Considerations | Inherited from FN-KCP-01 |
| Verification Strategy | T — verified within FN-KCP-01 test cases; evidence L1 |
| Unit Test Requirements | UT-FN-KCP-01.1 (proposed id)<br>Isolated test of this step with positive and negative cases: BVH closest point and feature type.<br>ALG-40: Point outside/inside a sphere. Invariants: Identity design → field ≡ 0 on unmasked vertices. |
| Integration Test Requirements | Inherited from FN-KCP-01 |
| Open Technical Questions | TQ-05; TQ-11 |

##### FN-KCP-01.2 — Sign by pseudonormal

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KCP-01.2 |
| Function Name | Sign by pseudonormal  (subfunction of FN-KCP-01 Signed distance positive → scan) |
| Related Requirement IDs | Inherited from parent FN-KCP-01: FR-070; UR-06; SAF-10 |
| Architecture Component | C4/K07 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Angle-weighted pseudonormal sign. |
| Input Data | Inherited from FN-KCP-01 |
| Input Data Structures | Inherited from FN-KCP-01 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Angle-weighted pseudonormal sign. — implemented by ALG-40 |
| Mathematical Model | ALG-40: For each positive vertex q: closest point on the scan (ALG-33) with feature type; sign = sign((q − p)·N) where N is the angle-weighted pseudonormal of the closest feature (face normal, edge average, or vertex angle-weighted normal) — gives correct sign on … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-40) |
| Geometry Operations | ALG-40 Signed distance field with angle-weighted pseudonormal sign [geometric comparison / surface deviation maps] |
| Output Data | Inherited from FN-KCP-01 |
| Output Data Structures | Inherited from FN-KCP-01 |
| Error Handling | Inherited from FN-KCP-01 |
| Performance Requirements | Inherited from FN-KCP-01 — complexity: ALG-40: O(n log m) |
| Dependencies | Inherited from FN-KCP-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-NUMBA numba (BSD-2-Clause (PyPI: "BSD"); CAND); LIB-OPEN3D Open3D (MIT; CAND); LIB-LIBIGL libigl (Python bindings "libigl") (MPL-2.0 (core); include/igl/copyleft/* under GPL/AGPL of wrapped libraries; CAND); module baseline |
| Alternative Implementations | ALG-40: Generalised winding number sign (F-SRC-11); ray parity (fails on open meshes). |
| Security Considerations | Inherited from FN-KCP-01 |
| Verification Strategy | T — verified within FN-KCP-01 test cases; evidence L1 |
| Unit Test Requirements | UT-FN-KCP-01.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Angle-weighted pseudonormal sign.<br>ALG-40: Point outside/inside a sphere. Invariants: Identity design → field ≡ 0 on unmasked vertices. |
| Integration Test Requirements | Inherited from FN-KCP-01 |
| Open Technical Questions | TQ-05; TQ-11 |

##### FN-KCP-01.3 — Exclusion masks

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KCP-01.3 |
| Function Name | Exclusion masks  (subfunction of FN-KCP-01 Signed distance positive → scan) |
| Related Requirement IDs | Inherited from parent FN-KCP-01: FR-070; UR-06; SAF-10 |
| Architecture Component | C4/K07 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Boundary and closure vertices. |
| Input Data | Inherited from FN-KCP-01 |
| Input Data Structures | Inherited from FN-KCP-01 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Boundary and closure vertices. — implemented by ALG-40 |
| Mathematical Model | ALG-40: For each positive vertex q: closest point on the scan (ALG-33) with feature type; sign = sign((q − p)·N) where N is the angle-weighted pseudonormal of the closest feature (face normal, edge average, or vertex angle-weighted normal) — gives correct sign on … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-40) |
| Geometry Operations | ALG-40 Signed distance field with angle-weighted pseudonormal sign [geometric comparison / surface deviation maps] |
| Output Data | Inherited from FN-KCP-01 |
| Output Data Structures | Inherited from FN-KCP-01 |
| Error Handling | Inherited from FN-KCP-01 |
| Performance Requirements | Inherited from FN-KCP-01 — complexity: ALG-40: O(n log m) |
| Dependencies | Inherited from FN-KCP-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-NUMBA numba (BSD-2-Clause (PyPI: "BSD"); CAND); LIB-OPEN3D Open3D (MIT; CAND); LIB-LIBIGL libigl (Python bindings "libigl") (MPL-2.0 (core); include/igl/copyleft/* under GPL/AGPL of wrapped libraries; CAND); module baseline |
| Alternative Implementations | ALG-40: Generalised winding number sign (F-SRC-11); ray parity (fails on open meshes). |
| Security Considerations | Inherited from FN-KCP-01 |
| Verification Strategy | T — verified within FN-KCP-01 test cases; evidence L1 |
| Unit Test Requirements | UT-FN-KCP-01.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Boundary and closure vertices.<br>ALG-40: Point outside/inside a sphere. Invariants: Identity design → field ≡ 0 on unmasked vertices. |
| Integration Test Requirements | Inherited from FN-KCP-01 |
| Open Technical Questions | TQ-05; TQ-11 |

#### FN-KCP-02 — Per-zone deviation statistics

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KCP-02 |
| Function Name | Per-zone deviation statistics |
| Related Requirement IDs | FR-070 |
| Architecture Component | C4/K07 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | min/max/mean deviation per zone (FR-070). Statistics over each zone's support set (w > 0) and its plateau. |
| Input Data | d, zone supports · Preconditions: Deviation field; zone list. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. For each enabled zone: S = support vertices with valid d; min, max, mean; same for plateau.<br>Algorithms: ALG-41 Deviation statistics and one-sided vertex-to-surface Hausdorff |
| Mathematical Model | ALG-41: Per region (zone id from op parameters, or whole mesh): min, max, mean, RMS of a per-vertex distance field; one-sided Hausdorff h(A→B) = max_{a∈V_A} d(a, B) using vertex samples (documented as vertex-sampled, a lower bound of the continuous Hausdorff). |
| Geometry Operations | ALG-41 Deviation statistics and one-sided vertex-to-surface Hausdorff [geometric comparison] |
| Output Data | Stats table. |
| Output Data Structures | JSON [{zone, support:{min,max,mean,n}, plateau:{…}}] · module baseline DS |
| Error Handling | Empty support → n = 0, values null.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-41: O(n) |
| Dependencies | Functions: FN-KCP-01; FN-KOP-10 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-41: Face-sampled Hausdorff (Metro-style) — post-MVP. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-070; UT-FN-KCP-02 (proposed) · suites: VER-01 · evidence level L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KCP-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Stats equal brute-force recomputation.<br>ALG-41: Hand fields. Invariants: Stats of field + c shift by c. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-070; UT-FN-KCP-02 (proposed) |
| Open Technical Questions | None registered |

#### FN-KCP-03 — Point deviation query

*Kernel operation (pure function) · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KCP-03 |
| Function Name | Point deviation query |
| Related Requirement IDs | FR-071 |
| Architecture Component | C4/K07 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Signed distance at a picked point (FR-071). Hint snapped to the full-resolution positive; exact signed distance computed. |
| Input Data | hint_xyz_mm or (face_id, bary) on full-res positive · Preconditions: Deviation computed. |
| Input Data Structures | JSON · module baseline DS |
| Processing Algorithm | 1. Snap hint to positive (FN-KAN-01).<br>2. Compute d at that point as FN-KCP-01.<br>Algorithms: ALG-33 BVH closest point, anchor snap and anchor evaluation |
| Mathematical Model | ALG-33: AABB BVH over faces; closest point on triangle by Voronoi-region classification (Ericson) → (face_id, barycentric, feature type {face, edge, vertex}); ties (equal distance) broken by smallest face_id. Anchor evaluation x = b₀v_{f0} + b₁v_{f1} + b₂v_{f2} on … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-33) |
| Geometry Operations | ALG-33 BVH closest point, anchor snap and anchor evaluation [anatomical landmarks / geometric comparison] |
| Output Data | Value. |
| Output Data Structures | JSON {d_mm, face_id, bary} · module baseline DS |
| Error Handling | Point on closure faces → NOT_APPLICABLE.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-33: Build O(m log m); query O(log m) expected [N] |
| Dependencies | Functions: FN-KCP-01 · Technical decisions: TD-02 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-33: KD-tree on vertices only (wrong: closest vertex ≠ closest point). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-071; UT-FN-KCP-03 (proposed) · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KCP-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Picked value equals the computed distance for that vertex/face.<br>ALG-33: Point above face centre, edge, vertex regions. Invariants: Snap of an on-surface point returns itself.<br>One negative test per error code: NOT_APPLICABLE |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-071; UT-FN-KCP-03 (proposed) |
| Open Technical Questions | TQ-05 |

#### FN-KCP-04 — One-sided vertex-to-surface distance statistics

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KCP-04 |
| Function Name | One-sided vertex-to-surface distance statistics |
| Related Requirement IDs | FR-022; FR-179; FR-177 |
| Architecture Component | C4/K07 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Shared max/RMS deviation report for decimation, offset and smoothing. Vertex-sampled one-sided Hausdorff (FR-022 definition). |
| Input Data | Point set A, surface B (V, F) · Preconditions: — |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. d(a) = min over B via BVH.<br>2. max = max d; rms = √(mean d²); mean, n.<br>Algorithms: ALG-41 Deviation statistics and one-sided vertex-to-surface Hausdorff |
| Mathematical Model | h(A→B) = max_a min_b ‖a − b‖ (vertex sampling; lower bound of the continuous Hausdorff distance).<br>ALG-41: Per region (zone id from op parameters, or whole mesh): min, max, mean, RMS of a per-vertex distance field; one-sided Hausdorff h(A→B) = max_{a∈V_A} d(a, B) using vertex samples (documented as vertex-sampled, a lower bound of the continuous Hausdorff). |
| Geometry Operations | ALG-41 Deviation statistics and one-sided vertex-to-surface Hausdorff [geometric comparison] |
| Output Data | Statistics. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-41: O(n) |
| Dependencies | Functions: FN-KAN-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-41: Face-sampled Hausdorff (Metro-style) — post-MVP. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-022; TC-FR-177; TC-FR-179; UT-FN-KCP-04 (proposed) · suites: VER-01, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KCP-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Matches brute force on 10³ points within 1e-9 mm.<br>ALG-41: Hand fields. Invariants: Stats of field + c shift by c. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-022; TC-FR-177; TC-FR-179; UT-FN-KCP-04 (proposed) |
| Open Technical Questions | None registered |

### Module KRP — Kernel replay, registry, hashing

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Geometry Engine / — |
| Runtime and execution | C4 worker process (pure function, single-threaded numerics); never in C3 request threads except hashing helpers · Pure function called by jobs |
| Input data structures | DS-01 + typed params (DS-03 schema) |
| Output data structures | DS-05 (outputs + report) |
| Interfaces | IF-03 |
| External libraries | LIB-NUMPY; LIB-SCIPY |
| Performance | Complexity per ALG; wall-time budgets TBD via BM-01/BM-02 (PM-04…08) |
| Security | Pure function: no I/O, no clock, no randomness; inputs validated by OpSpec schemas; display_only inputs rejected (INV-10) |
| Integration tests | Called through the job runner on fixture designs; results persisted and re-read; determinism over 100 runs (VER-07) |
| Alternatives | See ALGORITHM_CATALOG alternatives |
| Versioning | op_version per op; kernel_version + image digest per result |

#### FN-KRP-01 — Op-log replay engine

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KRP-01 |
| Function Name | Op-log replay engine |
| Related Requirement IDs | FR-052; FR-053; FR-023; SAF-09; VER-07; UR-03 |
| Architecture Component | C4/K08 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Regenerate any design deterministically from (original, cleanup ops, frame, ordered ops) (FR-052, ADR-003). Evaluates enabled ops in order with per-op caching; stops at the first rejected op. |
| Input Data | original_sha, unit factor, cleanup ops, frame, design ops, config values referenced, kernel_version · Preconditions: All inputs content-addressed. |
| Input Data Structures | JSON + blobs · module baseline DS |
| Processing Algorithm | 1. Stage 1: original → units.to_mm → cleanup ops → scan_prepared.<br>2. Stage 2: design ops in seq order (disabled skipped); closure handled per OQ-FS-01. Op implementations (FN-KOP-*) are looked up in the registry (FN-KRP-04), so the engine does not depend on individual ops.<br>3. Cache key per op = SHA-256(JCS({input_geometry_sha, type, op_version, params, kernel_version})); hit → reuse output.<br>4. Rejected op → return last valid output, rejected op index and code (SAF-09).<br>5. Return final geometry, per-op reports, geometry_sha (FN-KRP-02).<br>Algorithms: ALG-53 Op-log replay engine with content-addressed cache |
| Mathematical Model | ALG-53: Geometry = fold(ops, scan_original): stage 1 original → units.to_mm → enabled cleanup ops → scan_prepared; stage 2 enabled design ops in order (closure as pinned terminal op if OQ-FS-01 = b). Cache key per op = SHA-256(input geometry sha ‖ op type ‖ … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-53) |
| Geometry Operations | ALG-53 Op-log replay engine with content-addressed cache [design versions / reproducibility] |
| Output Data | Positive candidate + reports. |
| Output Data Structures | Arrays + JSON · module baseline DS |
| Error Handling | Missing blob → BLOB_MISSING (integrity incident).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-53: Σ op costs; edit of op k recomputes ops k…n only |
| Dependencies | Functions: FN-KRP-02; FN-KRP-04 · Technical decisions: TD-07, TD-19 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-53: Snapshot geometry per version only (loses replay). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-023; TC-FR-052; TC-FR-053; TC-SAF-09; UT-FN-KRP-01 (proposed) · suites: VER-07, VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KRP-01 (proposed id)<br>Acceptance criteria as unit/component assertions: 100 regenerations of 10 reference designs → 1 geometry hash each; disable + re-enable an op returns the prior hash.<br>ALG-53: Replay of fixture op lists. Invariants: Replay(ops) independent of cache state.<br>One negative test per error code: BLOB_MISSING |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-023; TC-FR-052; TC-FR-053; TC-SAF-09; UT-FN-KRP-01 (proposed) |
| Open Technical Questions | OQ-FS-01; TQ-15 |

##### FN-KRP-01.1 — Scan preparation stage

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KRP-01.1 |
| Function Name | Scan preparation stage  (subfunction of FN-KRP-01 Op-log replay engine) |
| Related Requirement IDs | Inherited from parent FN-KRP-01: FR-052; FR-053; FR-023; SAF-09; VER-07; UR-03 |
| Architecture Component | C4/K08 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Original → mm → cleanup ops. |
| Input Data | Inherited from FN-KRP-01 |
| Input Data Structures | Inherited from FN-KRP-01 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Original → mm → cleanup ops. — implemented by ALG-53 |
| Mathematical Model | ALG-53: Geometry = fold(ops, scan_original): stage 1 original → units.to_mm → enabled cleanup ops → scan_prepared; stage 2 enabled design ops in order (closure as pinned terminal op if OQ-FS-01 = b). Cache key per op = SHA-256(input geometry sha ‖ op type ‖ … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-53) |
| Geometry Operations | ALG-53 Op-log replay engine with content-addressed cache [design versions / reproducibility] |
| Output Data | Inherited from FN-KRP-01 |
| Output Data Structures | Inherited from FN-KRP-01 |
| Error Handling | Inherited from FN-KRP-01 |
| Performance Requirements | Inherited from FN-KRP-01 — complexity: ALG-53: Σ op costs; edit of op k recomputes ops k…n only |
| Dependencies | Inherited from FN-KRP-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-53: Snapshot geometry per version only (loses replay). |
| Security Considerations | Inherited from FN-KRP-01 |
| Verification Strategy | T — verified within FN-KRP-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-KRP-01.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Original → mm → cleanup ops.<br>ALG-53: Replay of fixture op lists. Invariants: Replay(ops) independent of cache state. |
| Integration Test Requirements | Inherited from FN-KRP-01 |
| Open Technical Questions | TQ-15 |

##### FN-KRP-01.2 — Design stage

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KRP-01.2 |
| Function Name | Design stage  (subfunction of FN-KRP-01 Op-log replay engine) |
| Related Requirement IDs | Inherited from parent FN-KRP-01: FR-052; FR-053; FR-023; SAF-09; VER-07; UR-03 |
| Architecture Component | C4/K08 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Ordered enabled ops; closure handling per OQ-FS-01. |
| Input Data | Inherited from FN-KRP-01 |
| Input Data Structures | Inherited from FN-KRP-01 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Ordered enabled ops; closure handling per OQ-FS-01. — implemented by ALG-53 |
| Mathematical Model | ALG-53: Geometry = fold(ops, scan_original): stage 1 original → units.to_mm → enabled cleanup ops → scan_prepared; stage 2 enabled design ops in order (closure as pinned terminal op if OQ-FS-01 = b). Cache key per op = SHA-256(input geometry sha ‖ op type ‖ … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-53) |
| Geometry Operations | ALG-53 Op-log replay engine with content-addressed cache [design versions / reproducibility] |
| Output Data | Inherited from FN-KRP-01 |
| Output Data Structures | Inherited from FN-KRP-01 |
| Error Handling | Inherited from FN-KRP-01 |
| Performance Requirements | Inherited from FN-KRP-01 — complexity: ALG-53: Σ op costs; edit of op k recomputes ops k…n only |
| Dependencies | Inherited from FN-KRP-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-53: Snapshot geometry per version only (loses replay). |
| Security Considerations | Inherited from FN-KRP-01 |
| Verification Strategy | T — verified within FN-KRP-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-KRP-01.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Ordered enabled ops; closure handling per OQ-FS-01.<br>ALG-53: Replay of fixture op lists. Invariants: Replay(ops) independent of cache state. |
| Integration Test Requirements | Inherited from FN-KRP-01 |
| Open Technical Questions | TQ-15 |

##### FN-KRP-01.3 — Per-op cache

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KRP-01.3 |
| Function Name | Per-op cache  (subfunction of FN-KRP-01 Op-log replay engine) |
| Related Requirement IDs | Inherited from parent FN-KRP-01: FR-052; FR-053; FR-023; SAF-09; VER-07; UR-03 |
| Architecture Component | C4/K08 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Content-addressed cache keys. |
| Input Data | Inherited from FN-KRP-01 |
| Input Data Structures | Inherited from FN-KRP-01 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Content-addressed cache keys. — implemented by ALG-53 |
| Mathematical Model | ALG-53: Geometry = fold(ops, scan_original): stage 1 original → units.to_mm → enabled cleanup ops → scan_prepared; stage 2 enabled design ops in order (closure as pinned terminal op if OQ-FS-01 = b). Cache key per op = SHA-256(input geometry sha ‖ op type ‖ … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-53) |
| Geometry Operations | ALG-53 Op-log replay engine with content-addressed cache [design versions / reproducibility] |
| Output Data | Inherited from FN-KRP-01 |
| Output Data Structures | Inherited from FN-KRP-01 |
| Error Handling | Inherited from FN-KRP-01 |
| Performance Requirements | Inherited from FN-KRP-01 — complexity: ALG-53: Σ op costs; edit of op k recomputes ops k…n only |
| Dependencies | Inherited from FN-KRP-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-53: Snapshot geometry per version only (loses replay). |
| Security Considerations | Inherited from FN-KRP-01 |
| Verification Strategy | T — verified within FN-KRP-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-KRP-01.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Content-addressed cache keys.<br>ALG-53: Replay of fixture op lists. Invariants: Replay(ops) independent of cache state. |
| Integration Test Requirements | Inherited from FN-KRP-01 |
| Open Technical Questions | TQ-15 |

##### FN-KRP-01.4 — Failure handling

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KRP-01.4 |
| Function Name | Failure handling  (subfunction of FN-KRP-01 Op-log replay engine) |
| Related Requirement IDs | Inherited from parent FN-KRP-01: FR-052; FR-053; FR-023; SAF-09; VER-07; UR-03 |
| Architecture Component | C4/K08 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Stop at first rejection; return last valid output. |
| Input Data | Inherited from FN-KRP-01 |
| Input Data Structures | Inherited from FN-KRP-01 (DS-01 + typed params (DS-03 schema)) |
| Processing Algorithm | Stop at first rejection; return last valid output. — implemented by ALG-53 |
| Mathematical Model | ALG-53: Geometry = fold(ops, scan_original): stage 1 original → units.to_mm → enabled cleanup ops → scan_prepared; stage 2 enabled design ops in order (closure as pinned terminal op if OQ-FS-01 = b). Cache key per op = SHA-256(input geometry sha ‖ op type ‖ … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-53) |
| Geometry Operations | ALG-53 Op-log replay engine with content-addressed cache [design versions / reproducibility] |
| Output Data | Inherited from FN-KRP-01 |
| Output Data Structures | Inherited from FN-KRP-01 |
| Error Handling | Inherited from FN-KRP-01 |
| Performance Requirements | Inherited from FN-KRP-01 — complexity: ALG-53: Σ op costs; edit of op k recomputes ops k…n only |
| Dependencies | Inherited from FN-KRP-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-53: Snapshot geometry per version only (loses replay). |
| Security Considerations | Inherited from FN-KRP-01 |
| Verification Strategy | T — verified within FN-KRP-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-KRP-01.4 (proposed id)<br>Isolated test of this step with positive and negative cases: Stop at first rejection; return last valid output.<br>ALG-53: Replay of fixture op lists. Invariants: Replay(ops) independent of cache state. |
| Integration Test Requirements | Inherited from FN-KRP-01 |
| Open Technical Questions | TQ-15 |

#### FN-KRP-02 — Canonical geometry hash

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KRP-02 |
| Function Name | Canonical geometry hash |
| Related Requirement IDs | FR-052; FR-090; FR-101; VER-07 |
| Architecture Component | C4/K08 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Byte-exact identity of geometry for approval binding (ADR-010). SHA-256 over a canonical binary layout. |
| Input Data | V float64[N,3], F int32[M,3] · Preconditions: Finite arrays. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Canonicalise −0.0 → +0.0.<br>2. Bytes = 'JGEO1' ‖ uint64LE(N) ‖ uint64LE(M) ‖ V float64 LE row-major ‖ F int32 LE row-major (ADR-016).<br>3. SHA-256.<br>Algorithms: ALG-54 Canonical geometry hash |
| Mathematical Model | ALG-54: geometry_sha256 = SHA-256("JGEO1" ‖ nV (u64 LE) ‖ nF (u64 LE) ‖ V float64 LE row-major with −0.0 → +0.0 ‖ F int32 LE row-major) (ADR-010). |
| Geometry Operations | ALG-54 Canonical geometry hash [design versions / approval binding] |
| Output Data | geometry_sha. |
| Output Data Structures | char(64) hex · module baseline DS |
| Error Handling | Non-finite → programming error.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-54: O(n + m) |
| Dependencies | Functions: none · Technical decisions: TD-19, TD-20 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-54: Order-independent hash (sort faces) — unnecessary cost. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-052; TC-FR-090; TC-FR-101; UT-FN-KRP-02 (proposed) · suites: VER-07, VER-12, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KRP-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Identical arrays → identical hash; a 1-ulp change in any coordinate → different hash.<br>ALG-54: Known vector → known hash. Invariants: Hash changes when any bit changes. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-052; TC-FR-090; TC-FR-101; UT-FN-KRP-02 (proposed) |
| Open Technical Questions | TQ-16 |

#### FN-KRP-03 — Canonical parameter-list hash

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KRP-03 |
| Function Name | Canonical parameter-list hash |
| Related Requirement IDs | FR-090; DATA-04 |
| Architecture Component | C4/K08 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Identity of the parameters bound by approval (FR-090 binding 3). SHA-256 of RFC 8785 canonical JSON. |
| Input Data | cleanup ops, frame id + matrix, ordered design ops (type, version, params, enabled), template ref, config_version · Preconditions: — |
| Input Data Structures | JSON · module baseline DS |
| Processing Algorithm | 1. Serialise with JCS (sorted keys, ES6 number formatting).<br>2. SHA-256.<br>Algorithms: ALG-55 Canonical JSON hash (RFC 8785 JCS) |
| Mathematical Model | ALG-55: params_sha = SHA-256(JCS(op-log ‖ frame ref ‖ config version)); JCS sorts keys by UTF-16 code units and serialises numbers per ECMAScript (shortest round-trip). |
| Geometry Operations | ALG-55 Canonical JSON hash (RFC 8785 JCS) [design versions / parameter binding / configuration diff] |
| Output Data | params_sha. |
| Output Data Structures | char(64) · module baseline DS |
| Error Handling | —<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-55: O(size) |
| Dependencies | Functions: none · Technical decisions: TD-19, TD-20 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-RFC8785 rfc8785 (Apache-2.0; CAND); module baseline |
| Alternative Implementations | ALG-55: Python json.dumps(sort_keys) — differs from JCS for some numbers/strings. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-04; TC-FR-090; UT-FN-KRP-03 (proposed) · suites: VER-12, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KRP-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Key order or whitespace changes do not change the hash; any value change does.<br>ALG-55: RFC 8785 test vectors. Invariants: Key order independence. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-04; TC-FR-090; UT-FN-KRP-03 (proposed) |
| Open Technical Questions | None registered |

#### FN-KRP-04 — Operation registry and parameter validation

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KRP-04 |
| Function Name | Operation registry and parameter validation |
| Related Requirement IDs | SAF-02; FR-055; FR-052 |
| Architecture Component | C4/K08 · Geometry Engine · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Versioned op catalogue with JSON Schemas that contain no defaults for clinical/production values (INV-12, SAF-02). Every op type has (type, op_version, schema, idempotent flag, topology_preserving flag). |
| Input Data | Op request · Preconditions: — |
| Input Data Structures | JSON · module baseline DS |
| Processing Algorithm | 1. Reject unknown type/version → OP_UNKNOWN.<br>2. Validate params: required keys present (else PARAM_NOT_SET), types, finiteness, structural ranges (radius > 0, transition ≥ 0, iterations ≥ 1).<br>3. Reject unknown keys.<br>4. Schema test in CI: no 'default' for clinical/production keys.<br>Algorithms: ALG-61 Operation registry and parameter-schema validation |
| Mathematical Model | ALG-61: Registry maps (type, version) → OpSpec (DS-03). Parameters are validated against a JSON Schema 2020-12 document per op version: required keys, types, units in key names, numeric bounds that are purely technical (e.g. radius_mm > 0); clinical/production … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-61) |
| Geometry Operations | ALG-61 Operation registry and parameter-schema validation [design versions / geometric constraints] |
| Output Data | Validated params. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | PARAM_NOT_SET (422), PARAM_INVALID (422), OP_UNKNOWN (422).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-61: O(size of params) |
| Dependencies | Functions: none · Technical decisions: TD-19 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-JSONSCHEMA jsonschema (MIT; R-MVP); module baseline |
| Alternative Implementations | ALG-61: pydantic models only (schemas still exported for INT-05 and manifest). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-052; TC-FR-055; TC-SAF-02; UT-FN-KRP-04 (proposed) · suites: VER-07, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KRP-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Schema test proves no defaults; missing magnitude returns PARAM_NOT_SET.<br>ALG-61: Every op schema: valid sample passes; each required key missing → PARAM_NOT_SET; extra key rejected. Invariants: No schema contains a default for a clinical key (meta-test).<br>One negative test per error code: OP_UNKNOWN, PARAM_INVALID, PARAM_NOT_SET |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-052; TC-FR-055; TC-SAF-02; UT-FN-KRP-04 (proposed) |
| Open Technical Questions | None registered |

### Module KEX — Kernel export manifest

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Import/Export Layer / Geometry Engine |
| Runtime and execution | C4 worker process (pure function, single-threaded numerics); never in C3 request threads except hashing helpers · Pure function called by jobs |
| Input data structures | DS-01 + typed params (DS-03 schema) |
| Output data structures | DS-05 (outputs + report) |
| Interfaces | IF-03 |
| External libraries | LIB-NUMPY; LIB-SCIPY |
| Performance | Complexity per ALG; wall-time budgets TBD via BM-01/BM-02 (PM-04…08) |
| Security | Pure function: no I/O, no clock, no randomness; inputs validated by OpSpec schemas; display_only inputs rejected (INV-10) |
| Integration tests | Called through the job runner on fixture designs; results persisted and re-read; determinism over 100 runs (VER-07) |
| Alternatives | See ALGORITHM_CATALOG alternatives |
| Versioning | op_version per op; kernel_version + image digest per result |

#### FN-KEX-01 — Build export manifest

*Kernel operation (pure function) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-KEX-01 |
| Function Name | Build export manifest |
| Related Requirement IDs | FR-103; INT-05; SAF-10; SAF-06; NFR-08 |
| Architecture Component | C4/K09 · Import/Export Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Carry zone metadata, units, frame and approval to production (FR-103). jude-manifest/0.1 JSON (07 §6.7; format confirmation TD-01, OQ-FS-23). |
| Input Data | case_id, version, STL name+SHA, frame (F_export matrix + definition ref + config_version), source scan SHA, op list with categories and effect statements, template ref, approval summary, re-import result, build, SAF-01 text · Preconditions: Approved version; export STL written. |
| Input Data Structures | Domain records · module baseline DS |
| Processing Algorithm | 1. Assemble object; every zone/offset/adjustment carries effect {positive_surface: outward\|inward, device_inner_surface: more space\|less space} (SAF-10).<br>2. Every index value included carries definition ID + version (SAF-06).<br>3. Serialise JCS; manifest_sha.<br>Algorithms: ALG-52 Export frame transform and manufacturing geometry hand-off |
| Mathematical Model | ALG-52: F_export = rule(F_anat) from configuration (origin, axes; DEC-015, UD-16); export geometry = approved positive (re-generated by replay, hash re-checked) transformed by T_anat→export (det +1); written as binary STL mm (ALG-06) with manifest … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-52) |
| Geometry Operations | ALG-52 Export frame transform and manufacturing geometry hand-off [manufacturing geometry / head surface input] |
| Output Data | Manifest JSON. |
| Output Data Structures | application/json; schema jude-manifest/0.1 · module baseline DS |
| Error Handling | Missing field → MANIFEST_INCOMPLETE (export failed).<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-52: O(m) |
| Dependencies | Functions: FN-KRP-03 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); module baseline |
| Alternative Implementations | ALG-52: 3MF with embedded units (post-MVP). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-103; TC-INT-05; TC-SAF-06; TC-SAF-10; UT-FN-KEX-01 (proposed) · suites: VER-06, VER-14, VER-20 · evidence level L0, L1, L1/L2 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KEX-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Manifest validates against schema; STL hash in manifest equals file hash; effect block present for every op.<br>ALG-52: Manifest schema validation. Invariants: Exported geometry = approved geometry within 1e-4 mm.<br>One negative test per error code: MANIFEST_INCOMPLETE |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-103; TC-INT-05; TC-SAF-06; TC-SAF-10; UT-FN-KEX-01 (proposed) |
| Open Technical Questions | OQ-FS-23 |

#### FN-KEX-02 — Validate manifest against published schema

*Kernel operation (pure function) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-KEX-02 |
| Function Name | Validate manifest against published schema |
| Related Requirement IDs | INT-05; FR-103 |
| Architecture Component | C4/K09 · Import/Export Layer · Worker OS process (one job per process), single-threaded numerics (OMP/BLAS = 1) |
| Technical Purpose | Guarantee a machine-readable, versioned contract (INT-05). JSON Schema validation before release. |
| Input Data | Manifest JSON, schema file · Preconditions: Manifest built. |
| Input Data Structures | JSON Schema 2020-12 · module baseline DS |
| Processing Algorithm | 1. Validate; on failure export not released.<br>Algorithms: ALG-52 Export frame transform and manufacturing geometry hand-off |
| Mathematical Model | ALG-52: F_export = rule(F_anat) from configuration (origin, axes; DEC-015, UD-16); export geometry = approved positive (re-generated by replay, hash re-checked) transformed by T_anat→export (det +1); written as binary STL mm (ALG-06) with manifest … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-52) |
| Geometry Operations | ALG-52 Export frame transform and manufacturing geometry hand-off [manufacturing geometry / head surface input] |
| Output Data | Result. |
| Output Data Structures | JSON {valid, errors[]} · module baseline DS |
| Error Handling | Invalid → export failed MANIFEST_INVALID.<br>Policy EH-KRN (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-52: O(m) |
| Dependencies | Functions: FN-KEX-01 |
| External Libraries | LIB-NUMPY numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; R-MVP); LIB-JSONSCHEMA jsonschema (MIT; R-MVP); module baseline |
| Alternative Implementations | ALG-52: 3MF with embedded units (post-MVP). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-103; TC-INT-05; UT-FN-KEX-02 (proposed) · suites: VER-06, VER-20 · evidence level L0, L1/L2 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-KEX-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Published schema; sample manifest validates.<br>ALG-52: Manifest schema validation. Invariants: Exported geometry = approved geometry within 1e-4 mm.<br>One negative test per error code: MANIFEST_INVALID |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-103; TC-INT-05; UT-FN-KEX-02 (proposed) |
| Open Technical Questions | None registered |

## SS-05 — Anatomy and measurement

### Module ANA — Anatomy: landmarks and frame

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Domain Layer / UI Layer; Geometry Engine |
| Runtime and execution | C3 API; C4 jobs (snap, frame, coverage); C1 W03 screens · Request + background jobs |
| Input data structures | DS-08 hints; DS-16 frame definitions |
| Output data structures | DS-08; DS-06; coverage report |
| Interfaces | IF-01; IF-02; IF-03 |
| External libraries | Kernel (own) + spatial library (TQ-05) |
| Performance | Snap latency per landmark TBD (interactive, BM-07) |
| Security | Stored coordinates only from server snap; supersession transactional (INV-08) |
| Integration tests | Place landmarks → frame job → confirm → coverage; landmark move supersedes dependants |
| Alternatives | Client-side snapping (rejected 07 §6.4) |
| Versioning | Frame definition version; landmark history append-only |

#### FN-ANA-01 — Create landmark set

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-ANA-01 |
| Function Name | Create landmark set |
| Related Requirement IDs | FR-030; FR-012; FR-014; FR-170 |
| Architecture Component | C3/M06, C1/W03 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Start landmarking a prepared scan under a chosen frame definition. Creates an empty set bound to (scan_prepared SHA, frame definition ID+version). |
| Input Data | scan_id, frame_definition_ref · Preconditions: Scan case- and unit-confirmed; gate passed or warn overridden; frame definition complete. |
| Input Data Structures | POST /scans/{id}/landmark-sets · module baseline DS |
| Processing Algorithm | 1. Check gates: CASE_ASSOC_NOT_CONFIRMED, UNIT_NOT_CONFIRMED, GATE_NOT_PASSED, CONFIG_NOT_SET.<br>2. Create set {version 1, reference topology hash}; emit landmarks.set_created. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Landmark set. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | See gate codes.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-SCN-06; FN-SCN-11; FN-CFG-06 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Client-side snapping (rejected 07 §6.4) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-012; TC-FR-014; TC-FR-030; TC-FR-170 · suites: VER-08, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-ANA-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Creation refused until all three intake gates pass.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-012; TC-FR-014; TC-FR-030; TC-FR-170 |
| Open Technical Questions | None registered |

#### FN-ANA-02 — Place, move or delete a landmark

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-ANA-02 |
| Function Name | Place, move or delete a landmark |
| Related Requirement IDs | FR-030; DATA-15; DATA-07; DATA-13 |
| Architecture Component | C3/M06, C1/W03 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Record each named landmark as a server-snapped surface anchor with a placement trail. Viewer pick on the LOD sends a hint; server snaps to the full-resolution surface; history rows are never overwritten (DATA-15). |
| Input Data | landmark code, hint_xyz_mm (F_scan) \| delete · Preconditions: Landmark set active (not superseded). |
| Input Data Structures | PUT /landmark-sets/{id}/landmarks/{code} {hint_xyz_mm} · module baseline DS |
| Processing Algorithm | 1. Validate code ∈ definition.<br>2. Snap via job or synchronous kernel call (FN-KAN-01); store landmark {face_id, bary, xyz_cache, snap_distance}.<br>3. If snap_distance > configured limit → flag 'snap distance large' (OQ-FS-14).<br>4. Append history row {hint, face_id, bary, snap_distance, user, time} (no UPDATE/DELETE on history).<br>5. Any change after frame computation supersedes frame, measurement sets and designs (FN-ANA-05).<br>6. Emit landmarks.changed.<br>Algorithms: ALG-33 BVH closest point, anchor snap and anchor evaluation |
| Mathematical Model | ALG-33: AABB BVH over faces; closest point on triangle by Voronoi-region classification (Ericson) → (face_id, barycentric, feature type {face, edge, vertex}); ties (equal distance) broken by smallest face_id. Anchor evaluation x = b₀v_{f0} + b₁v_{f1} + b₂v_{f2} on … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-33) |
| Geometry Operations | ALG-33 BVH closest point, anchor snap and anchor evaluation [anatomical landmarks / geometric comparison] |
| Output Data | Landmark. |
| Output Data Structures | JSON {code, face_id, bary, xyz_mm, snap_distance_mm, flagged} · module baseline DS |
| Error Handling | Unknown code → 422 LANDMARK_UNKNOWN.<br>Set superseded → 409 DEPENDENCY_SUPERSEDED.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-33: Build O(m log m); query O(log m) expected [N] |
| Dependencies | Functions: FN-KAN-01; FN-ANA-01; FN-ANA-05 · Technical decisions: TD-02 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-33: KD-tree on vertices only (wrong: closest vertex ≠ closest point). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-07; TC-DATA-13; TC-DATA-15; TC-FR-030 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-ANA-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Stored coordinates on surface (< 1e-6 mm); place + 2 moves → 3 history rows.<br>ALG-33: Point above face centre, edge, vertex regions. Invariants: Snap of an on-surface point returns itself.<br>One negative test per error code: DEPENDENCY_SUPERSEDED, LANDMARK_UNKNOWN |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-07; TC-DATA-13; TC-DATA-15; TC-FR-030 |
| Open Technical Questions | OQ-FS-14 |

#### FN-ANA-03 — Compute anatomical frame (job)

*Background job · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-ANA-03 |
| Function Name | Compute anatomical frame (job) |
| Related Requirement IDs | FR-031; FR-033; SAF-03 |
| Architecture Component | C3/M06, C1/W03 · Domain Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Build F_anat from the complete landmark set (FR-031). Runs FN-KFR-02 and stores the frame with provenance. |
| Input Data | landmark_set_id · Preconditions: All landmarks of the definition placed. |
| Input Data Structures | POST /landmark-sets/{id}/frame → 202 · module baseline DS |
| Processing Algorithm | 1. Missing landmark → 409 LANDMARKS_INCOMPLETE.<br>2. Run FN-KFR-02; store frame {matrix, det, definition ref, landmark-set hash}.<br>3. Generate display LOD in F_anat with axes, mid-sagittal plane and L/R labels (FN-KOP-04).<br>Algorithms: ALG-31 Anatomical frame construction from named landmarks |
| Mathematical Model | ALG-31: Clinic frame definition (DEC-027) names landmarks and rules: origin o (point \| midpoint \| centroid \| projection); primary axis a₁ = normalise(p_j − p_i); reference plane normal from least-squares plane through ≥ 3 landmarks (SVD of centred points, smallest … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-31) |
| Geometry Operations | ALG-31 Anatomical frame construction from named landmarks [coordinate systems / anatomical landmarks] |
| Output Data | Frame (unconfirmed). |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | FRAME_DEGENERATE, FRAME_INVALID surfaced with landmark names.<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-31: O(k) for k landmarks |
| Dependencies | Functions: FN-KFR-02; FN-JOB-01; FN-ANA-02 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-31: Kabsch/Umeyama template fit (post-MVP visit registration, F-SRC-07); PCA of scan (rejected: depends on scan extent). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-031; TC-FR-033; TC-SAF-03 · suites: VER-01, VER-03, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-ANA-03 (proposed id)<br>Acceptance criteria as unit/component assertions: On VER-01 phantoms axes match analytic frame within tolerance.<br>ALG-31: Analytic landmark sets → exact axes; swapped labels → warning. Invariants: RᵀR = I; det = +1; frame equivariance under rigid motion of input.<br>One negative test per error code: FRAME_DEGENERATE, FRAME_INVALID |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-031; TC-FR-033; TC-SAF-03 |
| Open Technical Questions | None registered |

#### FN-ANA-04 — Confirm frame and run coverage check

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-ANA-04 |
| Function Name | Confirm frame and run coverage check |
| Related Requirement IDs | FR-032; FR-033; FR-172; SAF-03 |
| Architecture Component | C3/M06, C1/W03 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Human confirmation of orientation and laterality before any measurement or design (FR-032). Technician reviews axes, mid-sagittal plane and L/R labels; coverage check (FR-172) runs after confirmation. |
| Input Data | frame_id, confirm=true · Preconditions: Frame computed. |
| Input Data Structures | POST /frames/{id}/confirm · module baseline DS |
| Processing Algorithm | 1. Show LATERALITY_LABEL_MISMATCH warnings if any.<br>2. Store confirmed_by/at; emit frame.confirmed.<br>3. Run FN-KAN-03; block → frame stays confirmed but measurement/design return COVERAGE_BLOCKED; warn → shown (override via FN-SCN-07 pattern with reason). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | No own geometry computation; invokes kernel functions FN-KAN-03 through IF-02/IF-03. |
| Output Data | Confirmed frame + coverage report. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | FRAME_NOT_CONFIRMED returned by measurement/design until confirmed.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-ANA-03; FN-KAN-03 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Client-side snapping (rejected 07 §6.4) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-032; TC-FR-033; TC-FR-172; TC-SAF-03 · suites: VER-03, VER-08, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-ANA-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Measurement/design API return FRAME_NOT_CONFIRMED before confirmation; reload re-displays identical landmarks and frame.<br>One negative test per error code: FRAME_NOT_CONFIRMED<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-032; TC-FR-033; TC-FR-172; TC-SAF-03 |
| Open Technical Questions | None registered |

#### FN-ANA-05 — Propagate supersession

*Background job · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-ANA-05 |
| Function Name | Propagate supersession |
| Related Requirement IDs | SAF-08; FR-046 |
| Architecture Component | C3/M06, C1/W03 · Domain Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Prevent approval of results built on outdated anatomy (SAF-08, FR-046). Marks dependants superseded in the same transaction as the upstream change. |
| Input Data | Changed object · Preconditions: Upstream change: cleanup change, landmark change, frame recomputation. |
| Input Data Structures | Internal · module baseline DS |
| Processing Algorithm | 1. Dependency graph: scan_prepared → landmark sets → frames → measurement sets, designs → design versions → approvals.<br>2. Mark every downstream object superseded=true (approvals keep their record but their versions become non-exportable).<br>3. Emit *.superseded events. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Supersession flags. |
| Output Data Structures | DB updates · module baseline DS |
| Error Handling | —<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-AUD-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Client-side snapping (rejected 07 §6.4) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-046; TC-SAF-08 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-ANA-05 (proposed id)<br>Acceptance criteria as unit/component assertions: Move a landmark → dependent design not approvable (DEPENDENCY_SUPERSEDED).<br>Job handler tests with fake kernel results: success, deterministic rejection, retryable failure, idempotent re-run. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-046; TC-SAF-08 |
| Open Technical Questions | None registered |

### Module MEA — Measurement

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Domain Layer / Geometry Engine; UI Layer |
| Runtime and execution | C3 API; C4 measurement job; C1 W04 · Request + background job |
| Input data structures | Confirmed frame; DS-10 definitions |
| Output data structures | DS-11 sets with provenance |
| Interfaces | IF-01; IF-02; IF-03 |
| External libraries | Kernel (own) |
| Performance | Measurement job time TBD (BM-07) |
| Security | No severity/threshold outputs (FR-045); output guard in API (FN-MEA-03) |
| Integration tests | Definition selection required; values equal VER-01 analytic within DEC-025; supersession on landmark change |
| Alternatives | — |
| Versioning | Definition id+version stored per value |

#### FN-MEA-01 — Compute measurement set

*User interaction · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-MEA-01 |
| Function Name | Compute measurement set |
| Related Requirement IDs | FR-040; FR-041; FR-042; FR-043; DATA-03; DATA-13; DATA-21; DATA-11; FR-179; STK-03 |
| Architecture Component | C3/M07, C1/W04 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Compute CI, CVA, CVAI and HC under explicitly selected definitions with full provenance (FR-040…043). Technician selects definitions; job computes values on scan_prepared in the confirmed frame (never on a smoothed or design mesh). |
| Input Data | frame_id, definition_refs[] (explicit) · Preconditions: Frame confirmed; coverage not blocked; definitions complete. |
| Input Data Structures | POST /frames/{id}/measurement-sets → 202 · module baseline DS |
| Processing Algorithm | 1. Empty selection → 422 DEFINITION_NOT_SELECTED (DEC-014, DEC-027).<br>2. Per definition: plane from plane/level rule in F_anat → FN-KMS-01 → FN-KMS-02 → FN-KMS-03/04/05; synthetic contact flag FN-KMS-06.<br>3. Store value records with 7 provenance fields (definition ID+version, frame ID, landmark-set hash, source-mesh hash, software version, operator, UTC time) + computed flag + provenance_class=derived + config_version.<br>4. Values not computable → stored as not_computed with reason.<br>5. Emit measurement.computed. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | No own geometry computation; invokes kernel functions FN-KMS-01, FN-KMS-02, FN-KMS-03, FN-KMS-04, FN-KMS-05, FN-KMS-06 through IF-02/IF-03. |
| Output Data | Measurement set. |
| Output Data Structures | JSON {set_id, values[{name, value, unit, definition, provenance…}]} · module baseline DS |
| Error Handling | FRAME_NOT_CONFIRMED, COVERAGE_BLOCKED, DEFINITION_NOT_SELECTED, CONTOUR_NOT_CLOSED, CONTOUR_AMBIGUOUS.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-KMS-01; FN-KMS-02; FN-KMS-03; FN-KMS-04; FN-KMS-05; FN-KMS-06; FN-ANA-04; FN-CFG-05 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-03; TC-DATA-11; TC-DATA-13; TC-DATA-21; TC-FR-040; TC-FR-041; TC-FR-042; TC-FR-043; TC-FR-179 · suites: VER-01, VER-02, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-MEA-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Phantom values within VER-01 tolerance per variant; no value record lacks any of the 7 fields; smoothed artifact rejected as input.<br>One negative test per error code: CONTOUR_AMBIGUOUS, CONTOUR_NOT_CLOSED, COVERAGE_BLOCKED, DEFINITION_NOT_SELECTED, FRAME_NOT_CONFIRMED<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-03; TC-DATA-11; TC-DATA-13; TC-DATA-21; TC-FR-040; TC-FR-041; TC-FR-042; TC-FR-043; TC-FR-179 |
| Open Technical Questions | OQ-FS-02; OQ-FS-03 |

##### FN-MEA-01.1 — Definition selection gate

*User interaction · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-MEA-01.1 |
| Function Name | Definition selection gate  (subfunction of FN-MEA-01 Compute measurement set) |
| Related Requirement IDs | Inherited from parent FN-MEA-01: FR-040; FR-041; FR-042; FR-043; DATA-03; DATA-13; DATA-21; DATA-11; FR-179; STK-03 |
| Architecture Component | C3/M07, C1/W04 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Explicit selection, completeness check. |
| Input Data | Inherited from FN-MEA-01 |
| Input Data Structures | Inherited from FN-MEA-01 (Confirmed frame; DS-10 definitions) |
| Processing Algorithm | Explicit selection, completeness check. |
| Mathematical Model | Inherited from FN-MEA-01 |
| Geometry Operations | Inherited from FN-MEA-01 |
| Output Data | Inherited from FN-MEA-01 |
| Output Data Structures | Inherited from FN-MEA-01 |
| Error Handling | Inherited from FN-MEA-01 |
| Performance Requirements | Inherited from FN-MEA-01 |
| Dependencies | Inherited from FN-MEA-01 |
| External Libraries | Inherited from FN-MEA-01 |
| Alternative Implementations | Inherited from FN-MEA-01 |
| Security Considerations | Inherited from FN-MEA-01 |
| Verification Strategy | T — verified within FN-MEA-01 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-MEA-01.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Explicit selection, completeness check. |
| Integration Test Requirements | Inherited from FN-MEA-01 |
| Open Technical Questions | Inherited from FN-MEA-01 |

##### FN-MEA-01.2 — Plane construction

*User interaction · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-MEA-01.2 |
| Function Name | Plane construction  (subfunction of FN-MEA-01 Compute measurement set) |
| Related Requirement IDs | Inherited from parent FN-MEA-01: FR-040; FR-041; FR-042; FR-043; DATA-03; DATA-13; DATA-21; DATA-11; FR-179; STK-03 |
| Architecture Component | C3/M07, C1/W04 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Plane/level rule evaluated in F_anat. |
| Input Data | Inherited from FN-MEA-01 |
| Input Data Structures | Inherited from FN-MEA-01 (Confirmed frame; DS-10 definitions) |
| Processing Algorithm | Plane/level rule evaluated in F_anat. |
| Mathematical Model | Inherited from FN-MEA-01 |
| Geometry Operations | Inherited from FN-MEA-01 |
| Output Data | Inherited from FN-MEA-01 |
| Output Data Structures | Inherited from FN-MEA-01 |
| Error Handling | Inherited from FN-MEA-01 |
| Performance Requirements | Inherited from FN-MEA-01 |
| Dependencies | Inherited from FN-MEA-01 |
| External Libraries | Inherited from FN-MEA-01 |
| Alternative Implementations | Inherited from FN-MEA-01 |
| Security Considerations | Inherited from FN-MEA-01 |
| Verification Strategy | T — verified within FN-MEA-01 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-MEA-01.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Plane/level rule evaluated in F_anat. |
| Integration Test Requirements | Inherited from FN-MEA-01 |
| Open Technical Questions | Inherited from FN-MEA-01 |

##### FN-MEA-01.3 — Index computation

*User interaction · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-MEA-01.3 |
| Function Name | Index computation  (subfunction of FN-MEA-01 Compute measurement set) |
| Related Requirement IDs | Inherited from parent FN-MEA-01: FR-040; FR-041; FR-042; FR-043; DATA-03; DATA-13; DATA-21; DATA-11; FR-179; STK-03 |
| Architecture Component | C3/M07, C1/W04 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | FN-KMS-02…05 per definition. |
| Input Data | Inherited from FN-MEA-01 |
| Input Data Structures | Inherited from FN-MEA-01 (Confirmed frame; DS-10 definitions) |
| Processing Algorithm | FN-KMS-02…05 per definition. |
| Mathematical Model | Inherited from FN-MEA-01 |
| Geometry Operations | Inherited from FN-MEA-01 |
| Output Data | Inherited from FN-MEA-01 |
| Output Data Structures | Inherited from FN-MEA-01 |
| Error Handling | Inherited from FN-MEA-01 |
| Performance Requirements | Inherited from FN-MEA-01 |
| Dependencies | Inherited from FN-MEA-01 |
| External Libraries | Inherited from FN-MEA-01 |
| Alternative Implementations | Inherited from FN-MEA-01 |
| Security Considerations | Inherited from FN-MEA-01 |
| Verification Strategy | T — verified within FN-MEA-01 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-MEA-01.3 (proposed id)<br>Isolated test of this step with positive and negative cases: FN-KMS-02…05 per definition. |
| Integration Test Requirements | Inherited from FN-MEA-01 |
| Open Technical Questions | Inherited from FN-MEA-01 |

##### FN-MEA-01.4 — Provenance record

*User interaction · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-MEA-01.4 |
| Function Name | Provenance record  (subfunction of FN-MEA-01 Compute measurement set) |
| Related Requirement IDs | Inherited from parent FN-MEA-01: FR-040; FR-041; FR-042; FR-043; DATA-03; DATA-13; DATA-21; DATA-11; FR-179; STK-03 |
| Architecture Component | C3/M07, C1/W04 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | 7 fields + computed flag + provenance class + config version. |
| Input Data | Inherited from FN-MEA-01 |
| Input Data Structures | Inherited from FN-MEA-01 (Confirmed frame; DS-10 definitions) |
| Processing Algorithm | 7 fields + computed flag + provenance class + config version. |
| Mathematical Model | Inherited from FN-MEA-01 |
| Geometry Operations | Inherited from FN-MEA-01 |
| Output Data | Inherited from FN-MEA-01 |
| Output Data Structures | Inherited from FN-MEA-01 |
| Error Handling | Inherited from FN-MEA-01 |
| Performance Requirements | Inherited from FN-MEA-01 |
| Dependencies | Inherited from FN-MEA-01 |
| External Libraries | Inherited from FN-MEA-01 |
| Alternative Implementations | Inherited from FN-MEA-01 |
| Security Considerations | Inherited from FN-MEA-01 |
| Verification Strategy | T — verified within FN-MEA-01 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-MEA-01.4 (proposed id)<br>Isolated test of this step with positive and negative cases: 7 fields + computed flag + provenance class + config version. |
| Integration Test Requirements | Inherited from FN-MEA-01 |
| Open Technical Questions | Inherited from FN-MEA-01 |

#### FN-MEA-02 — Present measurement values

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-MEA-02 |
| Function Name | Present measurement values |
| Related Requirement IDs | FR-044; FR-047; FR-178; SAF-06; NFR-09; UR-02; FR-045 |
| Architecture Component | C3/M07, C1/W04 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Show each value with its definition, plane and repeatability text; no interpretation. Values panel and 3D overlay of plane, contour, W/L extremes and diagonals (FR-047). |
| Input Data | set_id · Preconditions: Measurement set exists. |
| Input Data Structures | GET /measurement-sets/{id} · module baseline DS |
| Processing Algorithm | 1. Every value rendered with definition name + version (FR-044, SAF-06).<br>2. Display precision from configuration; stored precision unchanged (NFR-09).<br>3. Repeatability: configured band for (index, definition) or text 'repeatability not established locally' (FR-178).<br>4. Overlay plane, selected contour, extremes and diagonals in the viewer.<br>5. No colours, thresholds or severity words (FR-045). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Rendered view. |
| Output Data Structures | UI · module baseline DS |
| Error Handling | not_computed values shown with reason.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-MEA-01; FN-UIX-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method I · test cases: TC-FR-044; TC-FR-045; TC-FR-047; TC-FR-178; TC-SAF-06 · suites: VER-09, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-MEA-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Automated scan of all views finds 0 definition-less values; repeatability text present before VER-05.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-044; TC-FR-045; TC-FR-047; TC-FR-178; TC-SAF-06 |
| Open Technical Questions | None registered |

#### FN-MEA-03 — Index output guard

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-MEA-03 |
| Function Name | Index output guard |
| Related Requirement IDs | SAF-06; FR-045; FR-043 |
| Architecture Component | C3/M07, C1/W04 · Domain Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Runtime and CI guarantee that no output carries an index value without definition, and no severity/threshold output exists. Serializer for index values used by UI API, report, CSV and manifest. |
| Input Data | Value record · Preconditions: — |
| Input Data Structures | Internal · module baseline DS |
| Processing Algorithm | 1. Serializer refuses a value without definition ID+version (raises).<br>2. Schema of outputs contains no severity/category fields; CI code search for index threshold constants (FN-OPS-01). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Serialised value. |
| Output Data Structures | JSON {value, unit, definition:{id, version, name}} · module baseline DS |
| Error Handling | Missing definition → 500 + test failure.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-MEA-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-043; TC-FR-045; TC-SAF-06 · suites: VER-09, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-MEA-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Automated output scan finds 0 values without definition.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-043; TC-FR-045; TC-SAF-06 |
| Open Technical Questions | None registered |

#### FN-MEA-04 — Measurement history

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-MEA-04 |
| Function Name | Measurement history |
| Related Requirement IDs | FR-046 |
| Architecture Component | C3/M07, C1/W04 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Keep and show superseded measurement sets. List of sets per scan with status current/superseded. |
| Input Data | scan_id · Preconditions: — |
| Input Data Structures | GET /scans/{id}/measurement-sets · module baseline DS |
| Processing Algorithm | 1. List sets newest first with superseded flag and reason. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | List. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | —<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-ANA-05; FN-MEA-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-046 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-MEA-04 (proposed id)<br>Acceptance criteria as unit/component assertions: After landmark move two sets exist; earlier flagged superseded.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-046 |
| Open Technical Questions | None registered |

## SS-06 — Positive-mould design

### Module DES — Design workspace

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Domain Layer / Geometry Engine; UI Layer |
| Runtime and execution | C3 API; C4 regenerate job; C1 W05 workspace · Request + background job |
| Input data structures | DS-04 op edits; DS-12 |
| Output data structures | DS-23 drafts/saved versions; DS-14 LOD |
| Interfaces | IF-01; IF-02; IF-03; IF-05 |
| External libraries | Kernel (own) |
| Performance | PM-06 T_regen (NFR-04, TBD) |
| Security | No pre-filled correction values (SAF-02); out-of-range confirmation logged (SAF-07); saved versions immutable |
| Integration tests | Edit op → regenerate → LOD displayed; failed op keeps last valid geometry; save creates immutable version; template apply |
| Alternatives | Snapshot-per-edit geometry (rejected ADR-003) |
| Versioning | op_version; DesignVersion.kernel_version + image digest |

#### FN-DES-01 — Create design

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-DES-01 |
| Function Name | Create design |
| Related Requirement IDs | FR-055; SAF-02; FR-061; DATA-11 |
| Architecture Component | C3/M08, C1/W05 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Start a positive-mould design on a confirmed frame with an empty op list (or a template). Creates design + draft version 1. |
| Input Data | scan_id, frame_id, optional template_version_ref · Preconditions: Frame confirmed, not superseded. |
| Input Data Structures | POST /cases/{id}/designs · module baseline DS |
| Processing Algorithm | 1. Draft version with modification list length 0 (FR-055) unless a template is applied (FN-DES-07).<br>2. Record config_version (DATA-11); emit design.created. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Design + draft. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | FRAME_NOT_CONFIRMED.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-ANA-04 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Snapshot-per-edit geometry (rejected ADR-003) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-11; TC-FR-055; TC-FR-061; TC-SAF-02 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-DES-01 (proposed id)<br>Acceptance criteria as unit/component assertions: New design has 0 ops; no correction field pre-filled.<br>One negative test per error code: FRAME_NOT_CONFIRMED<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-11; TC-FR-055; TC-FR-061; TC-SAF-02 |
| Open Technical Questions | None registered |

#### FN-DES-02 — Edit the modification list

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-DES-02 |
| Function Name | Edit the modification list |
| Related Requirement IDs | FR-053; FR-050; FR-051; FR-054; FR-177; FR-179; FR-180; SAF-07; SAF-02; DATA-08; UR-03 |
| Architecture Component | C3/M08, C1/W05 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Add, edit, disable, re-enable, reorder and delete design operations; each change regenerates and is logged (FR-053). Draft-only; op types: offset.uniform_normal, adjust.global_axis (length \| circumference), zone.normal_falloff, smooth.windowed_sinc, positive.close_base (rule per OQ-FS-01). |
| Input Data | op type + params (all explicit), or seq + patch, or reorder list · Preconditions: Version is draft. |
| Input Data Structures | POST/PATCH /designs/{id}/versions/{n}/ops; POST …/ops/reorder · module baseline DS |
| Processing Algorithm | 1. Validate params (FN-KRP-04): PARAM_NOT_SET for any missing value.<br>2. Zones: category from clinic list (FR-054) and name required; overlap check FN-KOP-11 → 409 ZONE_OVERLAP_NOT_ALLOWED.<br>3. Range check against magnitude_ranges_mm → requires confirm_out_of_range (FN-DES-05).<br>4. Store op; enqueue regeneration (FN-DES-03); emit design.op_changed with before/after summary.<br>Algorithms: ALG-61 Operation registry and parameter-schema validation; ALG-46 Correction / relief zone displacement (plateau + smoothstep); ALG-48 Global axis length adjustment (anisotropic scaling about the frame origin); ALG-49 Circumference adjustment at a level with tapered band |
| Mathematical Model | ALG-61: Registry maps (type, version) → OpSpec (DS-03). Parameters are validated against a JSON Schema 2020-12 document per op version: required keys, types, units in key names, numeric bounds that are purely technical (e.g. radius_mm > 0); clinical/production … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-61)<br>ALG-46: Centre c from anchor (face_id, bary) evaluated on the current positive; tangent basis (t₁, t₂) from the projected reference direction (OQ-FS-10); p = v − c; normalised radius ρ = ‖p‖/r (circle) or ρ = √((p·t̂₁/r₁)² + (p·t̂₂/r₂)² + (p·n̂_c/min(r₁,r₂))²) … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-46)<br>ALG-48: Extent L along axis â over scan-origin vertices; k = (L + Δ)/L > 0; v' = o + (I + (k − 1)ââᵀ)(v − o). Extent changes by exactly Δ; orthogonal coordinates unchanged. |
| Geometry Operations | ALG-61 Operation registry and parameter-schema validation [design versions / geometric constraints]; ALG-46 Correction / relief zone displacement (plateau + smoothstep) [correction zones / relief zones]; ALG-48 Global axis length adjustment (anisotropic scaling about the frame origin) [geometric constraints / correction]; ALG-49 Circumference adjustment at a level with tapered band [geometric constraints / correction] |
| Output Data | Updated draft + regeneration job. |
| Output Data Structures | HTTP 202 · module baseline DS |
| Error Handling | VERSION_NOT_DRAFT, PARAM_NOT_SET, ZONE_OVERLAP_NOT_ALLOWED, OUT_OF_RANGE_UNCONFIRMED, CATEGORY_REQUIRED.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-61: O(size of params); ALG-46: O(n) (or O(n_affected) with BVH range query); ALG-48: O(n); ALG-49: O(n) |
| Dependencies | Functions: FN-KRP-04; FN-KOP-11; FN-DES-03; FN-DES-05; FN-CFG-04 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-61: pydantic models only (schemas still exported for INT-05 and manifest).; ALG-46: Laplacian surface editing (F-SRC-19), ARAP (F-SRC-18), RBF fields — post-MVP/research.; ALG-48: Tapered/banded scaling (as ALG-49). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-08; TC-FR-050; TC-FR-051; TC-FR-053; TC-FR-054; TC-FR-177; TC-FR-179; TC-FR-180; TC-SAF-02; TC-SAF-07 · suites: VER-01, VER-07, VER-08, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-DES-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Each change produces one audit event and one regeneration; disable + re-enable restores the prior hash.<br>ALG-61: Every op schema: valid sample passes; each required key missing → PARAM_NOT_SET; extra key rejected. Invariants: No schema contains a default for a clinical key (meta-test).<br>ALG-46: Plane with zone: displacement profile matches w analytically. Invariants: Vertices outside extent+T bit-identical; sign of m equals sign of deviation.<br>ALG-48: Box extent change. Invariants: Orthogonal extents unchanged.<br>One negative test per error code: CATEGORY_REQUIRED, OUT_OF_RANGE_UNCONFIRMED, PARAM_NOT_SET, VERSION_NOT_DRAFT, ZONE_OVERLAP_NOT_ALLOWED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-08; TC-FR-050; TC-FR-051; TC-FR-053; TC-FR-054; TC-FR-177; TC-FR-179; TC-FR-180; TC-SAF-02; TC-SAF-07 |
| Open Technical Questions | OQ-FS-01 |

##### FN-DES-02.1 — Zone editor

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-DES-02.1 |
| Function Name | Zone editor  (subfunction of FN-DES-02 Edit the modification list) |
| Related Requirement IDs | Inherited from parent FN-DES-02: FR-053; FR-050; FR-051; FR-054; FR-177; FR-179; FR-180; SAF-07; SAF-02; DATA-08; UR-03 |
| Architecture Component | C3/M08, C1/W05 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Centre pick (anchor), shape, magnitude, transition, category, name. |
| Input Data | Inherited from FN-DES-02 |
| Input Data Structures | Inherited from FN-DES-02 (DS-04 op edits; DS-12) |
| Processing Algorithm | Centre pick (anchor), shape, magnitude, transition, category, name. — implemented by ALG-46 |
| Mathematical Model | ALG-46: Centre c from anchor (face_id, bary) evaluated on the current positive; tangent basis (t₁, t₂) from the projected reference direction (OQ-FS-10); p = v − c; normalised radius ρ = ‖p‖/r (circle) or ρ = √((p·t̂₁/r₁)² + (p·t̂₂/r₂)² + (p·n̂_c/min(r₁,r₂))²) … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-46) |
| Geometry Operations | ALG-46 Correction / relief zone displacement (plateau + smoothstep) [correction zones / relief zones] |
| Output Data | Inherited from FN-DES-02 |
| Output Data Structures | Inherited from FN-DES-02 |
| Error Handling | Inherited from FN-DES-02 |
| Performance Requirements | Inherited from FN-DES-02 — complexity: ALG-46: O(n) (or O(n_affected) with BVH range query) |
| Dependencies | Inherited from FN-DES-02 |
| External Libraries | Inherited from FN-DES-02 |
| Alternative Implementations | ALG-46: Laplacian surface editing (F-SRC-19), ARAP (F-SRC-18), RBF fields — post-MVP/research. |
| Security Considerations | Inherited from FN-DES-02 |
| Verification Strategy | T — verified within FN-DES-02 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-DES-02.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Centre pick (anchor), shape, magnitude, transition, category, name.<br>ALG-46: Plane with zone: displacement profile matches w analytically. Invariants: Vertices outside extent+T bit-identical; sign of m equals sign of deviation. |
| Integration Test Requirements | Inherited from FN-DES-02 |
| Open Technical Questions | Inherited from FN-DES-02 |

##### FN-DES-02.2 — Offset editor

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-DES-02.2 |
| Function Name | Offset editor  (subfunction of FN-DES-02 Edit the modification list) |
| Related Requirement IDs | Inherited from parent FN-DES-02: FR-053; FR-050; FR-051; FR-054; FR-177; FR-179; FR-180; SAF-07; SAF-02; DATA-08; UR-03 |
| Architecture Component | C3/M08, C1/W05 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | offset_mm + purpose, no default. |
| Input Data | Inherited from FN-DES-02 |
| Input Data Structures | Inherited from FN-DES-02 (DS-04 op edits; DS-12) |
| Processing Algorithm | offset_mm + purpose, no default. |
| Mathematical Model | Inherited from FN-DES-02 |
| Geometry Operations | Inherited from FN-DES-02 |
| Output Data | Inherited from FN-DES-02 |
| Output Data Structures | Inherited from FN-DES-02 |
| Error Handling | Inherited from FN-DES-02 |
| Performance Requirements | Inherited from FN-DES-02 |
| Dependencies | Inherited from FN-DES-02 |
| External Libraries | Inherited from FN-DES-02 |
| Alternative Implementations | Inherited from FN-DES-02 |
| Security Considerations | Inherited from FN-DES-02 |
| Verification Strategy | T — verified within FN-DES-02 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-DES-02.2 (proposed id)<br>Isolated test of this step with positive and negative cases: offset_mm + purpose, no default. |
| Integration Test Requirements | Inherited from FN-DES-02 |
| Open Technical Questions | Inherited from FN-DES-02 |

##### FN-DES-02.3 — Global adjustment editor

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-DES-02.3 |
| Function Name | Global adjustment editor  (subfunction of FN-DES-02 Edit the modification list) |
| Related Requirement IDs | Inherited from parent FN-DES-02: FR-053; FR-050; FR-051; FR-054; FR-177; FR-179; FR-180; SAF-07; SAF-02; DATA-08; UR-03 |
| Architecture Component | C3/M08, C1/W05 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Axis length or circumference at level with band/transition. |
| Input Data | Inherited from FN-DES-02 |
| Input Data Structures | Inherited from FN-DES-02 (DS-04 op edits; DS-12) |
| Processing Algorithm | Axis length or circumference at level with band/transition. — implemented by ALG-48, ALG-49 |
| Mathematical Model | ALG-48: Extent L along axis â over scan-origin vertices; k = (L + Δ)/L > 0; v' = o + (I + (k − 1)ââᵀ)(v − o). Extent changes by exactly Δ; orthogonal coordinates unchanged.<br>ALG-49: Section at level h (ALG-23) gives perimeter C; radial scaling about the level axis by k = (C + Δ)/C applied with weight w(\|z − h\|) (plateau band + smoothstep transition); perimeter at h changes by Δ exactly for a star-shaped contour (radial scaling of a … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-49) |
| Geometry Operations | ALG-48 Global axis length adjustment (anisotropic scaling about the frame origin) [geometric constraints / correction]; ALG-49 Circumference adjustment at a level with tapered band [geometric constraints / correction] |
| Output Data | Inherited from FN-DES-02 |
| Output Data Structures | Inherited from FN-DES-02 |
| Error Handling | Inherited from FN-DES-02 |
| Performance Requirements | Inherited from FN-DES-02 — complexity: ALG-48: O(n); ALG-49: O(n) |
| Dependencies | Inherited from FN-DES-02 |
| External Libraries | Inherited from FN-DES-02 |
| Alternative Implementations | ALG-48: Tapered/banded scaling (as ALG-49).; ALG-49: Normal offset in band (changes perimeter by 2πd only for circles). |
| Security Considerations | Inherited from FN-DES-02 |
| Verification Strategy | T — verified within FN-DES-02 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-DES-02.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Axis length or circumference at level with band/transition.<br>ALG-48: Box extent change. Invariants: Orthogonal extents unchanged.<br>ALG-49: Cylinder band perimeter change. Invariants: Vertices outside band+transition unchanged. |
| Integration Test Requirements | Inherited from FN-DES-02 |
| Open Technical Questions | Inherited from FN-DES-02 |

##### FN-DES-02.4 — Smoothing region editor

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-DES-02.4 |
| Function Name | Smoothing region editor  (subfunction of FN-DES-02 Edit the modification list) |
| Related Requirement IDs | Inherited from parent FN-DES-02: FR-053; FR-050; FR-051; FR-054; FR-177; FR-179; FR-180; SAF-07; SAF-02; DATA-08; UR-03 |
| Architecture Component | C3/M08, C1/W05 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Centre, radius, transition, iterations, pass-band. |
| Input Data | Inherited from FN-DES-02 |
| Input Data Structures | Inherited from FN-DES-02 (DS-04 op edits; DS-12) |
| Processing Algorithm | Centre, radius, transition, iterations, pass-band. |
| Mathematical Model | Inherited from FN-DES-02 |
| Geometry Operations | Inherited from FN-DES-02 |
| Output Data | Inherited from FN-DES-02 |
| Output Data Structures | Inherited from FN-DES-02 |
| Error Handling | Inherited from FN-DES-02 |
| Performance Requirements | Inherited from FN-DES-02 |
| Dependencies | Inherited from FN-DES-02 |
| External Libraries | Inherited from FN-DES-02 |
| Alternative Implementations | Inherited from FN-DES-02 |
| Security Considerations | Inherited from FN-DES-02 |
| Verification Strategy | T — verified within FN-DES-02 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-DES-02.4 (proposed id)<br>Isolated test of this step with positive and negative cases: Centre, radius, transition, iterations, pass-band. |
| Integration Test Requirements | Inherited from FN-DES-02 |
| Open Technical Questions | Inherited from FN-DES-02 |

##### FN-DES-02.5 — Stack operations

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-DES-02.5 |
| Function Name | Stack operations  (subfunction of FN-DES-02 Edit the modification list) |
| Related Requirement IDs | Inherited from parent FN-DES-02: FR-053; FR-050; FR-051; FR-054; FR-177; FR-179; FR-180; SAF-07; SAF-02; DATA-08; UR-03 |
| Architecture Component | C3/M08, C1/W05 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Disable/enable/reorder/delete with regeneration. |
| Input Data | Inherited from FN-DES-02 |
| Input Data Structures | Inherited from FN-DES-02 (DS-04 op edits; DS-12) |
| Processing Algorithm | Disable/enable/reorder/delete with regeneration. |
| Mathematical Model | Inherited from FN-DES-02 |
| Geometry Operations | Inherited from FN-DES-02 |
| Output Data | Inherited from FN-DES-02 |
| Output Data Structures | Inherited from FN-DES-02 |
| Error Handling | Inherited from FN-DES-02 |
| Performance Requirements | Inherited from FN-DES-02 |
| Dependencies | Inherited from FN-DES-02 |
| External Libraries | Inherited from FN-DES-02 |
| Alternative Implementations | Inherited from FN-DES-02 |
| Security Considerations | Inherited from FN-DES-02 |
| Verification Strategy | T — verified within FN-DES-02 test cases; evidence L0, L1 |
| Unit Test Requirements | UT-FN-DES-02.5 (proposed id)<br>Isolated test of this step with positive and negative cases: Disable/enable/reorder/delete with regeneration. |
| Integration Test Requirements | Inherited from FN-DES-02 |
| Open Technical Questions | Inherited from FN-DES-02 |

#### FN-DES-03 — Regenerate positive (job)

*Background job · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-DES-03 |
| Function Name | Regenerate positive (job) |
| Related Requirement IDs | FR-052; SAF-09; NFR-04 |
| Architecture Component | C3/M08, C1/W05 · Domain Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Recompute the positive after every change and keep the last valid state on failure (FR-052, SAF-09). Runs FN-KRP-01; produces display LOD and per-op reports. |
| Input Data | design version spec · Preconditions: Draft with valid params. |
| Input Data Structures | Job payload · module baseline DS |
| Processing Algorithm | 1. Run replay; on success store positive artifact, geometry_sha, params_sha (FN-KRP-03), LOD.<br>2. On op rejection: mark op status=rejected with code, keep last valid geometry, draft flag regen_failed=true (save refused).<br>3. Emit design.regenerated / design.regeneration_failed.<br>Algorithms: ALG-53 Op-log replay engine with content-addressed cache |
| Mathematical Model | ALG-53: Geometry = fold(ops, scan_original): stage 1 original → units.to_mm → enabled cleanup ops → scan_prepared; stage 2 enabled design ops in order (closure as pinned terminal op if OQ-FS-01 = b). Cache key per op = SHA-256(input geometry sha ‖ op type ‖ … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-53) |
| Geometry Operations | ALG-53 Op-log replay engine with content-addressed cache [design versions / reproducibility] |
| Output Data | Positive candidate. |
| Output Data Structures | Artifacts + JSON · module baseline DS |
| Error Handling | REGEN_FAILED.<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-53: Σ op costs; edit of op k recomputes ops k…n only |
| Dependencies | Functions: FN-KRP-01; FN-KRP-03; FN-KOP-04; FN-JOB-02 · Technical decisions: TD-01 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-53: Snapshot geometry per version only (loses replay). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-052; TC-SAF-09 · suites: VER-07, VER-08 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-DES-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Injected kernel failure leaves the geometry hash unchanged; save returns REGEN_FAILED.<br>ALG-53: Replay of fixture op lists. Invariants: Replay(ops) independent of cache state.<br>One negative test per error code: REGEN_FAILED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-052; TC-SAF-09 |
| Open Technical Questions | OQ-FS-29; TQ-13 |

#### FN-DES-04 — Save design version

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-DES-04 |
| Function Name | Save design version |
| Related Requirement IDs | FR-056; DATA-04; DATA-11; FR-091 |
| Architecture Component | C3/M08, C1/W05 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Freeze a draft into an immutable version (FR-056, DATA-04). Saving does not approve (UR-04). |
| Input Data | design_id, n · Preconditions: Last regeneration succeeded; no pending job. |
| Input Data Structures | POST /designs/{id}/versions/{n}/save · module baseline DS |
| Processing Algorithm | 1. Refuse REGEN_FAILED / REGEN_PENDING.<br>2. Persist DATA-04 record (source mesh hash, cleanup ops, frame ID, ordered ops, template ref, config version, software version, geometry_sha, params_sha, author, time); status=saved.<br>3. Later edits create draft n+1 with parent n (FR-091).<br>4. Emit design.version_saved. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Saved version. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | REGEN_FAILED, REGEN_PENDING.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-DES-03 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Snapshot-per-edit geometry (rejected ADR-003) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-04; TC-DATA-11; TC-FR-056; TC-FR-091 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-DES-04 (proposed id)<br>Acceptance criteria as unit/component assertions: UPDATE on a saved version is rejected; edits create version n+1.<br>One negative test per error code: REGEN_FAILED, REGEN_PENDING<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-04; TC-DATA-11; TC-FR-056; TC-FR-091 |
| Open Technical Questions | None registered |

#### FN-DES-05 — Out-of-range confirmation

*User interaction · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-DES-05 |
| Function Name | Out-of-range confirmation |
| Related Requirement IDs | SAF-07 |
| Architecture Component | C3/M08, C1/W05 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Typing-error barrier for magnitudes and adjustments outside clinic ranges (SAF-07). Explicit confirmation, logged. |
| Input Data | op request + confirm_out_of_range=true · Preconditions: Op param outside configured range. |
| Input Data Structures | Flag on op request · module baseline DS |
| Processing Algorithm | 1. Compare \|value\| with magnitude_ranges_mm for the op family; outside and not confirmed → 409 OUT_OF_RANGE_UNCONFIRMED.<br>2. Confirmed → emit design.range_confirmed with value and range. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Confirmation record. |
| Output Data Structures | audit event · module baseline DS |
| Error Handling | NOT_SET range → CONFIG_NOT_SET.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CFG-04 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Snapshot-per-edit geometry (rejected ADR-003) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-SAF-07 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-DES-05 (proposed id)<br>Acceptance criteria as unit/component assertions: Value beyond range prompts and logs; in-range does not.<br>One negative test per error code: CONFIG_NOT_SET, NOT_SET<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SAF-07 |
| Open Technical Questions | None registered |

#### FN-DES-06 — Sign-convention presentation

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-DES-06 |
| Function Name | Sign-convention presentation |
| Related Requirement IDs | SAF-10; VER-14 |
| Architecture Component | C3/M08, C1/W05 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | State every direction as effect on the positive and on the device inner surface (SAF-10). Labels on controls, legend and manifest. |
| Input Data | Sign of magnitude/offset · Preconditions: — |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Positive value → 'наружу на позитиве / больше пространства в изделии'; negative → 'внутрь на позитиве / меньше пространства в изделии' (wording from resource file, UD-23 vocabulary).<br>2. Same mapping in deviation legend and manifest effect block. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Labels. |
| Output Data Structures | UI strings · module baseline DS |
| Error Handling | —<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-UIX-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Snapshot-per-edit geometry (rejected ADR-003) |
| Security Considerations | Module baseline |
| Verification Strategy | Method I · test cases: TC-SAF-10 · suites: VER-14 · evidence level L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-DES-06 (proposed id)<br>Acceptance criteria as unit/component assertions: VER-14 sign test passes in UI control label, map sign and manifest.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SAF-10 |
| Open Technical Questions | None registered |

#### FN-DES-07 — Templates: save, apply, version

*User interaction · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-DES-07 |
| Function Name | Templates: save, apply, version |
| Related Requirement IDs | FR-060; FR-061; FR-062; UR-07 |
| Architecture Component | C3/M08, C1/W05 · Domain Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Reuse clinic correction parameters entered by the technician (FR-060…062). Template = named, versioned op list (optionally without zone locations). |
| Input Data | Save: design version, include_locations (bool), name. Apply: template_version, design draft. · Preconditions: Technician. |
| Input Data Structures | POST /templates; POST /templates/{id}/versions; apply via FN-DES-01 · module baseline DS |
| Processing Algorithm | 1. Save copies ops (strips anchors if include_locations=false; such zones need a centre before regeneration → PARAM_NOT_SET).<br>2. Edit creates template version n+1; designs keep the version they used.<br>3. Apply records template ID+version; ops remain individually editable. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Template version. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | —<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-DES-01; FN-DES-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Snapshot-per-edit geometry (rejected ADR-003) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-060; TC-FR-061; TC-FR-062 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-DES-07 (proposed id)<br>Acceptance criteria as unit/component assertions: Template ops equal source; design shows template ID+version; older designs keep old version.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-060; TC-FR-061; TC-FR-062 |
| Open Technical Questions | None registered |

## SS-07 — Review, approval and export

### Module REV — Review and approval

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Validation Layer / Domain Layer; UI Layer |
| Runtime and execution | C3 API (gates, approval transaction); C4 review job; C1 W06 · Request + background job |
| Input data structures | Saved DS-23; DS-25; DS-13; checklist; prescription sha |
| Output data structures | DS-25; DS-13; DS-20; rejection |
| Interfaces | IF-01; IF-02; IF-03 |
| External libraries | Kernel (own) |
| Performance | PM-07 |
| Security | Technician-only approval (FR-130); gates re-checked server-side in one transaction (ADR-008); statement text stored verbatim |
| Integration tests | Gate matrix G1–G7 each failing alone; approval binding altered → export refused (TC-FR-090); self-approval disclosure |
| Alternatives | — |
| Versioning | DATA-05 schema; checklist version |

#### FN-REV-01 — Run review (deviation + validity) job

*Background job · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-REV-01 |
| Function Name | Run review (deviation + validity) job |
| Related Requirement IDs | FR-070; FR-080; FR-081 |
| Architecture Component | C3/M09, C1/W06 · Validation Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Produce the review evidence for a saved version (FR-070, FR-080). Validity check, deviation field, per-zone stats, LOD with scalar field. |
| Input Data | design_version_id · Preconditions: Version saved. |
| Input Data Structures | POST /design-versions/{id}/review → 202 · module baseline DS |
| Processing Algorithm | 1. FN-KVL-07 on the positive → validity_report bound to geometry_sha.<br>2. FN-KCP-01 + FN-KCP-02 → deviation artifact + stats.<br>3. Status reviewed_pass / reviewed_fail; emit design.reviewed.<br>Algorithms: ALG-13 Composite solid validity (validate.solid); ALG-40 Signed distance field with angle-weighted pseudonormal sign |
| Mathematical Model | ALG-13: Conjunction of geometric checks: boundary edges = 0; non-manifold edges = 0; non-manifold vertices = 0; self-intersections = 0 (ALG-11); components = 1; inconsistent edges = 0; signed volume > 0 (outward); degenerate faces = 0. Each check reported … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-13)<br>ALG-40: For each positive vertex q: closest point on the scan (ALG-33) with feature type; sign = sign((q − p)·N) where N is the angle-weighted pseudonormal of the closest feature (face normal, edge average, or vertex angle-weighted normal) — gives correct sign on … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-40) |
| Geometry Operations | ALG-13 Composite solid validity (validate.solid) [watertightness / manifold validation / solid validity]; ALG-40 Signed distance field with angle-weighted pseudonormal sign [geometric comparison / surface deviation maps] |
| Output Data | Validity report, deviation artifact. |
| Output Data Structures | JSON + artifact · module baseline DS |
| Error Handling | Kernel failure → job failed, status unchanged.<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-13: Dominated by ALG-11; ALG-40: O(n log m) |
| Dependencies | Functions: FN-KVL-07; FN-KCP-01; FN-KCP-02; FN-KOP-04 · Technical decisions: TD-02, TD-09 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-13: manifold3d constructor as validity oracle (reports error status for non-manifold input [N]).; ALG-40: Generalised winding number sign (F-SRC-11); ray parity (fails on open meshes). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-070; TC-FR-080; TC-FR-081 · suites: VER-01, VER-08 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-REV-01 (proposed id)<br>Acceptance criteria as unit/component assertions: VER-08 defects fail; valid phantoms pass; stats reproducible.<br>ALG-13: Each defect type fails exactly its check. Invariants: All checks pass on analytic closed phantoms.<br>ALG-40: Point outside/inside a sphere. Invariants: Identity design → field ≡ 0 on unmasked vertices. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-070; TC-FR-080; TC-FR-081 |
| Open Technical Questions | None registered |

#### FN-REV-02 — Show deviation map and point query

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-REV-02 |
| Function Name | Show deviation map and point query |
| Related Requirement IDs | FR-070; FR-071; UR-06; SAF-10 |
| Architecture Component | C3/M09, C1/W06 · Validation Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Let the technician see where and by how much the positive differs from the scan (UR-06). Colour map with numeric legend (mm), per-zone table, picked-point value. |
| Input Data | design_version_id; picked hint · Preconditions: Review done. |
| Input Data Structures | GET …/deviation; GET …/deviation/query · module baseline DS |
| Processing Algorithm | 1. Render scalar field with diverging colour scale symmetric around 0; legend shows mm and SAF-10 effect wording.<br>2. Per-zone min/max/mean table.<br>3. Pick → FN-KCP-03. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | No own geometry computation; invokes kernel functions FN-KCP-03 through IF-02/IF-03. |
| Output Data | View. |
| Output Data Structures | UI · module baseline DS |
| Error Handling | Excluded vertices (closure/boundary) rendered neutral with legend note.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-REV-01; FN-KCP-03; FN-UIX-04 |
| External Libraries | LIB-THREE three.js + three-mesh-bvh (+ @react-three/fiber optional) (MIT; R-MVP); module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-070; TC-FR-071; TC-SAF-10 · suites: VER-01, VER-14, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-REV-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Legend values equal stored field values; picked value equals computed distance.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-070; TC-FR-071; TC-SAF-10 |
| Open Technical Questions | None registered |

#### FN-REV-03 — Validity panel

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-REV-03 |
| Function Name | Validity panel |
| Related Requirement IDs | FR-081; FR-082 |
| Architecture Component | C3/M09, C1/W06 · Validation Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Show geometric checks with geometry-only wording (FR-081, FR-082). Lists each check, count, pass/fail. |
| Input Data | version id · Preconditions: Validity report. |
| Input Data Structures | GET …/validity · module baseline DS |
| Processing Algorithm | 1. Render checks C1–C5 with counts; failing version shows the failed check and affected element count.<br>2. Approved FR-082 label displayed verbatim.<br>Algorithms: ALG-13 Composite solid validity (validate.solid) |
| Mathematical Model | ALG-13: Conjunction of geometric checks: boundary edges = 0; non-manifold edges = 0; non-manifold vertices = 0; self-intersections = 0 (ALG-11); components = 1; inconsistent edges = 0; signed volume > 0 (outward); degenerate faces = 0. Each check reported … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-13) |
| Geometry Operations | ALG-13 Composite solid validity (validate.solid) [watertightness / manifold validation / solid validity] |
| Output Data | Panel. |
| Output Data Structures | UI · module baseline DS |
| Error Handling | —<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-13: Dominated by ALG-11 |
| Dependencies | Functions: FN-REV-01 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-13: manifold3d constructor as validity oracle (reports error status for non-manifold input [N]). |
| Security Considerations | Module baseline |
| Verification Strategy | Method I · test cases: TC-FR-081; TC-FR-082 · suites: VER-08, VER-09 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-REV-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Label present on panel and in report.<br>ALG-13: Each defect type fails exactly its check. Invariants: All checks pass on analytic closed phantoms. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-081; TC-FR-082 |
| Open Technical Questions | None registered |

#### FN-REV-04 — Approve design version

*User interaction · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-REV-04 |
| Function Name | Approve design version |
| Related Requirement IDs | FR-090; FR-093; FR-182; FR-164; FR-175; SAF-08; SAF-11; FR-141; DATA-05; UR-04; FR-081; FR-130 |
| Architecture Component | C3/M09, C1/W06 · Validation Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Explicit, gated approval bound to exact geometry, parameters, scan, measurements and prescription (FR-090, FR-182). Technician-only action with the configured checklist; records self-approval and scope statement verbatim. |
| Input Data | checklist responses (Yes/No/N/A + comment per CHK item), measurement_set_id (OQ-FS-04), prescription_file_id, confirm_stale_source? · Preconditions: Version reviewed_pass; prescription attached; checklist configured. |
| Input Data Structures | POST /design-versions/{id}/approve · module baseline DS |
| Processing Algorithm | 1. Gate order (single transaction): G1 role technician (ROLE_FORBIDDEN); G2 saved ∧ ¬superseded (NOT_SAVED / DEPENDENCY_SUPERSEDED); G3 validity passed for this geometry_sha (VALIDITY_FAILED); G4 all checklist items answered and none 'No' (CHECKLIST_INCOMPLETE); G5 prescription file attached and chosen (PRESCRIPTION_MISSING); G6 newer scan exists → confirm_stale_source required (STALE_SOURCE_UNCONFIRMED); G7 measurement set current for the design's frame (MEASUREMENT_SET_INVALID).<br>2. Write DATA-05 record: version ID, geometry_sha, params_sha, source scan SHA, measurement set ID, approver, role, UTC time, checklist version + responses, self-approval flag (approver authored any op), prescription SHA-256 + upload time, config version + controlled-config last-changed-by/at, SAF-11 statement text verbatim.<br>3. Self-approval → FR-093 statement stored and displayed.<br>4. Emit design.approved. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Approval record. |
| Output Data Structures | JSON (DATA-05) · module baseline DS |
| Error Handling | Gate codes as listed (403/409).<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-REV-01; FN-CAS-06; FN-CFG-04; FN-ANA-05; FN-MEA-01; FN-AUD-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-05; TC-FR-081; TC-FR-090; TC-FR-093; TC-FR-130; TC-FR-141; TC-FR-164; TC-FR-175; TC-FR-182; TC-SAF-08; TC-SAF-11 · suites: VER-08, VER-09, VER-12, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-REV-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Admin → 403; approval stores all bindings and altering any one makes export refuse; incomplete checklist blocks; no approval path without prescription file.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-05; TC-FR-081; TC-FR-090; TC-FR-093; TC-FR-130; TC-FR-141; TC-FR-164; TC-FR-175; TC-FR-182; TC-SAF-08; TC-SAF-11 |
| Open Technical Questions | OQ-FS-04; OQ-FS-21 |

##### FN-REV-04.1 — Gate evaluation

*User interaction · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-REV-04.1 |
| Function Name | Gate evaluation  (subfunction of FN-REV-04 Approve design version) |
| Related Requirement IDs | Inherited from parent FN-REV-04: FR-090; FR-093; FR-182; FR-164; FR-175; SAF-08; SAF-11; FR-141; DATA-05; UR-04; FR-081; FR-130 |
| Architecture Component | C3/M09, C1/W06 · Validation Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | G1–G7 in fixed order; all failures returned as a list. |
| Input Data | Inherited from FN-REV-04 |
| Input Data Structures | Inherited from FN-REV-04 (Saved DS-23; DS-25; DS-13; checklist; prescription sha) |
| Processing Algorithm | G1–G7 in fixed order; all failures returned as a list. |
| Mathematical Model | Inherited from FN-REV-04 |
| Geometry Operations | Inherited from FN-REV-04 |
| Output Data | Inherited from FN-REV-04 |
| Output Data Structures | Inherited from FN-REV-04 |
| Error Handling | Inherited from FN-REV-04 |
| Performance Requirements | Inherited from FN-REV-04 |
| Dependencies | Inherited from FN-REV-04 |
| External Libraries | Inherited from FN-REV-04 |
| Alternative Implementations | Inherited from FN-REV-04 |
| Security Considerations | Inherited from FN-REV-04 |
| Verification Strategy | T — verified within FN-REV-04 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-REV-04.1 (proposed id)<br>Isolated test of this step with positive and negative cases: G1–G7 in fixed order; all failures returned as a list. |
| Integration Test Requirements | Inherited from FN-REV-04 |
| Open Technical Questions | Inherited from FN-REV-04 |

##### FN-REV-04.2 — Checklist capture

*User interaction · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-REV-04.2 |
| Function Name | Checklist capture  (subfunction of FN-REV-04 Approve design version) |
| Related Requirement IDs | Inherited from parent FN-REV-04: FR-090; FR-093; FR-182; FR-164; FR-175; SAF-08; SAF-11; FR-141; DATA-05; UR-04; FR-081; FR-130 |
| Architecture Component | C3/M09, C1/W06 · Validation Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Checklist version from configuration; any 'No' blocks. |
| Input Data | Inherited from FN-REV-04 |
| Input Data Structures | Inherited from FN-REV-04 (Saved DS-23; DS-25; DS-13; checklist; prescription sha) |
| Processing Algorithm | Checklist version from configuration; any 'No' blocks. |
| Mathematical Model | Inherited from FN-REV-04 |
| Geometry Operations | Inherited from FN-REV-04 |
| Output Data | Inherited from FN-REV-04 |
| Output Data Structures | Inherited from FN-REV-04 |
| Error Handling | Inherited from FN-REV-04 |
| Performance Requirements | Inherited from FN-REV-04 |
| Dependencies | Inherited from FN-REV-04 |
| External Libraries | Inherited from FN-REV-04 |
| Alternative Implementations | Inherited from FN-REV-04 |
| Security Considerations | Inherited from FN-REV-04 |
| Verification Strategy | T — verified within FN-REV-04 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-REV-04.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Checklist version from configuration; any 'No' blocks. |
| Integration Test Requirements | Inherited from FN-REV-04 |
| Open Technical Questions | Inherited from FN-REV-04 |

##### FN-REV-04.3 — Binding and record

*User interaction · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-REV-04.3 |
| Function Name | Binding and record  (subfunction of FN-REV-04 Approve design version) |
| Related Requirement IDs | Inherited from parent FN-REV-04: FR-090; FR-093; FR-182; FR-164; FR-175; SAF-08; SAF-11; FR-141; DATA-05; UR-04; FR-081; FR-130 |
| Architecture Component | C3/M09, C1/W06 · Validation Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | DATA-05 record; self-approval detection. |
| Input Data | Inherited from FN-REV-04 |
| Input Data Structures | Inherited from FN-REV-04 (Saved DS-23; DS-25; DS-13; checklist; prescription sha) |
| Processing Algorithm | DATA-05 record; self-approval detection. |
| Mathematical Model | Inherited from FN-REV-04 |
| Geometry Operations | Inherited from FN-REV-04 |
| Output Data | Inherited from FN-REV-04 |
| Output Data Structures | Inherited from FN-REV-04 |
| Error Handling | Inherited from FN-REV-04 |
| Performance Requirements | Inherited from FN-REV-04 |
| Dependencies | Inherited from FN-REV-04 |
| External Libraries | Inherited from FN-REV-04 |
| Alternative Implementations | Inherited from FN-REV-04 |
| Security Considerations | Inherited from FN-REV-04 |
| Verification Strategy | T — verified within FN-REV-04 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-REV-04.3 (proposed id)<br>Isolated test of this step with positive and negative cases: DATA-05 record; self-approval detection. |
| Integration Test Requirements | Inherited from FN-REV-04 |
| Open Technical Questions | Inherited from FN-REV-04 |

#### FN-REV-05 — Reject design version

*User interaction · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-REV-05 |
| Function Name | Reject design version |
| Related Requirement IDs | FR-092; DATA-22 |
| Architecture Component | C3/M09, C1/W06 · Validation Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Record a negative review outcome (FR-092). Typed reason + clinic reason category (DATA-22). |
| Input Data | reason (non-empty), category · Preconditions: Version saved or reviewed. |
| Input Data Structures | POST /design-versions/{id}/reject · module baseline DS |
| Processing Algorithm | 1. Missing reason → 422 REASON_REQUIRED; missing category → 422 CATEGORY_REQUIRED.<br>2. Store rejection; status rejected; emit design.rejected. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Rejection record. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | See logic.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-AUD-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-22; TC-FR-092 · suites: VER-13, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-REV-05 (proposed id)<br>Acceptance criteria as unit/component assertions: Rejected version shows reason, user, time.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-22; TC-FR-092 |
| Open Technical Questions | None registered |

#### FN-REV-06 — Design version state machine

*API service (synchronous) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-REV-06 |
| Function Name | Design version state machine |
| Related Requirement IDs | FR-091; FR-056; SAF-08 |
| Architecture Component | C3/M09, C1/W06 · Validation Layer · API process (ASGI); one DB transaction per request |
| Technical Purpose | Single authority for version status transitions (07 §8.1, ADR-008). draft → saved → reviewed_pass\|reviewed_fail → approved\|rejected → exported; any → superseded. |
| Input Data | Event · Preconditions: — |
| Input Data Structures | Internal · module baseline DS |
| Processing Algorithm | 1. Allowed transitions only; any edit of non-draft → new draft n+1 (FR-091).<br>2. Approval never carries over to a new version. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Status. |
| Output Data Structures | enum · module baseline DS |
| Error Handling | Illegal transition → 409 ILLEGAL_STATE.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: none |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-056; TC-FR-091; TC-SAF-08 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-REV-06 (proposed id)<br>Acceptance criteria as unit/component assertions: Edit after approval → new version 'not approved'; old approval unchanged.<br>One negative test per error code: ILLEGAL_STATE<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-056; TC-FR-091; TC-SAF-08 |
| Open Technical Questions | None registered |

### Module EXP — Export

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Import/Export Layer / Validation Layer; Data Layer |
| Runtime and execution | C3 API (gates); C4 export job · Request + background job (release step not retried) |
| Input data structures | Approved DS-23 + DS-20 |
| Output data structures | STL bytes, DS-15, DS-21 |
| Interfaces | IF-01; IF-02; IF-06 |
| External libraries | Kernel (own); LIB-NUMPYSTL (second reader); LIB-JSONSCHEMA |
| Performance | PM-08 |
| Security | Release only on re-import pass and hash equality; download logged (SEC-15/16); file names J-xxxxxxxx_* only |
| Integration tests | Export of unapproved/mismatched version refused; corrupted-write injection marks failed; manifest validates; download audit |
| Alternatives | 3MF (post-MVP) |
| Versioning | jude-manifest/0.1; STL header schema id |

#### FN-EXP-01 — Request export (gates)

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-EXP-01 |
| Function Name | Request export (gates) |
| Related Requirement IDs | FR-101; FR-141; FR-175; FR-130 |
| Architecture Component | C3/M10, C4/K09, C1/W06 · Import/Export Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Allow export only of approved, unchanged geometry under the current controlled configuration. Gate checks then job enqueue. |
| Input Data | design_version_id, confirm_stale_source? · Preconditions: Approval exists. |
| Input Data Structures | POST /design-versions/{id}/exports → 202 · module baseline DS |
| Processing Algorithm | 1. E0 role technician; E1 approval exists ∧ approval.geometry_sha = version.geometry_sha (APPROVAL_REQUIRED / APPROVAL_HASH_MISMATCH); E2 export_frame and re-import tolerance set (CONFIG_NOT_SET); E3 stale-source confirmation if newer scan (STALE_SOURCE_UNCONFIRMED); E4 approval not flagged reapproval_required (REAPPROVAL_REQUIRED, FR-141); E5 version not superseded.<br>2. Enqueue FN-EXP-02; emit export.created (or export.refused with code). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Export job. |
| Output Data Structures | HTTP 202 · module baseline DS |
| Error Handling | Gate codes; refusals audited.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-REV-04; FN-CFG-04; FN-JOB-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: 3MF (post-MVP) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-101; TC-FR-130; TC-FR-141; TC-FR-175 · suites: VER-12, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-EXP-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Export of unapproved or hash-mismatched version refused via UI and API; outdated approval returns REAPPROVAL_REQUIRED.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-101; TC-FR-130; TC-FR-141; TC-FR-175 |
| Open Technical Questions | None registered |

#### FN-EXP-02 — Export job: STL, manifest, re-import, release

*Background job · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-EXP-02 |
| Function Name | Export job: STL, manifest, re-import, release |
| Related Requirement IDs | FR-100; FR-102; FR-103; DATA-06; INT-04; INT-05; SAF-03; STK-04; NFR-08 |
| Architecture Component | C3/M10, C4/K09, C1/W06 · Import/Export Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Produce and verify the manufacturing hand-off (FR-100…103). Regenerates geometry from the approved spec, checks hash, transforms, writes, re-imports, releases. |
| Input Data | Approved version spec · Preconditions: Gates passed. |
| Input Data Structures | Job payload · module baseline DS |
| Processing Algorithm | 1. Replay (FN-KRP-01) and assert geometry_sha equals the approved hash (else APPROVAL_HASH_MISMATCH, not released).<br>2. Transform to F_export (FN-KFR-04); write binary STL (FN-KIO-06); store blob.<br>3. Build manifest (FN-KEX-01) and validate (FN-KEX-02).<br>4. Re-import compare (FN-KIO-07) with tolerance 1e-4 mm.<br>5. Pass → export record (DATA-06) released=true; fail → status failed, not released; emit export.released / export.failed.<br>6. File names J-xxxxxxxx_v<n>_positive.stl and …_manifest.json.<br>Algorithms: ALG-52 Export frame transform and manufacturing geometry hand-off; ALG-06 Binary STL writer and independent re-read comparison; ALG-32 Rigid transform algebra and reflection guard |
| Mathematical Model | ALG-52: F_export = rule(F_anat) from configuration (origin, axes; DEC-015, UD-16); export geometry = approved positive (re-generated by replay, hash re-checked) transformed by T_anat→export (det +1); written as binary STL mm (ALG-06) with manifest … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-52)<br>ALG-06: Write: float64 → float32 rounding (round-to-nearest), facet normal = normalised (b−a)×(c−a) in float64 then cast, attribute 0, little-endian, 80-byte ASCII header with schema id and design id (no patient data). Re-read: parse with an implementation … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-06)<br>ALG-32: 4×4 homogeneous matrices with explicit (from, to) frame tags; composition checks tag compatibility; inverse via [Rᵀ, −Rᵀt]; validity: ‖RᵀR − I‖_F ≤ 1e-9 and det R = +1 ± 1e-9; any reflection (det −1) is rejected (SAF-03, ADR-009). Export frame F_export … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-32) |
| Geometry Operations | ALG-52 Export frame transform and manufacturing geometry hand-off [manufacturing geometry / head surface input]; ALG-06 Binary STL writer and independent re-read comparison [manufacturing geometry]; ALG-32 Rigid transform algebra and reflection guard [coordinate systems] |
| Output Data | Export record + files. |
| Output Data Structures | DATA-06; binary STL mm; manifest JSON · module baseline DS |
| Error Handling | REIMPORT_FAILED, MANIFEST_INVALID, APPROVAL_HASH_MISMATCH.<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-52: O(m); ALG-06: O(m); ALG-32: O(n) to apply |
| Dependencies | Functions: FN-KRP-01; FN-KFR-04; FN-KIO-06; FN-KIO-07; FN-KEX-01; FN-KEX-02; FN-BLB-01 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-52: 3MF with embedded units (post-MVP).; ALG-06: ASCII STL (larger, decimal rounding); 3MF (post-MVP, FN-PMV-11).; ALG-32: Quaternion storage (no advantage for audit; matrices are what manifests carry). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-06; TC-FR-100; TC-FR-102; TC-FR-103; TC-INT-04; TC-INT-05; TC-SAF-03 · suites: VER-03, VER-06, VER-20 · evidence level L0, L1, L1/L2 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-EXP-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Exported bbox equals in-app bbox within 1e-4 mm; corrupted-write injection → failed; laterality preserved; Neo import (VER-06) on clinic install.<br>ALG-52: Manifest schema validation. Invariants: Exported geometry = approved geometry within 1e-4 mm.<br>ALG-06: Known triangle → known bytes; header content check. Invariants: Triangle count preserved; orientation preserved; laterality preserved (VER-03).<br>ALG-32: Compose/inverse identities; mirror rejected. Invariants: T∘T⁻¹ = I; det preserved.<br>One negative test per error code: APPROVAL_HASH_MISMATCH, MANIFEST_INVALID, REIMPORT_FAILED |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-06; TC-FR-100; TC-FR-102; TC-FR-103; TC-INT-04; TC-INT-05; TC-SAF-03 |
| Open Technical Questions | OQ-FS-32 |

##### FN-EXP-02.1 — Hash re-check

*Background job · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-EXP-02.1 |
| Function Name | Hash re-check  (subfunction of FN-EXP-02 Export job: STL, manifest, re-import, release) |
| Related Requirement IDs | Inherited from parent FN-EXP-02: FR-100; FR-102; FR-103; DATA-06; INT-04; INT-05; SAF-03; STK-04; NFR-08 |
| Architecture Component | C3/M10, C4/K09, C1/W06 · Import/Export Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Replay and compare with approved geometry_sha. |
| Input Data | Inherited from FN-EXP-02 |
| Input Data Structures | Inherited from FN-EXP-02 (Approved DS-23 + DS-20) |
| Processing Algorithm | Replay and compare with approved geometry_sha. |
| Mathematical Model | Inherited from FN-EXP-02 |
| Geometry Operations | Inherited from FN-EXP-02 |
| Output Data | Inherited from FN-EXP-02 |
| Output Data Structures | Inherited from FN-EXP-02 |
| Error Handling | Inherited from FN-EXP-02 |
| Performance Requirements | Inherited from FN-EXP-02 |
| Dependencies | Inherited from FN-EXP-02 |
| External Libraries | Inherited from FN-EXP-02 |
| Alternative Implementations | Inherited from FN-EXP-02 |
| Security Considerations | Inherited from FN-EXP-02 |
| Verification Strategy | T — verified within FN-EXP-02 test cases; evidence L0, L1, L1/L2 |
| Unit Test Requirements | UT-FN-EXP-02.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Replay and compare with approved geometry_sha. |
| Integration Test Requirements | Inherited from FN-EXP-02 |
| Open Technical Questions | Inherited from FN-EXP-02 |

##### FN-EXP-02.2 — Write

*Background job · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-EXP-02.2 |
| Function Name | Write  (subfunction of FN-EXP-02 Export job: STL, manifest, re-import, release) |
| Related Requirement IDs | Inherited from parent FN-EXP-02: FR-100; FR-102; FR-103; DATA-06; INT-04; INT-05; SAF-03; STK-04; NFR-08 |
| Architecture Component | C3/M10, C4/K09, C1/W06 · Import/Export Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | F_export transform + binary STL. |
| Input Data | Inherited from FN-EXP-02 |
| Input Data Structures | Inherited from FN-EXP-02 (Approved DS-23 + DS-20) |
| Processing Algorithm | F_export transform + binary STL. — implemented by ALG-06, ALG-32 |
| Mathematical Model | ALG-06: Write: float64 → float32 rounding (round-to-nearest), facet normal = normalised (b−a)×(c−a) in float64 then cast, attribute 0, little-endian, 80-byte ASCII header with schema id and design id (no patient data). Re-read: parse with an implementation … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-06)<br>ALG-32: 4×4 homogeneous matrices with explicit (from, to) frame tags; composition checks tag compatibility; inverse via [Rᵀ, −Rᵀt]; validity: ‖RᵀR − I‖_F ≤ 1e-9 and det R = +1 ± 1e-9; any reflection (det −1) is rejected (SAF-03, ADR-009). Export frame F_export … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-32) |
| Geometry Operations | ALG-06 Binary STL writer and independent re-read comparison [manufacturing geometry]; ALG-32 Rigid transform algebra and reflection guard [coordinate systems] |
| Output Data | Inherited from FN-EXP-02 |
| Output Data Structures | Inherited from FN-EXP-02 |
| Error Handling | Inherited from FN-EXP-02 |
| Performance Requirements | Inherited from FN-EXP-02 — complexity: ALG-06: O(m); ALG-32: O(n) to apply |
| Dependencies | Inherited from FN-EXP-02 |
| External Libraries | Inherited from FN-EXP-02 |
| Alternative Implementations | ALG-06: ASCII STL (larger, decimal rounding); 3MF (post-MVP, FN-PMV-11).; ALG-32: Quaternion storage (no advantage for audit; matrices are what manifests carry). |
| Security Considerations | Inherited from FN-EXP-02 |
| Verification Strategy | T — verified within FN-EXP-02 test cases; evidence L0, L1, L1/L2 |
| Unit Test Requirements | UT-FN-EXP-02.2 (proposed id)<br>Isolated test of this step with positive and negative cases: F_export transform + binary STL.<br>ALG-06: Known triangle → known bytes; header content check. Invariants: Triangle count preserved; orientation preserved; laterality preserved (VER-03).<br>ALG-32: Compose/inverse identities; mirror rejected. Invariants: T∘T⁻¹ = I; det preserved. |
| Integration Test Requirements | Inherited from FN-EXP-02 |
| Open Technical Questions | Inherited from FN-EXP-02 |

##### FN-EXP-02.3 — Manifest

*Background job · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-EXP-02.3 |
| Function Name | Manifest  (subfunction of FN-EXP-02 Export job: STL, manifest, re-import, release) |
| Related Requirement IDs | Inherited from parent FN-EXP-02: FR-100; FR-102; FR-103; DATA-06; INT-04; INT-05; SAF-03; STK-04; NFR-08 |
| Architecture Component | C3/M10, C4/K09, C1/W06 · Import/Export Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Build + schema validation. |
| Input Data | Inherited from FN-EXP-02 |
| Input Data Structures | Inherited from FN-EXP-02 (Approved DS-23 + DS-20) |
| Processing Algorithm | Build + schema validation. |
| Mathematical Model | Inherited from FN-EXP-02 |
| Geometry Operations | Inherited from FN-EXP-02 |
| Output Data | Inherited from FN-EXP-02 |
| Output Data Structures | Inherited from FN-EXP-02 |
| Error Handling | Inherited from FN-EXP-02 |
| Performance Requirements | Inherited from FN-EXP-02 |
| Dependencies | Inherited from FN-EXP-02 |
| External Libraries | Inherited from FN-EXP-02 |
| Alternative Implementations | Inherited from FN-EXP-02 |
| Security Considerations | Inherited from FN-EXP-02 |
| Verification Strategy | T — verified within FN-EXP-02 test cases; evidence L0, L1, L1/L2 |
| Unit Test Requirements | UT-FN-EXP-02.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Build + schema validation. |
| Integration Test Requirements | Inherited from FN-EXP-02 |
| Open Technical Questions | Inherited from FN-EXP-02 |

##### FN-EXP-02.4 — Re-import and release

*Background job · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-EXP-02.4 |
| Function Name | Re-import and release  (subfunction of FN-EXP-02 Export job: STL, manifest, re-import, release) |
| Related Requirement IDs | Inherited from parent FN-EXP-02: FR-100; FR-102; FR-103; DATA-06; INT-04; INT-05; SAF-03; STK-04; NFR-08 |
| Architecture Component | C3/M10, C4/K09, C1/W06 · Import/Export Layer · Worker OS process (job-scoped); DB writes via completion handler transaction in C3 |
| Technical Purpose | Independent re-read; release only on pass. |
| Input Data | Inherited from FN-EXP-02 |
| Input Data Structures | Inherited from FN-EXP-02 (Approved DS-23 + DS-20) |
| Processing Algorithm | Independent re-read; release only on pass. — implemented by ALG-06 |
| Mathematical Model | ALG-06: Write: float64 → float32 rounding (round-to-nearest), facet normal = normalised (b−a)×(c−a) in float64 then cast, attribute 0, little-endian, 80-byte ASCII header with schema id and design id (no patient data). Re-read: parse with an implementation … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-06) |
| Geometry Operations | ALG-06 Binary STL writer and independent re-read comparison [manufacturing geometry] |
| Output Data | Inherited from FN-EXP-02 |
| Output Data Structures | Inherited from FN-EXP-02 |
| Error Handling | Inherited from FN-EXP-02 |
| Performance Requirements | Inherited from FN-EXP-02 — complexity: ALG-06: O(m) |
| Dependencies | Inherited from FN-EXP-02 |
| External Libraries | LIB-NUMPYSTL numpy-stl (BSD-3-Clause; CAND); module baseline |
| Alternative Implementations | ALG-06: ASCII STL (larger, decimal rounding); 3MF (post-MVP, FN-PMV-11). |
| Security Considerations | Inherited from FN-EXP-02 |
| Verification Strategy | T — verified within FN-EXP-02 test cases; evidence L0, L1, L1/L2 |
| Unit Test Requirements | UT-FN-EXP-02.4 (proposed id)<br>Isolated test of this step with positive and negative cases: Independent re-read; release only on pass.<br>ALG-06: Known triangle → known bytes; header content check. Invariants: Triangle count preserved; orientation preserved; laterality preserved (VER-03). |
| Integration Test Requirements | Inherited from FN-EXP-02 |
| Open Technical Questions | Inherited from FN-EXP-02 |

#### FN-EXP-03 — Download released export

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-EXP-03 |
| Function Name | Download released export |
| Related Requirement IDs | SEC-16; SEC-15; FR-102 |
| Architecture Component | C3/M10, C4/K09, C1/W06 · Import/Export Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Controlled, logged hand-off of released files only (SEC-16). Single-case downloads with pseudonymous names. |
| Input Data | export_id, file ∈ {stl, manifest} · Preconditions: Export released. |
| Input Data Structures | GET /exports/{id}/files/{stl\|manifest} · module baseline DS |
| Processing Algorithm | 1. Refuse unreleased → 409 EXPORT_NOT_RELEASED.<br>2. Authorise; log export.downloaded; stream. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | File. |
| Output Data Structures | Binary STL / JSON · module baseline DS |
| Error Handling | See logic.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-EXP-02; FN-AUD-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: 3MF (post-MVP) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-102; TC-SEC-15; TC-SEC-16 · suites: VER-06, VER-12, VER-13, VER-21 · evidence level L0, L1/L2 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-EXP-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Unreleased → EXPORT_NOT_RELEASED; other case → 403; names match J-xxxxxxxx_*.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-102; TC-SEC-15; TC-SEC-16 |
| Open Technical Questions | None registered |

## SS-08 — Reporting and records

### Module RPT — Reporting

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Application Layer / Data Layer |
| Runtime and execution | C4 worker (render in child process); C3 download · Background job |
| Input data structures | Stored records only |
| Output data structures | PDF blob + inputs list |
| Interfaces | IF-10; IF-04 |
| External libraries | LIB-WEASY; own rasteriser (TD-18) |
| Performance | Report time TBD |
| Security | Values read from storage only (no recomputation); no interpretive text (FR-111); download logged |
| Integration tests | Every value in PDF equals DB value; Cyrillic renders in two readers (TC-INT-06) |
| Alternatives | Headless Chromium PDF |
| Versioning | Template version stored per report |

#### FN-RPT-01 — Generate case report PDF (job)

*Background job · MVP · Should · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-RPT-01 |
| Function Name | Generate case report PDF (job) |
| Related Requirement IDs | FR-110; FR-111; INT-06; SAF-01; SAF-11; FR-082; FR-093; FR-182; NFR-08; UR-10 |
| Architecture Component | C3/M11, C4 · Application Layer · Worker job; rendering in a child process (WeasyPrint / rasteriser) |
| Technical Purpose | Russian PDF with stored values and definitions, design parameters, deviation image, validity and approval; no interpretation (FR-110, FR-111). HTML template rendered to PDF with embedded Cyrillic fonts (ADR-013 proposes WeasyPrint). |
| Input Data | case_id, selected design version (optional) · Preconditions: Case has at least one measurement set or design version. |
| Input Data Structures | POST /cases/{id}/reports → 202 · module baseline DS |
| Processing Algorithm | 1. Read stored records only (never recompute).<br>2. Sections: case header (pseudonymous ID), scan provenance, measurement values with definition per value and repeatability text, design op list with SAF-10 effect wording, deviation image (FN-RPT-02) and per-zone stats, validity results with FR-082 label, approval record (incl. self-approval statement, SAF-11 text, prescription file name/date), software build, generation time.<br>3. Footer: approved SAF-01 statement on every page.<br>4. Store PDF blob + inputs list; emit report.generated. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | PDF. |
| Output Data Structures | application/pdf (fonts embedded) · module baseline DS |
| Error Handling | Missing inputs → section shows 'not available' (no interpretation).<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-RPT-02; FN-MEA-03; FN-BLB-01 · Technical decisions: TD-18 |
| External Libraries | LIB-WEASY WeasyPrint (BSD-3-Clause (classifier: BSD License); R-MVP); module baseline |
| Alternative Implementations | Module baseline: Headless Chromium PDF |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-082; TC-FR-093; TC-FR-110; TC-FR-111; TC-FR-182; TC-INT-06; TC-SAF-01; TC-SAF-11 · suites: VER-09, VER-12, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-RPT-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Every value in the PDF equals the DB value at stored precision; definition per value; Cyrillic correct in two readers; VER-09 passes on template.<br>Job handler tests with fake kernel results: success, deterministic rejection, retryable failure, idempotent re-run. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-082; TC-FR-093; TC-FR-110; TC-FR-111; TC-FR-182; TC-INT-06; TC-SAF-01; TC-SAF-11 |
| Open Technical Questions | OQ-FS-24 |

##### FN-RPT-01.1 — Data assembly

*Background job · MVP · Should · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-RPT-01.1 |
| Function Name | Data assembly  (subfunction of FN-RPT-01 Generate case report PDF (job)) |
| Related Requirement IDs | Inherited from parent FN-RPT-01: FR-110; FR-111; INT-06; SAF-01; SAF-11; FR-082; FR-093; FR-182; NFR-08; UR-10 |
| Architecture Component | C3/M11, C4 · Application Layer · Worker job; rendering in a child process (WeasyPrint / rasteriser) |
| Technical Purpose | Stored values only. |
| Input Data | Inherited from FN-RPT-01 |
| Input Data Structures | Inherited from FN-RPT-01 (Stored records only) |
| Processing Algorithm | Stored values only. |
| Mathematical Model | Inherited from FN-RPT-01 |
| Geometry Operations | Inherited from FN-RPT-01 |
| Output Data | Inherited from FN-RPT-01 |
| Output Data Structures | Inherited from FN-RPT-01 |
| Error Handling | Inherited from FN-RPT-01 |
| Performance Requirements | Inherited from FN-RPT-01 |
| Dependencies | Inherited from FN-RPT-01 |
| External Libraries | LIB-WEASY WeasyPrint (BSD-3-Clause (classifier: BSD License); R-MVP); module baseline |
| Alternative Implementations | Inherited from FN-RPT-01 |
| Security Considerations | Inherited from FN-RPT-01 |
| Verification Strategy | T — verified within FN-RPT-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-RPT-01.1 (proposed id)<br>Isolated test of this step with positive and negative cases: Stored values only. |
| Integration Test Requirements | Inherited from FN-RPT-01 |
| Open Technical Questions | Inherited from FN-RPT-01 |

##### FN-RPT-01.2 — Template rendering

*Background job · MVP · Should · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-RPT-01.2 |
| Function Name | Template rendering  (subfunction of FN-RPT-01 Generate case report PDF (job)) |
| Related Requirement IDs | Inherited from parent FN-RPT-01: FR-110; FR-111; INT-06; SAF-01; SAF-11; FR-082; FR-093; FR-182; NFR-08; UR-10 |
| Architecture Component | C3/M11, C4 · Application Layer · Worker job; rendering in a child process (WeasyPrint / rasteriser) |
| Technical Purpose | Russian HTML template, Cyrillic fonts. |
| Input Data | Inherited from FN-RPT-01 |
| Input Data Structures | Inherited from FN-RPT-01 (Stored records only) |
| Processing Algorithm | Russian HTML template, Cyrillic fonts. |
| Mathematical Model | Inherited from FN-RPT-01 |
| Geometry Operations | Inherited from FN-RPT-01 |
| Output Data | Inherited from FN-RPT-01 |
| Output Data Structures | Inherited from FN-RPT-01 |
| Error Handling | Inherited from FN-RPT-01 |
| Performance Requirements | Inherited from FN-RPT-01 |
| Dependencies | Inherited from FN-RPT-01 |
| External Libraries | LIB-WEASY WeasyPrint (BSD-3-Clause (classifier: BSD License); R-MVP); module baseline |
| Alternative Implementations | Inherited from FN-RPT-01 |
| Security Considerations | Inherited from FN-RPT-01 |
| Verification Strategy | T — verified within FN-RPT-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-RPT-01.2 (proposed id)<br>Isolated test of this step with positive and negative cases: Russian HTML template, Cyrillic fonts. |
| Integration Test Requirements | Inherited from FN-RPT-01 |
| Open Technical Questions | Inherited from FN-RPT-01 |

##### FN-RPT-01.3 — PDF output

*Background job · MVP · Should · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-RPT-01.3 |
| Function Name | PDF output  (subfunction of FN-RPT-01 Generate case report PDF (job)) |
| Related Requirement IDs | Inherited from parent FN-RPT-01: FR-110; FR-111; INT-06; SAF-01; SAF-11; FR-082; FR-093; FR-182; NFR-08; UR-10 |
| Architecture Component | C3/M11, C4 · Application Layer · Worker job; rendering in a child process (WeasyPrint / rasteriser) |
| Technical Purpose | Blob + inputs list + audit event. |
| Input Data | Inherited from FN-RPT-01 |
| Input Data Structures | Inherited from FN-RPT-01 (Stored records only) |
| Processing Algorithm | Blob + inputs list + audit event. |
| Mathematical Model | Inherited from FN-RPT-01 |
| Geometry Operations | Inherited from FN-RPT-01 |
| Output Data | Inherited from FN-RPT-01 |
| Output Data Structures | Inherited from FN-RPT-01 |
| Error Handling | Inherited from FN-RPT-01 |
| Performance Requirements | Inherited from FN-RPT-01 |
| Dependencies | Inherited from FN-RPT-01 |
| External Libraries | LIB-WEASY WeasyPrint (BSD-3-Clause (classifier: BSD License); R-MVP); module baseline |
| Alternative Implementations | Inherited from FN-RPT-01 |
| Security Considerations | Inherited from FN-RPT-01 |
| Verification Strategy | T — verified within FN-RPT-01 test cases; evidence L0 |
| Unit Test Requirements | UT-FN-RPT-01.3 (proposed id)<br>Isolated test of this step with positive and negative cases: Blob + inputs list + audit event. |
| Integration Test Requirements | Inherited from FN-RPT-01 |
| Open Technical Questions | Inherited from FN-RPT-01 |

#### FN-RPT-02 — Render deviation image off-screen

*Background job · MVP · Should · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-RPT-02 |
| Function Name | Render deviation image off-screen |
| Related Requirement IDs | FR-110 |
| Architecture Component | C3/M11, C4 · Application Layer · Worker job; rendering in a child process (WeasyPrint / rasteriser) |
| Technical Purpose | Static image of the deviation map for the report. Server-side off-screen rendering of the LOD with the scalar field from fixed standard views. |
| Input Data | LOD + field, view list (anterior, posterior, left, right, superior) · Preconditions: Deviation artifact. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Render with the same colour map and legend as FN-UIX-04 at fixed camera poses in F_anat.<br>2. Output PNG per view; embed in report.<br>Algorithms: ALG-57 Scalar field colour mapping; ALG-60 Off-screen rendering of the deviation image |
| Mathematical Model | ALG-57: Diverging colour map symmetric about 0 with limits ±L (L = configured or max \|d\| rounded up), masked vertices neutral grey; same LUT in UI and report; legend values from stored data.<br>ALG-60: Fixed camera views (anterior, posterior, lateral L/R, superior) in F_anat; orthographic projection; per-vertex colours (ALG-57); flat/Gouraud shading; output PNG embedded in PDF. |
| Geometry Operations | ALG-57 Scalar field colour mapping [surface deviation maps (display)]; ALG-60 Off-screen rendering of the deviation image [reporting] |
| Output Data | PNG images. |
| Output Data Structures | image/png · module baseline DS |
| Error Handling | Renderer failure → report generated with 'image not available' note.<br>Policy EH-JOB (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-57: O(n); ALG-60: O(m) per view |
| Dependencies | Functions: FN-REV-01 · Technical decisions: TD-18 |
| External Libraries | LIB-VTK VTK (BSD-3-Clause; CAND); LIB-MATPLOTLIB matplotlib (Matplotlib licence (PSF-based); CAND); module baseline |
| Alternative Implementations | ALG-57: Library colormaps (matplotlib PSF-style licence).; ALG-60: matplotlib plot_trisurf (licence PSF-style; painter's algorithm artefacts). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-110 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-RPT-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Image colours match legend values at sampled pixels.<br>ALG-57: LUT endpoints. Invariants: Sign → hue mapping fixed (SAF-10).<br>ALG-60: Pixel colour at known vertex. Invariants: Legend equals UI legend. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-110 |
| Open Technical Questions | OQ-FS-24; TQ-10; TQ-23; Missing data: No architecture component is defined for server-side rendering (GAP-M09). |

#### FN-RPT-03 — Download report

*User interaction · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-RPT-03 |
| Function Name | Download report |
| Related Requirement IDs | SEC-15; SEC-16 |
| Architecture Component | C3/M11, C4 · Application Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Logged access to reports. Streams stored PDF. |
| Input Data | report_id · Preconditions: Report generated. |
| Input Data Structures | GET /reports/{id}/pdf · module baseline DS |
| Processing Algorithm | 1. Authorise; log report.downloaded; stream with J-xxxxxxxx_report_<n>.pdf. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | PDF. |
| Output Data Structures | application/pdf · module baseline DS |
| Error Handling | 403.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-RPT-01; FN-AUD-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: Headless Chromium PDF |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-SEC-15; TC-SEC-16 · suites: VER-12, VER-13, VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-RPT-03 (proposed id)<br>Acceptance criteria as unit/component assertions: One read event per download.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SEC-15; TC-SEC-16 |
| Open Technical Questions | None registered |

## SS-09 — Presentation layer (web UI and viewer)

### Module UIX — Web UI shell and viewer

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | UI Layer / — |
| Runtime and execution | C1/C2 browser (main thread + Web Worker for payload decode and BVH) · Client-side interaction |
| Input data structures | DS-14; DS-24; job status |
| Output data structures | User actions → IF-01 requests; picking hints in F_scan/F_anat mm |
| Interfaces | IF-01; IF-05 |
| External libraries | LIB-TS; LIB-THREE |
| Performance | PM-09, PM-10 (TBD) |
| Security | No secrets in client; no stored coordinate from client is trusted (server snap); Russian strings externalised; CSP headers |
| Integration tests | E2E (Playwright) UC-02…UC-10 on supported browsers (VER-11) |
| Alternatives | vtk.js viewer (ADR-006 fallback) |
| Versioning | Generated OpenAPI client version pinned to API |

#### FN-UIX-01 — Application shell, localisation and intended-use statement

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-UIX-01 |
| Function Name | Application shell, localisation and intended-use statement |
| Related Requirement IDs | UR-09; NFR-05; SAF-01; NFR-08; STK-05 |
| Architecture Component | C1/W01-W08, C2 · UI Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Russian-language UI with externalised strings and the approved intended-use statement on sign-in and about screens. Next.js shell (W01): navigation by canonical workflow steps S1–S12, ru resource files, about screen, build version. |
| Input Data | Resource files ru.json; approved SAF-01 text version · Preconditions: — |
| Input Data Structures | i18n key/value JSON · module baseline DS |
| Processing Algorithm | 1. All visible strings resolved by key; missing key fails the build (FN-OPS-01).<br>2. Sign-in and about screens show SAF-01 text verbatim with its approved version ID.<br>3. Times displayed in the clinic time zone from configuration; build version in about screen. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | UI. |
| Output Data Structures | Web pages · module baseline DS |
| Error Handling | Missing key → build failure.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CFG-04 |
| External Libraries | LIB-TS TypeScript + Next.js + React (MIT; R-MVP); module baseline |
| Alternative Implementations | Module baseline: vtk.js viewer (ADR-006 fallback) |
| Security Considerations | Module baseline |
| Verification Strategy | Method I · test cases: TC-SAF-01 · suites: VER-09 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-UIX-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Zero hard-coded UI strings; SAF-01 present in the 3 required locations (with report footer).<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SAF-01 |
| Open Technical Questions | None registered |

#### FN-UIX-02 — 3D viewer

*User interaction · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-UIX-02 |
| Function Name | 3D viewer |
| Related Requirement IDs | NFR-02; NFR-03; FR-047; SAF-03 |
| Architecture Component | C1/W01-W08, C2 · UI Layer · Browser main thread (render) + Web Worker (payload decode, BVH build) |
| Technical Purpose | Display meshes, overlays and picking hints; never a source of stored coordinates. Three.js + three-mesh-bvh (ADR-006 proposed) rendering jude-mesh/1 payloads in mm. |
| Input Data | jude-mesh/1 blobs, overlays (axes, planes, contours, landmarks, zones) · Preconditions: WebGL2-capable browser (A-17). |
| Input Data Structures | Binary payload + JSON · module baseline DS |
| Processing Algorithm | 1. Decode header JMSH; build BufferGeometry; orbit/pan/zoom.<br>2. Picking: BVH ray cast on LOD → hint_xyz_mm sent to server; result displayed from server response only.<br>3. Overlay rendering: axes with L/R labels, mid-sagittal plane, measurement plane/contour/diagonals, zone outlines.<br>Algorithms: ALG-56 Display LOD payload (jude-mesh/1) |
| Mathematical Model | ALG-56: Decimate (ALG-17) to a face budget for the client (TBD, NFR-02/03), quantise nothing (float32 positions in mm, F_anat), optional per-vertex scalar; flag display_only (INV-10). |
| Geometry Operations | ALG-56 Display LOD payload (jude-mesh/1) [interactive display] |
| Output Data | Rendered view; pick hints. |
| Output Data Structures | UI events · module baseline DS |
| Error Handling | WebGL unavailable → message with supported browser list (NFR-01).<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-56: O(m log m) |
| Dependencies | Functions: FN-KOP-04; FN-BLB-02 · Technical decisions: TD-01, TD-11, TD-17 |
| External Libraries | LIB-TS TypeScript + Next.js + React (MIT; R-MVP); LIB-MESHOPT meshoptimizer (MIT; CAND); LIB-THREE three.js + three-mesh-bvh (+ @react-three/fiber optional) (MIT; R-MVP); LIB-VTKJS vtk.js (BSD-3-Clause; RESERVE); module baseline |
| Alternative Implementations | ALG-56: glTF + Draco (metres/Y-up, extra conversion — rejected ADR-006). |
| Security Considerations | Module baseline |
| Verification Strategy | Method D · test cases: TC-FR-047; TC-SAF-03 · suites: VER-03, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-UIX-02 (proposed id)<br>Acceptance criteria as unit/component assertions: LOD of N triangles renders on min-spec client; stored coordinates always come from server responses.<br>ALG-56: Pack/unpack round-trip. Invariants: LOD never accepted as kernel input. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-047; TC-SAF-03 |
| Open Technical Questions | OQ-FS-29; TQ-13; TQ-14 |

#### FN-UIX-03 — Gate and job status presentation

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-UIX-03 |
| Function Name | Gate and job status presentation |
| Related Requirement IDs | NFR-05; FR-014; FR-032 |
| Architecture Component | C1/W01-W08, C2 · UI Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Render server gate lists and job progress so the user knows the next required step. Generic component consuming error catalogue responses (ADR-008). |
| Input Data | Problem responses, job status · Preconditions: — |
| Input Data Structures | JSON · module baseline DS |
| Processing Algorithm | 1. Show each gate code with Russian message and a link to the step that resolves it.<br>2. Poll job status (FN-JOB-03) and refresh views on completion. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | UI. |
| Output Data Structures | — · module baseline DS |
| Error Handling | —<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-API-02; FN-JOB-03 |
| External Libraries | LIB-TS TypeScript + Next.js + React (MIT; R-MVP); module baseline |
| Alternative Implementations | Module baseline: vtk.js viewer (ADR-006 fallback) |
| Security Considerations | Module baseline |
| Verification Strategy | Method I · test cases: TC-FR-014; TC-FR-032 · suites: VER-08, VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-UIX-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Each gate code has a resource string and a target step.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-014; TC-FR-032 |
| Open Technical Questions | None registered |

#### FN-UIX-04 — Scalar field colour mapping and legend

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-UIX-04 |
| Function Name | Scalar field colour mapping and legend |
| Related Requirement IDs | FR-070; SAF-10 |
| Architecture Component | C1/W01-W08, C2 · UI Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Consistent deviation colours and numeric legend in UI and report. Diverging colour map symmetric around 0 mm with SAF-10 wording. |
| Input Data | Field values, range (symmetric max \|d\|) · Preconditions: Deviation field. |
| Input Data Structures | float32[] · module baseline DS |
| Processing Algorithm | 1. Map d ∈ [−a, a] to a perceptually uniform diverging palette; values outside clamp with indicator.<br>2. Legend ticks in mm with sign wording from FN-DES-06.<br>Algorithms: ALG-57 Scalar field colour mapping |
| Mathematical Model | ALG-57: Diverging colour map symmetric about 0 with limits ±L (L = configured or max \|d\| rounded up), masked vertices neutral grey; same LUT in UI and report; legend values from stored data. |
| Geometry Operations | ALG-57 Scalar field colour mapping [surface deviation maps (display)] |
| Output Data | Colours + legend. |
| Output Data Structures | UI · module baseline DS |
| Error Handling | —<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-57: O(n) |
| Dependencies | Functions: FN-DES-06 |
| External Libraries | LIB-TS TypeScript + Next.js + React (MIT; R-MVP); LIB-THREE three.js + three-mesh-bvh (+ @react-three/fiber optional) (MIT; R-MVP); module baseline |
| Alternative Implementations | ALG-57: Library colormaps (matplotlib PSF-style licence). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-070; TC-SAF-10 · suites: VER-01, VER-14 · evidence level L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-UIX-04 (proposed id)<br>Acceptance criteria as unit/component assertions: Legend numbers equal stored values at tick positions.<br>ALG-57: LUT endpoints. Invariants: Sign → hue mapping fixed (SAF-10). |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-070; TC-SAF-10 |
| Open Technical Questions | None registered |

#### FN-UIX-05 — Region selection tools

*User interaction · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-UIX-05 |
| Function Name | Region selection tools |
| Related Requirement IDs | FR-020; FR-050; FR-179 |
| Architecture Component | C1/W01-W08, C2 · UI Layer · Browser main thread (render) + Web Worker (payload decode, BVH build) |
| Technical Purpose | Select faces for cleanup and pick centres for zones and smoothing regions. Brush/lasso/connected-component selection on the LOD mapped to full-resolution face IDs by the server. |
| Input Data | Screen-space selection, component pick · Preconditions: Viewer loaded. |
| Input Data Structures | UI · module baseline DS |
| Processing Algorithm | 1. Component pick selects a whole connected component (from integrity report).<br>2. Lasso/brush produce a selection polygon + camera; server resolves full-resolution face IDs whose centroids project inside (deterministic).<br>3. Preview highlighted before the op is added.<br>Algorithms: ALG-33 BVH closest point, anchor snap and anchor evaluation; ALG-43 Region segmentation (MVP: technician-defined regions) |
| Mathematical Model | ALG-33: AABB BVH over faces; closest point on triangle by Voronoi-region classification (Ericson) → (face_id, barycentric, feature type {face, edge, vertex}); ties (equal distance) broken by smallest face_id. Anchor evaluation x = b₀v_{f0} + b₁v_{f1} + b₂v_{f2} on … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-33)<br>ALG-43: MVP regions are explicit: (a) face sets from UI brush/lasso selection resolved on the server against full-resolution face ids; (b) disc/ellipse regions defined by an anchored centre and Euclidean radius (A-15); (c) angular sectors in F_anat (ALG-34). No … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-43) |
| Geometry Operations | ALG-33 BVH closest point, anchor snap and anchor evaluation [anatomical landmarks / geometric comparison]; ALG-43 Region segmentation (MVP: technician-defined regions) [region segmentation] |
| Output Data | Face ID set or anchor hint. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | Empty selection → no op.<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-33: Build O(m log m); query O(log m) expected [N]; ALG-43: O(selection · log m) |
| Dependencies | Functions: FN-UIX-02; FN-KAN-01 · Technical decisions: TD-02 |
| External Libraries | LIB-TS TypeScript + Next.js + React (MIT; R-MVP); LIB-THREE three.js + three-mesh-bvh (+ @react-three/fiber optional) (MIT; R-MVP); module baseline |
| Alternative Implementations | ALG-33: KD-tree on vertices only (wrong: closest vertex ≠ closest point).; ALG-43: Geodesic distance regions (potpourri3d MIT heat method, libigl exact geodesics MPL-2.0) — post-MVP. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-FR-020; TC-FR-050; TC-FR-179 · suites: VER-01, VER-08, VER-20 · evidence level L0, L1 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-UIX-05 (proposed id)<br>Acceptance criteria as unit/component assertions: Server-resolved face set equals brute-force projection test.<br>ALG-33: Point above face centre, edge, vertex regions. Invariants: Snap of an on-surface point returns itself.<br>ALG-43: Disc membership on plane. Invariants: Selection resolved on full mesh is the stored truth. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-FR-020; TC-FR-050; TC-FR-179 |
| Open Technical Questions | None registered |

#### FN-UIX-06 — Number and time formatting

*User interaction · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-UIX-06 |
| Function Name | Number and time formatting |
| Related Requirement IDs | NFR-09; NFR-08 |
| Architecture Component | C1/W01-W08, C2 · UI Layer · Browser (C1) + API request transaction (C3) |
| Technical Purpose | Display precision and time zone per configuration; stored values untouched. Formatting helpers. |
| Input Data | Values, display_decimals, time_zone · Preconditions: — |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Round half-even for display only.<br>2. UTC → clinic zone for display; ISO in exports. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Strings. |
| Output Data Structures | — · module baseline DS |
| Error Handling | —<br>Policy EH-API (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CFG-04 |
| External Libraries | LIB-TS TypeScript + Next.js + React (MIT; R-MVP); module baseline |
| Alternative Implementations | Module baseline: vtk.js viewer (ADR-006 fallback) |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-UIX-06 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-UIX-06 (proposed id)<br>Acceptance criteria as unit/component assertions: Display decimals follow config; DB stores full precision.<br>Service-layer tests with in-memory/transactional DB: each precondition/gate refusal, success path, audit event emitted, permission denial per role. |
| Integration Test Requirements | Module baseline · catalogue cases: UT-FN-UIX-06 (proposed) |
| Open Technical Questions | None registered |

## SS-10 — Quality, operations and verification tooling

### Module OPS — Quality, operations and verification tooling

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Application Layer / Security and Audit Layer; Validation Layer |
| Runtime and execution | CI runners; operator procedures; oracle container (GPL tools, never shipped) · CI job / procedure |
| Input data structures | Repository, lockfiles, fixtures, deployment |
| Output data structures | Reports, records, CI pass/fail |
| Interfaces | IF-12 |
| External libraries | LIB-TEST; LIB-CGAL (oracle); LIB-PYMESHLAB (oracle); LIB-TRIMESH (oracle) |
| Performance | CI duration budget TBD |
| Security | Oracle images isolated; secrets in CI store; vulnerability gate CVSS ≥ 7.0 (SD-04) |
| Integration tests | CI pipeline itself is tested by seeded failures (GPL package added → fail; vulnerable package → fail) |
| Alternatives | — |
| Versioning | Fixture set version; SOUP list per release |

#### FN-OPS-01 — Wording and localisation lint

*Build / CI tooling · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-OPS-01 |
| Function Name | Wording and localisation lint |
| Related Requirement IDs | VER-09; NFR-05; NFR-06; FR-045; FR-111; SEC-18; SAF-12; DATA-18 |
| Architecture Component | CI pipeline, deployment · Application Layer · CI container |
| Technical Purpose | Block merges that introduce prohibited words, severity terms, threshold constants or hard-coded strings (VER-09). CI job over UI resources, report templates, manifest text, help and user docs; exclusion file for registers quoting owner answers. |
| Input Data | Repository tree, word lists (DEC-012 words in all inflections, severity terms, 'анонимизирован'), exclusion file · Preconditions: — |
| Input Data Structures | Text files · module baseline DS |
| Processing Algorithm | 1. Russian morphological matching (lemma list per word).<br>2. Detect hard-coded JSX/TSX text nodes.<br>3. Search code for index threshold constants.<br>4. Fail on any hit outside exclusions. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | CI result. |
| Output Data Structures | Job log + JUnit · module baseline DS |
| Error Handling | Hit → merge blocked.<br>Policy EH-CI (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: none |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-18; TC-FR-045; TC-FR-111; TC-SEC-18 · suites: VER-09, VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-OPS-01 (proposed id)<br>Acceptance criteria as unit/component assertions: Seeded forbidden word or hard-coded string fails CI; clean tree passes. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-18; TC-FR-045; TC-FR-111; TC-SEC-18 |
| Open Technical Questions | None registered |

#### FN-OPS-02 — Licence allow-list and SOUP list

*Build / CI tooling · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-OPS-02 |
| Function Name | Licence allow-list and SOUP list |
| Related Requirement IDs | SEC-09 |
| Architecture Component | CI pipeline, deployment · Application Layer · CI container |
| Technical Purpose | Ship only allow-listed licences; generate SOUP list (ADR-011, 05 §4.4). Lockfile scan for Python and npm. |
| Input Data | Lockfiles · Preconditions: — |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Fail on licences outside the allow-list; GPL tools only in the oracle-test job.<br>2. Emit SOUP list (name, version, licence, supplier). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | SOUP list. |
| Output Data Structures | CSV · module baseline DS |
| Error Handling | Disallowed licence → build fails.<br>Policy EH-CI (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: none · Technical decisions: TD-23 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-SEC-09 · suites: VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-OPS-02 (proposed id)<br>Acceptance criteria as unit/component assertions: Adding a GPL package to a shipped lockfile fails CI. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SEC-09 |
| Open Technical Questions | TQ-24 |

#### FN-OPS-03 — Dependency vulnerability scan

*Build / CI tooling · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-OPS-03 |
| Function Name | Dependency vulnerability scan |
| Related Requirement IDs | SEC-09 |
| Architecture Component | CI pipeline, deployment · Application Layer · CI container |
| Technical Purpose | Block releases with unresolved CVSS ≥ 7.0 vulnerabilities (SEC-09, SD-04). Scan on every build. |
| Input Data | Lockfiles, advisory database · Preconditions: — |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Scan; any CVSS ≥ 7.0 without a recorded risk acceptance by a named approver → release job fails. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Report. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | —<br>Policy EH-CI (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-OPS-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-SEC-09 · suites: VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-OPS-03 (proposed id)<br>Acceptance criteria as unit/component assertions: Seeded vulnerable package fails the release job. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SEC-09 |
| Open Technical Questions | None registered |

#### FN-OPS-04 — Determinism regression

*Build / CI tooling · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-OPS-04 |
| Function Name | Determinism regression |
| Related Requirement IDs | VER-07; FR-052; DATA-16 |
| Architecture Component | CI pipeline, deployment · Application Layer · CI container |
| Technical Purpose | Detect any change of regenerated geometry for stored reference designs (VER-07, R-29). Nightly and pre-upgrade job. |
| Input Data | Reference design specs + expected hashes · Preconditions: 10 reference designs. |
| Input Data Structures | JSON · module baseline DS |
| Processing Algorithm | 1. Regenerate each design 100 times on the CI host; expect exactly 1 hash equal to the stored one.<br>2. Second host run recorded; difference triggers ADR-010 fallback decision. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | No own geometry computation; invokes kernel functions FN-KRP-01, FN-KRP-02 through IF-02/IF-03. |
| Output Data | Report. |
| Output Data Structures | JUnit · module baseline DS |
| Error Handling | Mismatch → build fails.<br>Policy EH-CI (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-KRP-01; FN-KRP-02 · Technical decisions: TD-19 |
| External Libraries | LIB-TEST pytest + hypothesis + Playwright + vitest (pytest MIT; hypothesis MPL-2.0; Playwright Apache-2.0; vitest MIT; DEV); module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-16; TC-FR-052 · suites: VER-07 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-OPS-04 (proposed id)<br>Acceptance criteria as unit/component assertions: 1 distinct hash per design. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-16; TC-FR-052 |
| Open Technical Questions | TQ-15; TQ-16 |

#### FN-OPS-05 — Backup and restore

*Operational procedure (software-supported) · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-OPS-05 |
| Function Name | Backup and restore |
| Related Requirement IDs | SEC-08; SEC-13; NFR-07 |
| Architecture Component | CI pipeline, deployment · Application Layer · Operator procedure supported by API/worker jobs |
| Technical Purpose | Daily backups of the database and file storage; tested restore (SEC-08, SD-03). Platform DB backup plus a separate daily file-storage backup (R-41). |
| Input Data | Schedules, backup targets · Preconditions: Deployment record exists. |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Daily DB backup (RPO 24 h); daily file-storage backup to an encrypted target.<br>2. Restore drill before pilot: restore on a clean environment; run FN-AUD-03 and FN-BLB-03 on everything; measure elapsed time ≤ 24 h.<br>3. Record result. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Backup logs; restore test record. |
| Output Data Structures | Records · module baseline DS |
| Error Handling | Missed backup → alert.<br>Policy EH-PROC (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-AUD-03; FN-BLB-03 · Technical decisions: TD-13, TD-25 |
| External Libraries | LIB-SUPA-STORAGE Supabase Storage (S3-compatible endpoint) (Service terms (Supabase client libs MIT); R-MVP); module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-SEC-08; TC-SEC-13 · suites: VER-21, VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-OPS-05 (proposed id)<br>Acceptance criteria as unit/component assertions: Backup log shows daily DB and file backups; restore test passes chain and SHA verification within 24 h. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SEC-08; TC-SEC-13 |
| Open Technical Questions | OQ-FS-08; TQ-02; TQ-03; Missing data: Whether the chosen Supabase plan backs up stored files is unverified (MA-05, R-41); worker/API hosting not decided (OQ-A1). |

#### FN-OPS-06 — Phantom and defect fixture generators

*Build / CI tooling · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-OPS-06 |
| Function Name | Phantom and defect fixture generators |
| Related Requirement IDs | VER-01; VER-03; VER-08; VER-14; VER-15 |
| Architecture Component | CI pipeline, deployment · Application Layer · CI container |
| Technical Purpose | Synthetic test objects with analytic ground truth (VER-01, -03, -08, -14, -15). Seeded generators T1–T10 of the geometry validation plan. |
| Input Data | Generator parameters + seed · Preconditions: — |
| Input Data Structures | JSON · module baseline DS |
| Processing Algorithm | 1. Icospheres R = 75 mm subdivision 6 (DEC-025), ellipsoids, asymmetric ellipsoid, open head-like surfaces, laterality object, sign sphere.<br>2. Defect catalogue with expected counts manifest.<br>3. Analytic values JSON (CI, CVA, CVAI, HC, axes, marker side). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | No own geometry computation; invokes kernel functions FN-KIO-06 through IF-02/IF-03. |
| Output Data | Fixtures. |
| Output Data Structures | STL/OBJ/PLY + JSON · module baseline DS |
| Error Handling | —<br>Policy EH-CI (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-KIO-06 |
| External Libraries | LIB-PYVISTA PyVista (MIT; DEV); module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-OPS-06 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-OPS-06 (proposed id)<br>Acceptance criteria as unit/component assertions: Reproducible by seed; analytic JSON present for every fixture. |
| Integration Test Requirements | Module baseline · catalogue cases: UT-FN-OPS-06 (proposed) |
| Open Technical Questions | None registered |

#### FN-OPS-07 — Geometry oracle tests (non-shipped)

*Build / CI tooling · MVP · Should · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-OPS-07 |
| Function Name | Geometry oracle tests (non-shipped) |
| Related Requirement IDs | VER-01; VER-08 |
| Architecture Component | CI pipeline, deployment · Application Layer · CI container; GPL oracle tools in a separate non-shipped container |
| Technical Purpose | Cross-check own kernel algorithms against independent implementations (ADR-011). Separate CI job with GPL tools (CGAL/PyMeshLab); artefacts never shipped. |
| Input Data | Fixtures · Preconditions: — |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Compare self-intersection counts, boundary loops, Hausdorff, section perimeters with oracle outputs. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | No own geometry computation; invokes kernel functions FN-KVL-05, FN-KCP-04 through IF-02/IF-03. |
| Output Data | Report. |
| Output Data Structures | JUnit · module baseline DS |
| Error Handling | —<br>Policy EH-CI (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-OPS-06; FN-KVL-05; FN-KCP-04 |
| External Libraries | LIB-TRIMESH trimesh (MIT; ORACLE); LIB-CGAL CGAL (PMP, Alpha Wrap, corefinement) (GPL-3.0+ for most algorithm packages, LGPL-3.0+ for kernel/support; commercial licence from GeometryFactory; ORACLE); LIB-PYMESHLAB PyMeshLab (GPL-3.0; ORACLE); module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-OPS-07 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-OPS-07 (proposed id)<br>Acceptance criteria as unit/component assertions: Counts equal; distances within 1e-6 mm on identical meshes. |
| Integration Test Requirements | Module baseline · catalogue cases: UT-FN-OPS-07 (proposed) |
| Open Technical Questions | TQ-21 |

#### FN-OPS-08 — End-to-end suite on supported browsers

*Build / CI tooling · MVP · Must · spec status: Blocked by open decision*

| Field | Technical specification |
|---|---|
| Function ID | FN-OPS-08 |
| Function Name | End-to-end suite on supported browsers |
| Related Requirement IDs | VER-11; NFR-01; NFR-02; NFR-03; NFR-04; UR-01; STK-01 |
| Architecture Component | CI pipeline, deployment · Application Layer · CI container |
| Technical Purpose | UC-02…UC-10 automated on every listed browser at minimum hardware (VER-11). Playwright-type E2E. |
| Input Data | Browser list, reference mesh · Preconditions: NFR-01/02 lists, N-triangle reference mesh. |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Run scripted workflow; record p95 timings for regeneration and measurement (NFR-04). |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Report. |
| Output Data Structures | JUnit + timings · module baseline DS |
| Error Handling | —<br>Policy EH-CI (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-UIX-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-OPS-08 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-OPS-08 (proposed id)<br>Acceptance criteria as unit/component assertions: 0 failed steps on every listed browser; timings recorded. |
| Integration Test Requirements | Module baseline · catalogue cases: UT-FN-OPS-08 (proposed) |
| Open Technical Questions | OQ-FS-29; TQ-13; TQ-14; Missing data: Browser list, hardware minimum, N and time budgets not set (OQ-A2, OQ-G4). |

#### FN-OPS-09 — Pilot evaluation analytics

*Operational procedure (software-supported) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-OPS-09 |
| Function Name | Pilot evaluation analytics |
| Related Requirement IDs | STK-07; STK-01; VER-10; VER-23; DATA-19; VER-04 |
| Architecture Component | CI pipeline, deployment · Application Layer · Operator procedure supported by API/worker jobs |
| Technical Purpose | Compute the two pilot measures of STK-07 (DEC-030): design time vs current process and agreement with manual measurements. Offline analysis scripts reading audit rows (DATA-19) and exported measurement values; no in-app interpretation. |
| Input Data | Audit events with ui_session_id; Jude values with definitions; manual values with method · Preconditions: Pilot cases; clinic manual measurements and current-process times provided by the clinic. |
| Input Data Structures | CSV · module baseline DS |
| Processing Algorithm | 1. Active time per step = Σ gaps between consecutive events of a UI session capped at an idle cut-off (proposed = 5 min; to be agreed).<br>2. Agreement (VER-23): per index n, bias = mean(J − M), SD of differences, 95% limits of agreement = bias ± 1.96·SD (Bland–Altman).<br>3. Report against the clinic thresholds.<br>Algorithms: ALG-59 Method agreement analysis (Bland–Altman) |
| Mathematical Model | LoA = d̄ ± 1.96·s_d.<br>ALG-59: Paired differences d = Jude − manual per infant and index; bias = mean(d); 95 % limits of agreement = bias ± 1.96·SD(d); report with n and CI of bias; thresholds set by clinic (DEC-030). |
| Geometry Operations | ALG-59 Method agreement analysis (Bland–Altman) [pilot evaluation] |
| Output Data | Pilot report. |
| Output Data Structures | CSV + PDF · module baseline DS |
| Error Handling | —<br>Policy EH-PROC (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline · complexity: ALG-59: O(n) |
| Dependencies | Functions: FN-AUD-05 |
| External Libraries | LIB-SCIPY scipy (BSD-3-Clause (classifier: BSD License); R-MVP); LIB-MATPLOTLIB matplotlib (Matplotlib licence (PSF-based); CAND); module baseline |
| Alternative Implementations | ALG-59: ICC; Deming regression. |
| Security Considerations | Module baseline |
| Verification Strategy | Method A · test cases: TC-DATA-19 · suites: VER-13 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-OPS-09 (proposed id)<br>Acceptance criteria as unit/component assertions: Report per index with n, bias, LoA, manual method and Jude definition.<br>ALG-59: Known dataset. Invariants: Output deterministic for identical input |
| Integration Test Requirements | Module baseline · catalogue cases: TC-DATA-19 |
| Open Technical Questions | TQ-23 |

#### FN-OPS-10 — Privacy inspection support (VER-22)

*Operational procedure (software-supported) · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-OPS-10 |
| Function Name | Privacy inspection support (VER-22) |
| Related Requirement IDs | VER-22; SEC-10; SEC-13; SEC-14; SEC-18; STK-06; VER-21; VER-20; VER-12; VER-13; SEC-04 |
| Architecture Component | CI pipeline, deployment · Application Layer · Operator procedure supported by API/worker jobs |
| Technical Purpose | Evidence pack for the privacy inspection before the first real scan. Generated checklist of SEC-10…14, SEC-17, SEC-18 with evidence links. |
| Input Data | Deployment record, config, test results · Preconditions: Deployment record. |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Generate checklist with evidence references; privacy specialist signs; record ID used by FN-CFG-08. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Inspection record. |
| Output Data Structures | PDF/Markdown · module baseline DS |
| Error Handling | Any fail keeps real_patient_data_enabled false.<br>Policy EH-PROC (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-CFG-08 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method I · test cases: TC-SEC-04; TC-SEC-10; TC-SEC-13; TC-SEC-14; TC-SEC-18 · suites: VER-12, VER-22 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-OPS-10 (proposed id)<br>Acceptance criteria as unit/component assertions: Signed record lists each control with evidence. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SEC-04; TC-SEC-10; TC-SEC-13; TC-SEC-14; TC-SEC-18 |
| Open Technical Questions | None registered |

#### FN-OPS-11 — Physical verification records (VER-02, VER-16, VER-06 Neo)

*Operational procedure (software-supported) · MVP · Must · spec status: Ready with open items (non-blocking)*

| Field | Technical specification |
|---|---|
| Function ID | FN-OPS-11 |
| Function Name | Physical verification records (VER-02, VER-16, VER-06 Neo) |
| Related Requirement IDs | VER-02; VER-16; VER-06; INT-04; VER-04; STK-04; STK-03 |
| Architecture Component | CI pipeline, deployment · Application Layer · Operator procedure supported by API/worker jobs |
| Technical Purpose | Record pilot-entry physical checks with clinic-owned limits (DEC-029). Forms to store results; values confidential to the clinic. |
| Input Data | Measured values, limits reference, Neo version · Preconditions: Clinic access (OQ-B4), physical phantom, produced positive. |
| Input Data Structures | Form · module baseline DS |
| Processing Algorithm | 1. Store pass/fail with clinic signature; limits themselves are not stored in project documents. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Records. |
| Output Data Structures | Records · module baseline DS |
| Error Handling | —<br>Policy EH-PROC (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-EXP-02; FN-MEA-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method A · test cases: TC-INT-04 · suites: VER-06 · evidence level L1/L2 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-OPS-11 (proposed id)<br>Acceptance criteria as unit/component assertions: Records exist before pilot. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-INT-04 |
| Open Technical Questions | OQ-FS-32 |

#### FN-OPS-12 — Security test suite and threat model review

*Build / CI tooling · MVP · Must · spec status: Ready*

| Field | Technical specification |
|---|---|
| Function ID | FN-OPS-12 |
| Function Name | Security test suite and threat model review |
| Related Requirement IDs | VER-21; SEC-07; VER-13; VER-12; VER-20 |
| Architecture Component | CI pipeline, deployment · Application Layer · CI container |
| Technical Purpose | Verify SEC-05…09, 15, 16, 19, 20 on the pilot configuration (VER-21). Automated tests + threat model mapping. |
| Input Data | Deployment · Preconditions: Pilot configuration. |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Run suite; map each threat to a passing test or recorded acceptance. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Report. |
| Output Data Structures | JUnit · module baseline DS |
| Error Handling | —<br>Policy EH-CI (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Module baseline (no geometric computation; request/transaction latency per PM table) |
| Dependencies | Functions: FN-IAM-01; FN-IAM-02; FN-AUD-02; FN-OPS-05 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: — |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-SEC-07 · suites: VER-21 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | UT-FN-OPS-12 (proposed id)<br>Acceptance criteria as unit/component assertions: All listed SEC criteria pass. |
| Integration Test Requirements | Module baseline · catalogue cases: TC-SEC-07 |
| Open Technical Questions | None registered |

## SS-11 — Post-MVP and research-only capabilities (outline)

### Module PMV — Post-MVP and research-only

Module baseline (applies to every function below where a field says "module baseline"):

| Baseline field | Value |
|---|---|
| Primary / secondary layer | Domain Layer / Geometry Engine (future) |
| Runtime and execution | Future (outline) · Outline — not for MVP implementation |
| Input data structures | — |
| Output data structures | — |
| Interfaces | — |
| External libraries | See ALGORITHM_CATALOG and LIBRARY_COMPARISON (RESERVE items) |
| Performance | Not specified (outline) |
| Security | Re-assess with privacy specialist before scoping (R-08, R-30) |
| Integration tests | Not specified (outline) |
| Alternatives | See ALG entries |
| Versioning | — |

#### FN-PMV-01 — Follow-up encounters and multi-device episodes

*Outline (post-MVP / research-only) · post-MVP · Should · spec status: Outline only (not for MVP implementation)*

| Field | Technical specification |
|---|---|
| Function ID | FN-PMV-01 |
| Function Name | Follow-up encounters and multi-device episodes |
| Related Requirement IDs | FR-150; FR-154; FR-155; DATA-12; UR-11 |
| Architecture Component | Future · Domain Layer · Future (outline) |
| Technical Purpose | Record visits, observations and several devices per episode. Encounter entity with date, optional scan, flags and wear time with source. |
| Input Data | Encounter fields (DATA-12) · Preconditions: MVP complete. |
| Input Data Structures | JSON · module baseline DS |
| Processing Algorithm | 1. Outline only; specify in FS v1.1 when scheduled. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Encounters. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | —<br>Policy EH-OUT (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Not specified (outline function). |
| Dependencies | Functions: FN-CAS-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: See ALG entries |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-PMV-01 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | Not specified (outline). |
| Integration Test Requirements | Not specified (outline). |
| Open Technical Questions | None registered |

#### FN-PMV-02 — Scan-to-scan registration and overlays

*Outline (post-MVP / research-only) · post-MVP · Could · spec status: Outline only (not for MVP implementation)*

| Field | Technical specification |
|---|---|
| Function ID | FN-PMV-02 |
| Function Name | Scan-to-scan registration and overlays |
| Related Requirement IDs | FR-151; FR-176; SAF-12 |
| Architecture Component | Future · Domain Layer · Future (outline) |
| Technical Purpose | Compare visits or a new scan with an approved positive in a shared frame. Landmark initialisation (Kabsch) + point-to-plane ICP; signed-distance map; geometric wording only. |
| Input Data | Two scans or scan + positive · Preconditions: FN-PMV-01. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Outline: Kabsch on common landmarks → ICP point-to-plane → FN-KCP-01.<br>Algorithms: ALG-44 Scan-to-scan rigid registration (Kabsch/Umeyama + ICP) |
| Mathematical Model | Kabsch: R = V diag(1,1,det(VUᵀ)) Uᵀ from SVD of the cross-covariance (det = +1 enforced).<br>ALG-44: Initial alignment from corresponding landmarks by Kabsch (SVD of cross-covariance, det fix); refinement by point-to-plane ICP restricted to stable regions; reflection guard. |
| Geometry Operations | ALG-44 Scan-to-scan rigid registration (Kabsch/Umeyama + ICP) [geometric comparison (follow-up)] |
| Output Data | Deviation map. |
| Output Data Structures | Artifact · module baseline DS |
| Error Handling | —<br>Policy EH-OUT (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Not specified (outline function). |
| Dependencies | Functions: FN-KCP-01; FN-KFR-03 |
| External Libraries | LIB-OPEN3D Open3D (MIT; CAND); module baseline |
| Alternative Implementations | ALG-44: Frame-to-frame alignment only (MVP-compatible). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-PMV-02 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | Not specified (outline). |
| Integration Test Requirements | Not specified (outline). |
| Open Technical Questions | None registered |

#### FN-PMV-03 — Trend table, definition warning, repeatability band

*Outline (post-MVP / research-only) · post-MVP · Should · spec status: Outline only (not for MVP implementation)*

| Field | Technical specification |
|---|---|
| Function ID | FN-PMV-03 |
| Function Name | Trend table, definition warning, repeatability band |
| Related Requirement IDs | FR-152; FR-153; VER-05 |
| Architecture Component | Future · Domain Layer · Future (outline) |
| Technical Purpose | Tabulate index values per visit without interpretation. Warn on definition/modality change; band from VER-05. |
| Input Data | Value records · Preconditions: FN-PMV-01; VER-05. |
| Input Data Structures | JSON · module baseline DS |
| Processing Algorithm | 1. Outline. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Table. |
| Output Data Structures | UI · module baseline DS |
| Error Handling | —<br>Policy EH-OUT (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Not specified (outline function). |
| Dependencies | Functions: FN-PMV-01; FN-MEA-03 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: See ALG entries |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-PMV-03 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | Not specified (outline). |
| Integration Test Requirements | Not specified (outline). |
| Open Technical Questions | None registered |

#### FN-PMV-04 — Mirrored reference overlay

*Outline (post-MVP / research-only) · post-MVP · Could · spec status: Outline only (not for MVP implementation)*

| Field | Technical specification |
|---|---|
| Function ID | FN-PMV-04 |
| Function Name | Mirrored reference overlay |
| Related Requirement IDs | FR-160 |
| Architecture Component | Future · Domain Layer · Future (outline) |
| Technical Purpose | Visual mirror of one side across the mid-sagittal plane; never applied to the design. Reflection used only for display (exempt from det guard because never stored as a design transform). |
| Input Data | Scan, MSP · Preconditions: Frame confirmed. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Outline.<br>Algorithms: ALG-42 Symmetry analysis (mirrored reference across mid-sagittal plane) |
| Mathematical Model | ALG-42: Reflect the scan across the mid-sagittal plane of F_anat (x_ML → −x_ML; a reflection used only for display, never for design or export — reflection guard does not apply to this display transform, which is tagged display_only); signed distance between … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-42) |
| Geometry Operations | ALG-42 Symmetry analysis (mirrored reference across mid-sagittal plane) [symmetry analysis] |
| Output Data | Overlay. |
| Output Data Structures | Display LOD · module baseline DS |
| Error Handling | —<br>Policy EH-OUT (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Not specified (outline function). |
| Dependencies | Functions: FN-KFR-02 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-42: Symmetry plane by optimisation (ICP of mirrored copy) — research. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-PMV-04 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | Not specified (outline). |
| Integration Test Requirements | Not specified (outline). |
| Open Technical Questions | None registered |

#### FN-PMV-05 — Trim/marking curve and clearance checklist

*Outline (post-MVP / research-only) · post-MVP · Could · spec status: Outline only (not for MVP implementation)*

| Field | Technical specification |
|---|---|
| Function ID | FN-PMV-05 |
| Function Name | Trim/marking curve and clearance checklist |
| Related Requirement IDs | FR-161 |
| Architecture Component | Future · Domain Layer · Future (outline) |
| Technical Purpose | Draw an extent curve on the positive and complete a clearance checklist. Geodesic polyline on surface (05 GEO-OP-20). |
| Input Data | Curve points · Preconditions: Design. |
| Input Data Structures | Anchors · module baseline DS |
| Processing Algorithm | 1. Outline.<br>Algorithms: ALG-51 Edge treatment: trim/marking curve and clearance band |
| Mathematical Model | ALG-51: Polyline drawn as anchors on the positive, connected by surface paths (geodesic via heat method or exact geodesics), exported as metadata (manifest) — the physical trim and edge rounding happen in production (thermoforming on a positive); shell edge … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-51) |
| Geometry Operations | ALG-51 Edge treatment: trim/marking curve and clearance band [edge treatment] |
| Output Data | Curve in manifest. |
| Output Data Structures | JSON · module baseline DS |
| Error Handling | —<br>Policy EH-OUT (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Not specified (outline function). |
| Dependencies | Functions: FN-KAN-01; FN-KEX-01 |
| External Libraries | LIB-LIBIGL libigl (Python bindings "libigl") (MPL-2.0 (core); include/igl/copyleft/* under GPL/AGPL of wrapped libraries; CAND); LIB-POTPOURRI potpourri3d (MIT; RESERVE); module baseline |
| Alternative Implementations | ALG-51: Straight segments projected onto surface. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-PMV-05 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | Not specified (outline). |
| Integration Test Requirements | Not specified (outline). |
| Open Technical Questions | None registered |

#### FN-PMV-06 — Helmet shell generation and wall-thickness analysis

*Outline (post-MVP / research-only) · post-MVP · Won't (this release) · spec status: Outline only (not for MVP implementation)*

| Field | Technical specification |
|---|---|
| Function ID | FN-PMV-06 |
| Function Name | Helmet shell generation and wall-thickness analysis |
| Related Requirement IDs | FR-162 |
| Architecture Component | Future · Domain Layer · Future (outline) |
| Technical Purpose | Generate the helmet shell by offsetting the inner surface and report minimum wall thickness (deferred by DEC-011). SDF-based offset (Manifold level set) + trim + side band; thickness by ray casting or SDF sampling (05 §2.3–2.4). |
| Input Data | Positive, thickness (technician) · Preconditions: DEC-011 reopened. |
| Input Data Structures | Arrays · module baseline DS |
| Processing Algorithm | 1. Outline (see assessment §A15).<br>Algorithms: ALG-27 Shell generation by SDF offset and iso-surface extraction; ALG-28 Mesh Boolean operations (union, difference, intersection); ALG-29 Wall thickness analysis |
| Mathematical Model | Outer = {x : SDF_inner(x) = t}; thickness(p) = distance along n̂_p to the outer surface.<br>ALG-27: Inner surface = approved positive (or offset of it). Outer surface = level set {x : sd(x) = t} of the signed distance to the inner surface, extracted by marching cubes (or dual contouring) on a grid of spacing h, or by Manifold's level-set API. Shell = … (full model: CAD_GEOMETRY_ENGINE_DESIGN, ALG-27)<br>ALG-28: Manifold library: exact-topology Boolean on manifold triangle meshes with guaranteed manifold output (symbolic perturbation) [P G-SRC-11].<br>ALG-29: Per outer-surface point: distance along inward normal ray to the inner surface (ray casting, Möller–Trumbore) or unsigned distance to the opposite surface (BVH closest point); shape-diameter function as alternative. |
| Geometry Operations | ALG-27 Shell generation by SDF offset and iso-surface extraction [shell generation / inner and outer surfaces / wall thickness]; ALG-28 Mesh Boolean operations (union, difference, intersection) [Boolean union / difference / intersection]; ALG-29 Wall thickness analysis [thickness analysis / wall thickness] |
| Output Data | Shell solid + thickness map. |
| Output Data Structures | Arrays · module baseline DS |
| Error Handling | —<br>Policy EH-OUT (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Not specified (outline function). |
| Dependencies | Functions: FN-KOP-06; FN-KVL-07 |
| External Libraries | LIB-MANIFOLD manifold3d (Manifold) (Apache-2.0; RESERVE); LIB-MESHLIB MeshLib SDK (LicenseRef-MeshLib: free for non-commercial/educational use; commercial licence required for business use; REJECT); LIB-EMBREE Intel Embree (Python: embreex) (Apache-2.0 (Embree); embreex wrapper BSD-style (copyright notice in PyPI metadata — verify); CAND); LIB-SKIMAGE scikit-image (BSD-3-Clause (classifier); RESERVE); module baseline |
| Alternative Implementations | ALG-27: Vertex-normal offset (folds); OCCT thick solid (needs B-Rep).; ALG-28: OCCT B-Rep Booleans (LGPL+exception; mesh→B-Rep conversion heavy); MeshLib (commercial).; ALG-29: SDF-based thickness. |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-PMV-06 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | Not specified (outline). |
| Integration Test Requirements | Not specified (outline). |
| Open Technical Questions | OQ-FS-33 |

#### FN-PMV-07 — Read-only shared review

*Outline (post-MVP / research-only) · post-MVP · Won't (this release) · spec status: Outline only (not for MVP implementation)*

| Field | Technical specification |
|---|---|
| Function ID | FN-PMV-07 |
| Function Name | Read-only shared review |
| Related Requirement IDs | FR-163 |
| Architecture Component | Future · Domain Layer · Future (outline) |
| Technical Purpose | Share a read-only case view with an invited reviewer. Needs privacy rules for external access. |
| Input Data | Invite · Preconditions: Privacy decision. |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Outline. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Access grant. |
| Output Data Structures | — · module baseline DS |
| Error Handling | —<br>Policy EH-OUT (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Not specified (outline function). |
| Dependencies | Functions: FN-IAM-04 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: See ALG entries |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-PMV-07 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | Not specified (outline). |
| Integration Test Requirements | Not specified (outline). |
| Open Technical Questions | None registered |

#### FN-PMV-08 — Protected regions

*Outline (post-MVP / research-only) · post-MVP · Could · spec status: Outline only (not for MVP implementation)*

| Field | Technical specification |
|---|---|
| Function ID | FN-PMV-08 |
| Function Name | Protected regions |
| Related Requirement IDs | FR-174 |
| Architecture Component | Future · Domain Layer · Future (outline) |
| Technical Purpose | Clinic-configured regions where zones are refused or need confirmation. Region masks in F_anat. |
| Input Data | Region definitions · Preconditions: Configuration. |
| Input Data Structures | JSON · module baseline DS |
| Processing Algorithm | 1. Outline. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | No own geometry computation; invokes kernel functions FN-KOP-11 through IF-02/IF-03. |
| Output Data | Gate result. |
| Output Data Structures | — · module baseline DS |
| Error Handling | —<br>Policy EH-OUT (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Not specified (outline function). |
| Dependencies | Functions: FN-KOP-11 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: See ALG entries |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-PMV-08 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | Not specified (outline). |
| Integration Test Requirements | Not specified (outline). |
| Open Technical Questions | None registered |

#### FN-PMV-09 — Dataset snapshot export

*Outline (post-MVP / research-only) · post-MVP · Should · spec status: Outline only (not for MVP implementation)*

| Field | Technical specification |
|---|---|
| Function ID | FN-PMV-09 |
| Function Name | Dataset snapshot export |
| Related Requirement IDs | DATA-20 |
| Architecture Component | Future · Domain Layer · Future (outline) |
| Technical Purpose | Pseudonymised, versioned dataset snapshots for research role. Respects DATA-14 permissions. |
| Input Data | Permission level · Preconditions: AI roadmap stage R1. |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Outline. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | Snapshot. |
| Output Data Structures | Archive · module baseline DS |
| Error Handling | —<br>Policy EH-OUT (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Not specified (outline function). |
| Dependencies | Functions: FN-CAS-05 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: See ALG entries |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-PMV-09 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | Not specified (outline). |
| Integration Test Requirements | Not specified (outline). |
| Open Technical Questions | None registered |

#### FN-PMV-10 — AI suggestion framework

*Outline (post-MVP / research-only) · research-only · Won't (this release) · spec status: Outline only (not for MVP implementation)*

| Field | Technical specification |
|---|---|
| Function ID | FN-PMV-10 |
| Function Name | AI suggestion framework |
| Related Requirement IDs | AI-01; AI-02; AI-03; AI-04; AI-05; AI-06; AI-07; AI-08; AI-09; DATA-21 |
| Architecture Component | Future · Domain Layer · Future (outline) |
| Technical Purpose | Suggestion records, shadow mode, model registry, kill switch, pre-registered evaluation (ADR-015). No MVP code path except reserved enums/events. |
| Input Data | — · Preconditions: AI roadmap gates R0–R4. |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Outline. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | — |
| Output Data Structures | — · module baseline DS |
| Error Handling | —<br>Policy EH-OUT (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Not specified (outline function). |
| Dependencies | Functions: FN-AUD-01 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: See ALG entries |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: TC-DATA-21 · suites: VER-20 · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | Not specified (outline). |
| Integration Test Requirements | Not specified (outline). |
| Open Technical Questions | None registered |

#### FN-PMV-11 — 3MF export

*Outline (post-MVP / research-only) · post-MVP · Could · spec status: Outline only (not for MVP implementation)*

| Field | Technical specification |
|---|---|
| Function ID | FN-PMV-11 |
| Function Name | 3MF export |
| Related Requirement IDs | None — no approved requirement (gap registered: GAP-M05/M06/M15, OQ-FS-33) |
| Architecture Component | Future · Domain Layer · Future (outline) |
| Technical Purpose | Export with units and metadata inside the file (05 §5.2). Not in RTM (GAP-M15); depends on OQ-G2. |
| Input Data | Approved geometry · Preconditions: Requirement approved. |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Outline. |
| Mathematical Model | No geometric or numerical model: deterministic state, validation and persistence logic as stated in Processing Algorithm. |
| Geometry Operations | None (no geometry is computed or modified by this function). |
| Output Data | 3MF. |
| Output Data Structures | 3MF · module baseline DS |
| Error Handling | —<br>Policy EH-OUT (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Not specified (outline function). |
| Dependencies | Functions: FN-EXP-02 |
| External Libraries | module baseline |
| Alternative Implementations | Module baseline: See ALG entries |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-PMV-11 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | Not specified (outline). |
| Integration Test Requirements | Not specified (outline). |
| Open Technical Questions | OQ-FS-33 |

#### FN-PMV-12 — Scan denoising, surface reconstruction and remeshing

*Outline (post-MVP / research-only) · research-only · Could · spec status: Outline only (not for MVP implementation)*

| Field | Technical specification |
|---|---|
| Function ID | FN-PMV-12 |
| Function Name | Scan denoising, surface reconstruction and remeshing |
| Related Requirement IDs | None — no approved requirement (gap registered: GAP-M05/M06/M15, OQ-FS-33) |
| Architecture Component | Future · Domain Layer · Future (outline) |
| Technical Purpose | Requested in the FS brief (Phase 3); no approved requirement exists; heavy cleanup stays in Artec Studio (ODC-04). Candidates: bilateral normal filtering, screened Poisson reconstruction, isotropic remeshing (assessment §A13–A14). |
| Input Data | Scan · Preconditions: Requirement approved. |
| Input Data Structures | — · module baseline DS |
| Processing Algorithm | 1. Outline only.<br>Algorithms: ALG-19 Mesh denoising (feature-preserving); ALG-20 Isotropic remeshing; ALG-21 Surface / solid reconstruction (screened Poisson, alpha wrapping); ALG-45 Discrete curvature estimation |
| Mathematical Model | ALG-19: Bilateral normal filtering (Zheng et al. 2011): filter face normals with spatial and range kernels, then update vertices to fit filtered normals.<br>ALG-20: Botsch–Kobbelt: iterate split long edges (> 4/3 L), collapse short (< 4/5 L), flip to valence 6, tangential relaxation, project to input.<br>ALG-21: Screened Poisson: solve ∇²χ = ∇·V with screening to fit an indicator function, extract iso-surface. Alpha wrap: shrink-wrap an offset envelope guaranteed watertight and manifold. |
| Geometry Operations | ALG-19 Mesh denoising (feature-preserving) [mesh denoising]; ALG-20 Isotropic remeshing [remeshing]; ALG-21 Surface / solid reconstruction (screened Poisson, alpha wrapping) [surface reconstruction / solid reconstruction]; ALG-45 Discrete curvature estimation [cranial surface analysis] |
| Output Data | — |
| Output Data Structures | — · module baseline DS |
| Error Handling | —<br>Policy EH-OUT (TECHNICAL_DESIGN §5.1). |
| Performance Requirements | Not specified (outline function). |
| Dependencies | Functions: FN-KVL-07 |
| External Libraries | module baseline |
| Alternative Implementations | ALG-19: Artec Studio processing before export (current baseline, ODC-04).; ALG-20: Keep scan topology (MVP).; ALG-21: Positive closure ALG-24 (MVP). |
| Security Considerations | Module baseline |
| Verification Strategy | Method T · test cases: UT-FN-PMV-12 (proposed) · suites: proposed UT only · evidence level L0 (geometric/software only; no clinical claim) |
| Unit Test Requirements | Not specified (outline). |
| Integration Test Requirements | Not specified (outline). |
| Open Technical Questions | OQ-FS-33 |
