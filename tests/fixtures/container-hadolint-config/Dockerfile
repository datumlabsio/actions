# THIS FIXTURE FAILS hadolint UNLESS THE VENDORED CONFIG IS READ.
#
# The `apt-get install` below is deliberately unpinned, which is DL3008 — the
# one rule configs/hadolint.yaml waives. So the lint stage passing on this
# fixture proves the config was found and applied; if `--config` ever stops
# being passed, this job fails rather than going green on a file nothing reads.
#
# Everything else here is deliberately clean, so DL3008 is the ONLY finding and
# a pass cannot come from some other rule masking it.
FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a

# Unpinned on purpose. See above.
# hadolint would say: Pin versions in apt get install.
RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 app
USER 10001
WORKDIR /home/app

COPY --chown=10001:10001 app.py .

CMD ["python", "app.py"]
