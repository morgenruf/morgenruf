FROM node:25-alpine AS build
WORKDIR /workspace
# Node 25 dropped the bundled corepack, so install it rather than relying on the
# base image. The pnpm version still comes from packageManager in package.json.
RUN npm install -g --force corepack@0.36.0 && corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY frontend/package.json frontend/package.json
RUN pnpm install --frozen-lockfile
COPY frontend/ frontend/
RUN pnpm --filter @morgenruf/frontend build

FROM nginxinc/nginx-unprivileged:stable-alpine
USER root
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /workspace/frontend/dist /usr/share/nginx/html
USER 101
ENV BACKEND_URL=http://app:3000
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s CMD wget -q -O /dev/null http://127.0.0.1:8080/frontend-healthz || exit 1
