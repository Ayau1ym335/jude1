# @jude/contracts

The `/api/v1` contract of record and its TypeScript client (XC-FND-06, IF-01, TD-22).

| File              | What it is                                                                                                                                                |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `openapi.json`    | OpenAPI 3.1, generated from the FastAPI app by `uv run jude-openapi`. Never edit it by hand.                                                              |
| `src/schema.d.ts` | Types generated from `openapi.json` by openapi-typescript 7.13.0. Never edit it by hand.                                                                  |
| `src/index.ts`    | `createJudeClient()` (openapi-fetch). Every request gets an `X-Correlation-ID` header (XC-FND-11), and the module exports the DS-24 `ErrorResponse` type. |

## Changing the API

1. Change the FastAPI code in `services/api`.
2. Run `just contract`, which runs `uv run jude-openapi` and then `pnpm --filter @jude/contracts generate`.
3. Commit `openapi.json` and `src/schema.d.ts` together with the code.

## What the CI `contract` stage checks

1. **`openapi.json` matches the code** (`jude-openapi --check`).
2. **No breaking change against the base commit** (`tools/contract/oacompat.py`). Within v1 only additive changes are allowed. The table in that file lists the rules:
   - **Allowed:** new paths and operations, new optional parameters and request fields, new response fields and status codes.
   - **Breaking:** removed paths, operations, fields or status codes; new required inputs; narrowed request types or constraints; widened response types (including a field becoming nullable); a new response enum value.

   A breaking change needs `/api/v2` (IF-01); there is no override.

3. **The client regenerates to the committed bytes.** The generator is pinned and its output uses LF line endings, so the same `openapi.json` always gives the same `schema.d.ts`.
4. **The contract tests pass**, for example: every DS-24 error body validates against the published `ErrorResponse`, and every `/api/v1` operation declares it.

## Using the client

```ts
import { createJudeClient, newCorrelationId } from "@jude/contracts";

const api = createJudeClient();
const action = newCorrelationId(); // one id per user action
const { data, error } = await api.GET("/api/v1/health", {
  headers: { "X-Correlation-ID": action },
});
```

`error` is typed as `ErrorResponse`. Show `error.message_ru`, and give `error.correlation_id` to support.

## Notes

- openapi-typescript declares a peer dependency on TypeScript 5; this repo uses 6.0.3. Generation and type checking work with it, and pnpm only prints a peer warning.
- `/livez`, `/readyz` and `/metrics` are internal probes, not part of the contract.
