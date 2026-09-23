# THIS FIXTURE REFUSES TO BUILD UNLESS `build-args` REACHED IT.
#
# A fixture that merely accepts an argument would still build if the input
# stopped being threaded through, and the self-test would go green while the
# feature was broken for every caller. So the assertion is the build: PROFILE
# defaults to a value the RUN below rejects, and only `PROFILE=heavy` passes.
#
# It is checked in the build-scan job AND, on a publish, again in the publish
# job — which is the property that matters. The scanned image has to be the
# image that would be published, so an arg reaching one build and not the
# other must fail rather than ship an unscanned variant.
#
# Same rules as container-ok beside it: base pinned by digest, numeric non-root
# user, no package-manager cache in the layer.
FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a

ARG PROFILE=missing
RUN if [ "$PROFILE" != "heavy" ]; then \
      echo "build-args did not reach this build: PROFILE=$PROFILE" >&2; \
      exit 1; \
    fi

RUN useradd --create-home --uid 10001 app
USER 10001
WORKDIR /home/app

COPY --chown=10001:10001 app.py .

CMD ["python", "app.py"]
