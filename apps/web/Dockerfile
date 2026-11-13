# syntax=docker/dockerfile:1
# Build context: repository root (pnpm workspace).
FROM node:22-alpine AS base
RUN corepack enable
WORKDIR /repo

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
RUN pnpm install --frozen-lockfile --filter @operon/web...

FROM deps AS build
ARG NEXT_PUBLIC_OPERON_DATA_SOURCE=api
ENV NEXT_PUBLIC_OPERON_DATA_SOURCE=$NEXT_PUBLIC_OPERON_DATA_SOURCE NEXT_TELEMETRY_DISABLED=1
COPY apps/web apps/web
RUN pnpm --filter @operon/web build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup -S operon && adduser -S operon -G operon
COPY --from=build --chown=operon:operon /repo/apps/web/.next/standalone ./
COPY --from=build --chown=operon:operon /repo/apps/web/.next/static ./apps/web/.next/static
USER operon
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
