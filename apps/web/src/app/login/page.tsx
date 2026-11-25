"use client";

// Sign-in page (FN-IAM-01). After a successful login the user goes to the start page.
import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { createJudeClient } from "@jude/contracts";

import { LoginForm } from "../../features/iam/LoginForm";

export default function LoginPage() {
  const router = useRouter();
  const client = useMemo(() => createJudeClient(), []);
  return (
    <main>
      <LoginForm client={client} onLoggedIn={() => router.push("/")} />
    </main>
  );
}
