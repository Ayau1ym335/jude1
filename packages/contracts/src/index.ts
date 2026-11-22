/**
 * Typed client for the Jude /api/v1 contract (XC-FND-06, IF-01).
 *
 * `schema.d.ts` is generated from `openapi.json` (`pnpm --filter @jude/contracts generate`);
 * never edit it by hand. This file adds what every call needs:
 *
 * - same-origin requests (the Caddy proxy routes /api/* to the API);
 * - an `X-Correlation-ID` header on every request (XC-FND-11), one per user action: pass the
 *   same id to all calls that belong to one action, or let the client create one per call;
 * - the DS-24 `ErrorResponse` type for refusals.
 */
import createClient, { type Client, type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, operations, paths } from "./schema";

/** DS-24 error envelope (`error` is a catalogue code, IDR-05). */
export type ErrorResponse = components["schemas"]["ErrorResponse"];

export const CORRELATION_HEADER = "X-Correlation-ID";

/** A new correlation id: 32 lowercase hex characters, like the API creates. */
export function newCorrelationId(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

/** Adds X-Correlation-ID unless the caller already set one for this action. */
export const correlationMiddleware: Middleware = {
  onRequest({ request }) {
    if (!request.headers.has(CORRELATION_HEADER)) {
      request.headers.set(CORRELATION_HEADER, newCorrelationId());
    }
    return request;
  },
};

export type JudeClient = Client<paths>;

/** Client for the /api/v1 contract. `baseUrl` defaults to same-origin. */
export function createJudeClient(baseUrl = ""): JudeClient {
  const client = createClient<paths>({ baseUrl });
  client.use(correlationMiddleware);
  return client;
}
