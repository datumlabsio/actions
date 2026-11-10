#!/usr/bin/env bash
# Reclaim disk before it runs out, not after.
#
# WHAT ACTUALLY FILLS IT. Not image layers -- this VM runs no container jobs and
# has no Docker. On 2026-11-10 the disk was 100% full, and the 65 GB that came
# back was download caches in each runner's home (pnpm's store, uv's cache) and
# a second copy of the runner itself, left behind by its own self-update.
#
# The version before this pruned Docker, which is not installed, and looked in
# /opt/actions-runner, which no runner has used since there were ten of them.
# It cleaned nothing for six weeks, and reported each run to a journal nobody
# reads. That is the failure this file now has to be tested against.
#
# EVERY RUNNER, FOUND BY DIRECTORY: $RUNNER_ROOT/actions-runner-N, each with its
# own run-ephemeral.sh. Not from a count, and NOT from RUNNER_DIR -- the env
# file still names the old single-runner directory, which is exactly how the
# previous version missed all ten.
#
# NEVER UNDER A RUNNING JOB. A runner with a Runner.Worker process is mid-job;
# its caches and work tree are left alone and it is picked up next hour.
#
# TIERS. A warm cache saves real time on a slow uplink, until the disk is the
# problem:
#   always            runner versions no longer in use -- older than a day, so
#                     an update still unpacking is never touched -- and diag
#                     logs older than a week
#   >= DISK_WARN_PCT  idle runners: download caches and the tool cache
#   >= DISK_CRIT_PCT  idle runners: the whole work tree and pipx's tools
#
# Hourly, as root. Exits 1 if the disk is still critical afterwards. It cannot
# tell anyone itself: a runner whose disk stays full waits in
# wait-until-ready.sh instead of registering, runner-watch sees it offline, and
# that is the alert.
set -uo pipefail
shopt -s nullglob

: "${RUNNER_ROOT:=/opt}"
: "${DISK_WARN_PCT:=70}"
: "${DISK_CRIT_PCT:=85}"

used() { df -P "$RUNNER_ROOT" 2>/dev/null | awk 'NR == 2 { sub("%", "", $5); print $5 + 0 }'; }

# The worker exists only while a job runs, as $dir/bin/Runner.Worker. The `/`
# after the directory keeps actions-runner-1 from matching actions-runner-10.
busy() { pgrep -f "^$1/bin[^/ ]*/Runner\.Worker" >/dev/null 2>&1; }

runners=()
for d in "$RUNNER_ROOT"/actions-runner-*/; do
  [ -f "${d}run-ephemeral.sh" ] && runners+=("${d%/}")
done

before=$(used)
echo "$(date -u +%FT%TZ) disk ${before}% before, ${#runners[@]} runner(s)"

for d in "${runners[@]}"; do
  # `bin` is a symlink to the version in use. Only act on a target that ends in
  # a plain version number; anything unexpected is left alone rather than
  # guessed at, because guessing wrong deletes the runner that is running.
  cur=$(readlink "$d/bin" 2>/dev/null)
  cur=${cur##*bin.}
  if [[ "$cur" =~ ^[0-9]+(\.[0-9]+)+$ ]]; then
    find "$d" -maxdepth 1 -mindepth 1 \( -name 'bin.*' -o -name 'externals.*' \) \
      ! -name "bin.$cur" ! -name "externals.$cur" -mtime +1 \
      -exec rm -rf {} + 2>/dev/null
  fi
  find "$d/_diag" -type f -mtime +7 -delete 2>/dev/null
done

if [ "$(used)" -ge "$DISK_WARN_PCT" ]; then
  for d in "${runners[@]}"; do
    if busy "$d"; then echo "  ${d##*/}: mid-job, caches left alone"; continue; fi
    rm -rf "$d/.pnpm-store" "$d/.cache" "$d/.npm/_cacache" "$d/_work/_tool"
  done
fi

if [ "$(used)" -ge "$DISK_CRIT_PCT" ]; then
  for d in "${runners[@]}"; do
    busy "$d" && continue
    rm -rf "$d/_work/"* "$d/.local"
  done
fi

# None installed today. If container jobs ever run here, this is what they need.
if command -v docker >/dev/null 2>&1; then
  docker container prune -f >/dev/null 2>&1 || true
  docker builder prune -f >/dev/null 2>&1 || true
  if [ "$(used)" -ge "$DISK_WARN_PCT" ]; then
    docker image prune -af --filter "until=24h" >/dev/null 2>&1 || true
  fi
fi

after=$(used)
echo "$(date -u +%FT%TZ) disk ${after}% after"
if [ "$after" -ge "$DISK_CRIT_PCT" ]; then
  echo "disk still ${after}% after cleaning every idle runner -- something other than the runners is using it: du -xsh /* | sort -rh | head" >&2
  exit 1
fi
