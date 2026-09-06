#!/usr/bin/env bash
# One job per runner, then a clean re-register. Never a reused runner.
#
# `--ephemeral` makes the runner exit after a single job. That is the whole
# security property: the next job gets a fresh registration and a fresh work
# directory, so it cannot read the previous job's checkout, its cached
# credentials, or anything it left in /tmp.
#
# A persistent runner is faster because caches survive. It is also a machine
# where job two can read job one's tokens, and jobs here run dependency installs
# from npm and PyPI. Slower is the correct trade.
#
# Run as a systemd service with Restart=always: the runner exits after each job,
# systemd restarts it, and this script registers a new one.
set -euo pipefail

: "${RUNNER_ORG:?set RUNNER_ORG, e.g. datumlabsio}"
: "${RUNNER_GROUP:?set RUNNER_GROUP -- the group scoped to PRIVATE repos only}"
: "${RUNNER_LABELS:=self-hosted,linux,x64,datum}"
: "${RUNNER_DIR:=/opt/actions-runner}"
# Registration goes through the datum-runner App, not a PAT.
#
# A PAT on disk IS the credential -- read the file, use it. It also belongs to a
# PERSON: when they leave or rotate it, every runner silently stops registering.
# The App's key needs a signed JWT exchange first, the token it yields lasts an
# hour, and the App holds `organization_self_hosted_runners: write` and nothing
# else -- it cannot read a repository, push, or see a secret.
#
# GH_TOKEN is still honoured so a PAT works while the App is being set up. It
# warns, because "temporary" credentials are the ones that stay.
: "${APP_ID:=}"
: "${APP_PRIVATE_KEY_PATH:=}"
: "${GH_TOKEN:=}"

if [ -n "$APP_ID" ] && [ -n "$APP_PRIVATE_KEY_PATH" ]; then
  GH_TOKEN=$(APP_ID="$APP_ID" APP_PRIVATE_KEY_PATH="$APP_PRIVATE_KEY_PATH" \
             RUNNER_ORG="$RUNNER_ORG" python3 "${RUNNER_DIR}/app-token.py")
elif [ -n "$GH_TOKEN" ]; then
  echo "::warning::Registering with a PAT. Move to the datum-runner App: a PAT is a long-lived credential tied to a person."
else
  echo "Set APP_ID and APP_PRIVATE_KEY_PATH (preferred), or GH_TOKEN." >&2
  exit 1
fi

cd "$RUNNER_DIR"

# A registration token is single-use and expires in an hour, which is why this
# is fetched per job rather than stored anywhere. The token authorising THIS
# call is itself an hour-long installation token, minted a moment ago.
TOKEN=$(curl -sS --fail -X POST \
  -H "Authorization: Bearer ${GH_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/orgs/${RUNNER_ORG}/actions/runners/registration-token" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

# --ephemeral is not optional. Without it this loop reuses one registration and
# the isolation above disappears silently -- the runner keeps working, which is
# what makes it easy to miss.
./config.sh \
  --unattended \
  --ephemeral \
  --replace \
  --url "https://github.com/${RUNNER_ORG}" \
  --token "$TOKEN" \
  --runnergroup "$RUNNER_GROUP" \
  --labels "$RUNNER_LABELS" \
  --name "$(hostname)-$$" \
  --work _work

# Exits after one job. systemd restarts us; the next loop registers afresh.
./run.sh
