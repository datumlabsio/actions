# DES §6: pinned base, non-root, hadolint-clean. Owned by the scaffold.
#
# Next is server-rendered, so it needs Node at runtime — unlike react-vite, which
# produces static files any web server can hold and therefore ships no Dockerfile.
#
# Pinned by DIGEST. A tag moves; a rebuild of an unchanged commit should not
# produce a different container. Renovate raises the digest.
FROM node:24-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03 AS build

WORKDIR /app
RUN corepack enable

# The lockfile first, so a source change does not reinstall the world.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build

# A second stage so the build toolchain does not ship. The runtime image holds
# the built output and production dependencies, nothing else.
FROM node:24-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03

RUN useradd --create-home --uid 10001 app
WORKDIR /app
RUN corepack enable

COPY --from=build --chown=10001:10001 /app/.next ./.next
COPY --from=build --chown=10001:10001 /app/node_modules ./node_modules
COPY --from=build --chown=10001:10001 /app/package.json ./

USER 10001
EXPOSE 3000

CMD ["pnpm", "start"]
