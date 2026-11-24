import type { ReactNode } from "react";

import { t } from "../i18n";

export const metadata = {
  title: t("app.title"),
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
