FROM node:20-alpine AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web-status/package.json apps/web-status/package.json
RUN pnpm install --filter @musematic/web-status... --frozen-lockfile

FROM node:20-alpine AS build
WORKDIR /app
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web-status/node_modules ./apps/web-status/node_modules
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web-status ./apps/web-status
RUN pnpm --filter @musematic/web-status build

FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/apps/web-status/out /usr/share/nginx/html
RUN mkdir -p /status-cache \
  && touch /status-cache/last-known-good.json \
  && ln -sf /status-cache/last-known-good.json /usr/share/nginx/html/last-known-good.json
VOLUME ["/status-cache"]
EXPOSE 80
