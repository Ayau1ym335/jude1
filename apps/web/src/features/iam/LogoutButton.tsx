"use client";

// FN-IAM-03 sign-out button (TSK-IAM-03-U). Text from the message resources (NFR-05, VER-09).
import { useState } from "react";

import type { JudeClient } from "@jude/contracts";

import { t } from "../../i18n";
import { logout } from "./session";

type Props = {
  client: JudeClient;
  onLoggedOut: () => void;
};

export function LogoutButton({ client, onLoggedOut }: Props) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function signOut() {
    if (busy) return;
    setBusy(true);
    setProblem(null);
    const result = await logout(client);
    setBusy(false);
    if (result.ok) {
      onLoggedOut();
    } else {
      setProblem(result.message ?? t("login.unavailable"));
    }
  }

  return (
    <div>
      <button type="button" onClick={signOut} disabled={busy}>
        {busy ? t("logout.submitting") : t("logout.submit")}
      </button>
      {problem !== null && <p role="alert">{problem}</p>}
    </div>
  );
}
