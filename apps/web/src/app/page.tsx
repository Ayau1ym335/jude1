// Placeholder start page. Product screens are built under src/features/<mod> (TT-U tasks).
import { t } from "../i18n";

export default function HomePage() {
  return (
    <main>
      <h1>{t("home.heading")}</h1>
      <p>{t("home.devNotice")}</p>
    </main>
  );
}
