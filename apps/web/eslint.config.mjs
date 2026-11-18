// ESLint flat config (XC-FND-04). Next 16 has no `next lint`; run `pnpm --filter @jude/web lint`.
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // Layer rule: the UI never imports the geometry kernel. Geometry runs in the worker
      // and reaches the UI only through the /api/v1 contract (@jude/contracts).
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: [
                "**/packages/kernel",
                "**/packages/kernel/**",
                "jude_kernel",
                "jude_kernel/**",
                "@jude/kernel",
                "@jude/kernel/**",
              ],
              message:
                "UI must not import the geometry kernel; use the API contract (@jude/contracts).",
            },
          ],
        },
      ],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  globalIgnores([".next/**", "next-env.d.ts"]),
]);
