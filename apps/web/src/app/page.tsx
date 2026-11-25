"use client";

// Placeholder start page. Product screens are built under src/features/<mod> (TT-U tasks); the
// application shell with navigation comes with TSK-UIX-01-U.
import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { createJudeClient } from "@jude/contracts";

import { LogoutButton } from "../features/iam/LogoutButton";
import { t } from "../i18n";

export default function HomePage() {
  const router = useRouter();
  const client = useMemo(() => createJudeClient(), []);
  return (
    <main>
      <h1>{t("home.heading")}</h1>
      <p>{t("home.devNotice")}</p>
      <LogoutButton client={client} onLoggedOut={() => router.push("/login")} />
    </main>
  );
}
