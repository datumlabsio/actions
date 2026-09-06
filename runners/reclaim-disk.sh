#!/usr/bin/env bash
# Reclaim disk before it runs out, not after.
#
# GitHub gives every job a clean 14 GB and throws the machine away. On our own
# hardware the NODE keeps everything: image layers, build caches, node_modules,
# Trivy's ~1 GB vulnerability database re-downloaded as it updates. Ephemeral
# runners clear the WORK directory, not the Docker store underneath it.
#
# A full disk is the most common way a self-hosted runner dies, and it does not
# fail cleanly -- jobs start, then fail somewhere in the middle with an error
# about the thing they were doing rather than about disk.
#
# Runs hourly. Cheap when there is nothing to do.
set -euo pipefail

: "${RUNNER_DIR:=/opt/actions-runner}"
: "${DISK_WARN_PCT:=75}"
: "${DISK_CRIT_PCT:=85}"

used() { df --output=pcent "$1" | tail -1 | tr -dc '0-9'; }

before=$(used "$RUNNER_DIR")
echo "$(date -u +%FT%TZ) disk ${before}% before"

# Always safe: anything not referenced by a live container or image.
docker container prune -f  >/dev/null 2>&1 || true
docker builder prune -f    >/dev/null 2>&1 || true

if [ "$(used "$RUNNER_DIR")" -ge "$DISK_WARN_PCT" ]; then
  # Images unused for a day. Keeps today's base layers, so the next build is
  # still warm, and drops last week's.
  docker image prune -af --filter "until=24h" >/dev/null 2>&1 || true
fi

if [ "$(used "$RUNNER_DIR")" -ge "$DISK_CRIT_PCT" ]; then
  # Past this point a warm cache is worth less than a working runner.
  echo "::warning::disk still $(used "$RUNNER_DIR")% -- dropping every unused image and volume"
  docker system prune -af --volumes >/dev/null 2>&1 || true
  # Orphaned work directories from runners that died mid-job.
  find "$RUNNER_DIR/_work" -maxdepth 1 -mindepth 1 -type d -mtime +1 \
    -exec rm -rf {} + 2>/dev/null || true
fi

after=$(used "$RUNNER_DIR")
echo "$(date -u +%FT%TZ) disk ${after}% after (reclaimed $((before - after)) points)"

# Loud, because the next thing that happens is jobs failing for unrelated-looking
# reasons. Alerting on this is the difference between fixing it on a Tuesday and
# debugging it on a Friday.
if [ "$after" -ge "$DISK_CRIT_PCT" ]; then
  echo "::error::disk is ${after}% AFTER a full prune. This runner needs more disk or fewer container jobs."
  exit 1
fi
