// Component tests (CT-*, DEVELOPMENT_TEST_PLAN): jsdom. tsconfig keeps JSX as is ("preserve",
// Next compiles it); for tests Vite's Oxc transform compiles it with React's automatic runtime.
import { defineConfig } from "vitest/config";

export default defineConfig({
  oxc: { jsx: { runtime: "automatic" } },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
