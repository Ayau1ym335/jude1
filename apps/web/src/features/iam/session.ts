// FN-IAM-01 sign-in on the client (TSK-IAM-01-U; SEC-01, SEC-05, SEC-20, TD-14, TD-26).
//
// - The session token travels only in the httpOnly cookie the API sets; the browser code never
//   sees it. The CSRF token comes in the login body and must accompany every state change
//   (X-CSRF-Token, SEC-20).
// - The CSRF token is kept in sessionStorage, so it survives a reload and dies with the tab. The
//   API has no endpoint that re-issues it, and a script running in the page could read it from
//   memory just as well, so this adds no exposure. Never localStorage, never a cookie readable
//   by scripts.
// - The password is passed straight to the request body and never stored or logged.
// - Refusals come back as the DS-24 envelope. The UI shows the API's Russian message
//   (`message_ru`, NFR-05) and never builds its own wording from the code.
import type { ErrorResponse, JudeClient, components } from "@jude/contracts";

export type SessionUser = components["schemas"]["SessionUser"];

export type LoginResult =
  | { ok: true; user: SessionUser }
  | { ok: false; code: string; message: string; lockedUntil: string | null }
  | { ok: false; code: "UNAVAILABLE"; message: null; lockedUntil: null };

const CSRF_KEY = "jude.csrf";

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null; // storage blocked: the session still works until the tab reloads
  }
}

let memoryToken: string | null = null;

export function csrfToken(): string | null {
  return memoryToken ?? storage()?.getItem(CSRF_KEY) ?? null;
}

export function rememberCsrfToken(token: string): void {
  memoryToken = token;
  storage()?.setItem(CSRF_KEY, token);
}

export function forgetSession(): void {
  memoryToken = null;
  storage()?.removeItem(CSRF_KEY);
}

function refusal(error: ErrorResponse): LoginResult {
  const locked = error.gates.find((g) => g.code === "ACCOUNT_LOCKED");
  return {
    ok: false,
    code: error.error,
    message: error.message_ru,
    lockedUntil: locked?.detail ?? null,
  };
}

export async function login(
  client: JudeClient,
  credentials: { login: string; password: string },
): Promise<LoginResult> {
  try {
    const { data, error } = await client.POST("/api/v1/auth/login", { body: credentials });
    if (data) {
      rememberCsrfToken(data.csrf_token);
      return { ok: true, user: data.user };
    }
    if (error && typeof error === "object" && "error" in error) {
      return refusal(error as ErrorResponse);
    }
  } catch {
    // network failure or a non-JSON answer from a proxy
  }
  return { ok: false, code: "UNAVAILABLE", message: null, lockedUntil: null };
}
