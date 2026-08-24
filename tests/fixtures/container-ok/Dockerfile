# B-26's rules, demonstrated: a base pinned by digest, a NUMERIC non-root user,
# and no package manager cache left in the layer.
#
# The digest is real and resolvable — a fixture that cannot build proves nothing
# about a workflow whose whole job is building.
FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a

# A container that runs as root runs as root on the node (§6). The UID is
# numeric because Kubernetes `runAsNonRoot` resolves a number, not a name —
# hadolint DL3066 says the same thing.
RUN useradd --create-home --uid 10001 app
USER 10001
WORKDIR /home/app

COPY --chown=10001:10001 app.py .

CMD ["python", "app.py"]
