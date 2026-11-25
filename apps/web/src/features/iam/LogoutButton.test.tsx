// CT-FN-IAM-03: sign-out button against the real typed client with a stubbed fetch.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createJudeClient } from "@jude/contracts";

import { t } from "../../i18n";
import { LogoutButton } from "./LogoutButton";
import { csrfToken, forgetSession, rememberCsrfToken } from "./session";

function setup(answer: () => Promise<Response>) {
  const fetchMock = vi.fn((_request: Request) => answer());
  vi.stubGlobal("fetch", fetchMock);
  const onLoggedOut = vi.fn();
  render(<LogoutButton client={createJudeClient("http://jude.test")} onLoggedOut={onLoggedOut} />);
  return { fetchMock, onLoggedOut, user: userEvent.setup() };
}

function refusal(status: number, error: string, message: string): Response {
  return new Response(
    JSON.stringify({
      error,
      http_status: status,
      message_ru: message,
      gates: [],
      correlation_id: "c",
    }),
    { status, headers: { "Content-Type": "application/json" } },
  );
}

beforeEach(() => {
  forgetSession();
  window.sessionStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LogoutButton", () => {
  it("sends the CSRF token, forgets the session and reports the sign-out", async () => {
    rememberCsrfToken("csrf-abc");
    const { fetchMock, onLoggedOut, user } = setup(async () => new Response(null, { status: 204 }));
    await user.click(screen.getByRole("button", { name: t("logout.submit") }));
    await waitFor(() => expect(onLoggedOut).toHaveBeenCalledTimes(1));
    const request = fetchMock.mock.calls[0]![0];
    expect(request.method).toBe("POST");
    expect(new URL(request.url).pathname).toBe("/api/v1/auth/logout");
    expect(request.headers.get("X-CSRF-Token")).toBe("csrf-abc");
    expect(request.headers.get("X-Correlation-ID")).toMatch(/^[0-9a-f]{32}$/);
    expect(csrfToken()).toBeNull();
    expect(window.sessionStorage.getItem("jude.csrf")).toBeNull();
  });

  it("treats an already ended session as signed out (the API is idempotent)", async () => {
    const { fetchMock, onLoggedOut, user } = setup(async () => new Response(null, { status: 204 }));
    await user.click(screen.getByRole("button", { name: t("logout.submit") }));
    await waitFor(() => expect(onLoggedOut).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]![0].headers.get("X-CSRF-Token")).toBeNull();
  });

  it("keeps the session and says why when the API refuses", async () => {
    rememberCsrfToken("stale");
    const message = "Сессия формы устарела. Обновите страницу и повторите.";
    const { onLoggedOut, user } = setup(async () => refusal(403, "CSRF_INVALID", message));
    await user.click(screen.getByRole("button", { name: t("logout.submit") }));
    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(onLoggedOut).not.toHaveBeenCalled();
    expect(csrfToken()).toBe("stale"); // the server session is still live
  });

  it("keeps the session when the server is unreachable", async () => {
    rememberCsrfToken("csrf-abc");
    const { onLoggedOut, user } = setup(async () => {
      throw new TypeError("network down");
    });
    await user.click(screen.getByRole("button", { name: t("logout.submit") }));
    expect((await screen.findByRole("alert")).textContent).toBe(t("login.unavailable"));
    expect(onLoggedOut).not.toHaveBeenCalled();
    expect(csrfToken()).toBe("csrf-abc");
  });

  it("sends one request while busy", async () => {
    let release: (r: Response) => void = () => undefined;
    const { fetchMock, onLoggedOut, user } = setup(
      () => new Promise<Response>((resolve) => (release = resolve)),
    );
    await user.click(screen.getByRole("button", { name: t("logout.submit") }));
    const busy = screen.getByRole("button", { name: t("logout.submitting") }) as HTMLButtonElement;
    expect(busy.disabled).toBe(true);
    await user.click(busy);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    release(new Response(null, { status: 204 }));
    await waitFor(() => expect(onLoggedOut).toHaveBeenCalledTimes(1));
  });
});
