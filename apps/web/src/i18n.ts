// UI text lives in message resources, never in components (NFR-05, VER-09 / FN-OPS-01).
// The wording lint checks these resources for prohibited words (WRD001) and the components
// for hard-coded text (WRD002).
import ru from "./messages/ru.json";

export type MessageKey = keyof typeof ru;

export function t(key: MessageKey): string {
  return ru[key];
}
