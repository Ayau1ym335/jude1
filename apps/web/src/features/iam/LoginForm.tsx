"use client";

// FN-IAM-01 sign-in form (TSK-IAM-01-U). Every visible string comes from the message resources
// (NFR-05, VER-09); refusal texts come from the API (message_ru).
import { useState, type FormEvent } from "react";

import type { JudeClient } from "@jude/contracts";

import { t } from "../../i18n";
import { login, type SessionUser } from "./session";

type Props = {
  client: JudeClient;
  onLoggedIn: (user: SessionUser) => void;
};

function formatUnlock(iso: string): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return iso;
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short" }).format(when);
}

export function LoginForm({ client, onLoggedIn }: Props) {
  const [loginName, setLoginName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setProblem(null);
    const result = await login(client, { login: loginName, password });
    setBusy(false);
    if (result.ok) {
      setPassword("");
      onLoggedIn(result.user);
      return;
    }
    setPassword(""); // never keep a rejected password in the form
    if (result.message === null) {
      setProblem(t("login.unavailable"));
    } else if (result.lockedUntil) {
      setProblem(
        `${result.message} ${t("login.lockedUntil")} ${formatUnlock(result.lockedUntil)}.`,
      );
    } else {
      setProblem(result.message);
    }
  }

  const canSubmit = loginName.trim() !== "" && password !== "" && !busy;

  return (
    <form onSubmit={submit} noValidate>
      <h1>{t("login.title")}</h1>
      <label htmlFor="login-name">{t("login.login")}</label>
      <input
        id="login-name"
        name="username"
        autoComplete="username"
        value={loginName}
        onChange={(e) => setLoginName(e.target.value)}
        maxLength={256}
        required
      />
      <label htmlFor="login-password">{t("login.password")}</label>
      <input
        id="login-password"
        name="password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        maxLength={1024}
        required
      />
      {problem !== null && <p role="alert">{problem}</p>}
      <button type="submit" disabled={!canSubmit}>
        {busy ? t("login.submitting") : t("login.submit")}
      </button>
    </form>
  );
}
