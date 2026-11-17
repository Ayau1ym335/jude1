# syntax=docker/dockerfile:1
# Build context: repository root. Node active LTS pinned by tag + index digest (IDR-09).
ARG NODE_IMAGE=node:26.13.1-bookworm-slim@sha256:5df79989ed685e09f0a98019db4cebfb22fb9df1a53c0161664a011f7ff6b0f1

FROM ${NODE_IMAGE} AS build
# Node >= 25 no longer ships corepack; install the pinned pnpm from package.json#packageManager.
RUN npm install -g --no-fund --no-audit pnpm@12.21.0
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /src
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/contracts/package.json packages/contracts/
RUN pnpm install --frozen-lockfile
COPY apps/web apps/web
RUN pnpm --filter @jude/web build

FROM ${NODE_IMAGE}
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build --chown=node:node /src/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /src/apps/web/.next/static ./apps/web/.next/static
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
