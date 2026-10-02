# The build output is static files, the same on every architecture, so build
# once on the runner's own platform. Running vite under QEMU for arm64 died
# with SIGILL (exit 132); only the nginx stage below needs to be per-arch.
FROM --platform=$BUILDPLATFORM node:26-alpine AS build
WORKDIR /workspace

# Node 25 dropped the bundled corepack, so install it rather than relying on the
# base image. The pnpm version still comes from packageManager in package.json.
RUN npm install -g --force corepack@0.36.0 && corepack enable

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY frontend/package.json frontend/package.json
RUN pnpm install --frozen-lockfile

COPY frontend/ frontend/
RUN pnpm --filter @morgenruf/frontend build && test -s frontend/dist/client/_shell.html

FROM nginxinc/nginx-unprivileged:stable-alpine

USER root
# The upstream image lags Alpine's security fixes (pcre2 CVE-2026-103111 in
# 2026-10), and the release scan refuses a fixable HIGH. Upgrading in place
# picks up whatever Alpine has fixed since the base image was built.
RUN apk upgrade --no-cache \
 && rm -rf /usr/share/nginx/html/*

COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /workspace/frontend/dist/client /usr/share/nginx/html

USER 101
ENV BACKEND_URL=http://app:3000
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s CMD wget -q -O /dev/null http://127.0.0.1:8080/frontend-healthz || exit 1
