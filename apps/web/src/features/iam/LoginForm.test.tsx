// CT-FN-IAM-01: sign-in form against the real typed client with a stubbed fetch.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createJudeClient } from "@jude/contracts";

import { t } from "../../i18n";
import { LoginForm } from "./LoginForm";
import { csrfToken, forgetSession } from "./session";

const USER = {
  id: "00000000-0000-4000-8000-000000000001",
  display_name: "Test",
  role: "technician",
};

function reply(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function refusal(status: number, error: string, message: string, gates: unknown[] = []) {
  return reply(status, {
    error,
    http_status: status,
    message_ru: message,
    gates,
    correlation_id: "c",
  });
}

function setup(answer: () => Promise<Response>) {
  const fetchMock = vi.fn((_request: Request) => answer());
  vi.stubGlobal("fetch", fetchMock);
  const onLoggedIn = vi.fn();
  render(<LoginForm client={createJudeClient("http://jude.test")} onLoggedIn={onLoggedIn} />);
  return { fetchMock, onLoggedIn, user: userEvent.setup() };
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, password = "secret pass 1") {
  await user.type(screen.getByLabelText(t("login.login")), "tech1");
  await user.type(screen.getByLabelText(t("login.password")), password);
  await user.click(screen.getByRole("button", { name: t("login.submit") }));
}

beforeEach(() => {
  forgetSession();
  window.sessionStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LoginForm", () => {
  it("signs in, keeps the CSRF token and reports the user", async () => {
    const { fetchMock, onLoggedIn, user } = setup(async () =>
      reply(200, { csrf_token: "csrf-123", user: USER }),
    );
    await fillAndSubmit(user);
    await waitFor(() => expect(onLoggedIn).toHaveBeenCalledWith(USER));
    expect(csrfToken()).toBe("csrf-123");
    expect(window.sessionStorage.getItem("jude.csrf")).toBe("csrf-123");

    const request = fetchMock.mock.calls[0]![0];
    expect(request.method).toBe("POST");
    expect(new URL(request.url).pathname).toBe("/api/v1/auth/login");
    expect(await request.json()).toEqual({ login: "tech1", password: "secret pass 1" });
    expect(request.headers.get("X-Correlation-ID")).toMatch(/^[0-9a-f]{32}$/);
  });

  it("shows the API's Russian message on wrong credentials and clears the password", async () => {
    const { onLoggedIn, user } = setup(async () =>
      refusal(401, "BAD_CREDENTIALS", "Неверный логин или пароль."),
    );
    await fillAndSubmit(user);
    expect((await screen.findByRole("alert")).textContent).toContain("Неверный логин или пароль.");
    expect((screen.getByLabelText(t("login.password")) as HTMLInputElement).value).toBe("");
    expect(onLoggedIn).not.toHaveBeenCalled();
    expect(csrfToken()).toBeNull();
  });

  it("shows the unlock time of a locked account", async () => {
    const until = "2026-11-25T10:15:00+00:00";
    const { user } = setup(async () =>
      refusal(423, "ACCOUNT_LOCKED", "Учётная запись временно заблокирована.", [
        { code: "ACCOUNT_LOCKED", detail: until },
      ]),
    );
    await fillAndSubmit(user);
    const expected = new Intl.DateTimeFormat("ru-RU", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(until));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Учётная запись временно заблокирована.");
    expect(alert.textContent).toContain(`${t("login.lockedUntil")} ${expected}`);
  });

  it("reports an unreachable server without inventing an error code", async () => {
    const { user } = setup(async () => {
      throw new TypeError("network down");
    });
    await fillAndSubmit(user);
    expect((await screen.findByRole("alert")).textContent).toContain(t("login.unavailable"));
  });

  it("treats a non-JSON proxy error as unreachable", async () => {
    const { user } = setup(async () => new Response("<html>502</html>", { status: 502 }));
    await fillAndSubmit(user);
    expect((await screen.findByRole("alert")).textContent).toContain(t("login.unavailable"));
  });

  it("cannot be submitted empty and masks the password", async () => {
    const { fetchMock, user } = setup(async () => reply(200, {}));
    const button = screen.getByRole("button", { name: t("login.submit") }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    await user.type(screen.getByLabelText(t("login.login")), "   ");
    expect(button.disabled).toBe(true);
    expect(screen.getByLabelText(t("login.password")).getAttribute("type")).toBe("password");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends one request per submit while busy", async () => {
    let release: (r: Response) => void = () => undefined;
    const { fetchMock, user } = setup(
      () => new Promise<Response>((resolve) => (release = resolve)),
    );
    await fillAndSubmit(user);
    expect(
      (screen.getByRole("button", { name: t("login.submitting") }) as HTMLButtonElement).disabled,
    ).toBe(true);
    await user.click(screen.getByRole("button", { name: t("login.submitting") }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    release(reply(200, { csrf_token: "x", user: USER }));
    await waitFor(() => expect(csrfToken()).toBe("x"));
  });
});
