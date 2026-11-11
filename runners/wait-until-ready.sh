#!/usr/bin/env bash
# Wait until this runner can do a job, instead of exiting until systemd gives up.
#
#     wait-until-ready.sh        # returns 0 once ready; until then, waits
#
# WHY WAIT AND NOT EXIT. A refusal used to be `exit 1`, and systemd restarted
# the unit five seconds later. That reads like a pause. It is not: every exit
# counts toward StartLimitBurst, and after twenty in five minutes systemd stops
# for good. On 2026-11-10 the disk was full, every runner exited twenty times,
# and all ten were dead until somebody ran reset-failed -- the fleet had been
# off for eight days by then. Waiting here keeps the unit running, so a refusal
# costs nothing, and the runner rejoins the moment the condition clears.
#
# THREE CONDITIONS, CHEAPEST FIRST:
#   disk        free space where the runner works. A full disk does not fail
#               cleanly: the runner aborts (exit 134) writing its first log
#               line, before it can say anything about why.
#   network     a TCP connection to GitHub. After a power cut this VM can boot
#               before the office network is back.
#   throughput  check-throughput.sh, unchanged: a starving link refuses.
#
# COULD-NOT-MEASURE STANDS ASIDE, as in check-throughput.sh: a df that fails is
# not evidence that the disk is full, and must never hold the fleet back.
#
# The reason it is waiting goes to the journal, and to a file anyone on the box
# can read without sudo:
#     cat /opt/actions-runner-*/_diag/not-ready
#
# NOT `set -e`. When the disk is full, writing that file fails too, and a failed
# write must not end the loop.
set -uo pipefail

: "${RUNNER_DIR:?RUNNER_DIR must be set}"
: "${READY_MIN_FREE_MB:=2048}"
: "${READY_HOST:=api.github.com}"
: "${READY_PORT:=443}"
: "${READY_FIRST_DELAY:=5}"
: "${READY_MAX_DELAY:=300}"

STATUS="$RUNNER_DIR/_diag/not-ready"

free_mb() { df -P -m "$RUNNER_DIR" 2>/dev/null | awk 'NR == 2 { print $4 }'; }

# Prints why the runner is not ready, or nothing when it is.
not_ready() {
  local mb
  mb=$(free_mb)
  if [[ "$mb" =~ ^[0-9]+$ ]] && [ "$mb" -lt "$READY_MIN_FREE_MB" ]; then
    echo "disk: ${mb} MB free where the runner works, needs ${READY_MIN_FREE_MB} MB"
    return
  fi
  if ! timeout 10 bash -c "exec 3<>/dev/tcp/${READY_HOST}/${READY_PORT}" 2>/dev/null; then
    echo "network: cannot open a connection to ${READY_HOST}:${READY_PORT}"
    return
  fi
  # Its verdict goes to the journal; only the exit code decides.
  if ! "$RUNNER_DIR/check-throughput.sh" >&2; then
    echo "throughput: the link is too slow to download an action in time"
    return
  fi
}

delay=$READY_FIRST_DELAY
while :; do
  why=$(not_ready)
  if [ -z "$why" ]; then
    rm -f "$STATUS"
    exit 0
  fi
  echo "not ready -- ${why}. Trying again in ${delay}s."
  mkdir -p "${STATUS%/*}" 2>/dev/null
  printf '%s  %s\n' "$(date -u +%FT%TZ)" "$why" > "$STATUS" 2>/dev/null
  sleep "$delay"
  delay=$(( delay * 2 ))
  [ "$delay" -gt "$READY_MAX_DELAY" ] && delay=$READY_MAX_DELAY
done
