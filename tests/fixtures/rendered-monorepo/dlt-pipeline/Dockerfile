# DES §6: pinned base, non-root, hadolint-clean. Owned by the scaffold — bumped
# by `copier update`, not hand-edited.
#
# Pinned by DIGEST, not by tag. A tag moves: `python:3.12-slim` today is not the
# image it was last month, so a rebuild of an unchanged commit can produce a
# different container. Renovate raises the digest as a reviewable pull request.
FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a

# A container that runs as root runs as root on the node. The UID is NUMERIC
# because Kubernetes `runAsNonRoot` resolves a number rather than a name — and
# hadolint DL3066 says the same thing.
RUN useradd --create-home --uid 10001 app
WORKDIR /app

# Dependencies before source, so a code change does not invalidate the layer
# that installs them.
COPY pyproject.toml ./
RUN pip install --no-cache-dir . \
 && chown -R 10001:10001 /app

COPY --chown=10001:10001 src/ ./src/

USER 10001

CMD ["python", "-m", "fixture_pipeline"]
