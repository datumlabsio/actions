#!/usr/bin/env bash
# Give any runner systemd has given up on another chance.
#
# StartLimitBurst is right to stop a runner restarting every five seconds into
# the same failure -- that is a hammer on GitHub's API. But it stops it FOR
# GOOD, until a person runs reset-failed, and on 2026-11-10 nobody had for
# eight days.
#
# wait-until-ready.sh now absorbs the failures we know about -- full disk, no
# network, a slow link -- without exiting at all. This is for the ones we do not
# know about yet. Every fifteen minutes, a runner in the FAILED state gets one
# more round: at most twenty attempts a quarter-hour, never zero for ever.
#
# Only failed units. A runner somebody STOPPED on purpose is inactive, not
# failed, and is left alone.
set -uo pipefail
shopt -s nullglob

: "${RUNNER_ROOT:=/opt}"

for d in "$RUNNER_ROOT"/actions-runner-*/; do
  [ -f "${d}run-ephemeral.sh" ] || continue
  n=${d%/}
  n=${n##*-}
  unit="actions-runner@${n}.service"
  if [ "$(systemctl is-failed "$unit" 2>/dev/null)" = "failed" ]; then
    echo "reviving $unit"
    systemctl reset-failed "$unit"
    systemctl start --no-block "$unit"
  fi
done
