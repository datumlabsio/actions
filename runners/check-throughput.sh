#!/usr/bin/env bash
# Refuse to register a runner that cannot fetch at a usable rate.
#
#     check-throughput.sh        # exit 0 = usable, 1 = refuse to register
#
# On 2026-10-06 every runner here sat at 6 KB/s for a morning. Nothing noticed.
# The link answered pings, the runners registered, jobs landed on them, and the
# handshake, TLS and first byte were all fast -- only bulk transfer collapsed.
# The cause was a path MTU of 1492 against an interface set to 1500: full-size
# packets dropped silently, so throughput fell to 0.5% while the link looked up.
#
# WHAT MADE IT EXPENSIVE WAS NOT THE FAULT, IT WAS THE SHAPE OF THE FAILURE.
# Jobs that downloaded an action died at GitHub's 100-second action-download
# timeout. Jobs that downloaded nothing passed. GitHub-hosted jobs in the same
# run passed. So it read as a broken branch, and the first three hours went
# into the repository rather than the network.
#
# A runner that cannot fetch is worse than a runner that is absent: absent, the
# job queues and someone sees a queue. Present and starving, the job lands and
# fails as though the code were wrong. So this runs BEFORE registration -- if
# the link is bad the runner never appears, systemd retries, and it joins by
# itself when the network recovers.
#
# THE THRESHOLD IS THE REAL BUDGET, NOT A ROUND NUMBER. The runner gives an
# action download 100 seconds. The probe is a real action tarball over the real
# host, and it must arrive in 20 -- a fifth of the budget. That sits about
# twelve times above the speed that broke us and twelve times below the speed
# of a healthy link here, so neither a slow afternoon nor a fast one moves it.
set -uo pipefail

# actions/checkout at the SHA this org pins everywhere, fetched from the host
# that actually serves action tarballs. Not a synthetic speed test: the point
# is to measure the path a job will use, including whatever sits in front of it.
: "${DATUM_PROBE_URL:=https://codeload.github.com/actions/checkout/tar.gz/11bd71901bbe5b1630ceea73d27597364c9af683}"
: "${DATUM_PROBE_MAX_SECONDS:=20}"
# A 404 returns in milliseconds and would sail through a timing check. Requiring
# a real payload is what stops a broken probe URL from reporting a healthy link.
: "${DATUM_PROBE_MIN_BYTES:=500000}"
: "${DATUM_PROBE_ATTEMPTS:=2}"

refuse() {
  echo "REFUSING TO REGISTER: $1" >&2
  echo "  This runner would accept jobs it cannot complete, and they would fail" >&2
  echo "  as though the repository were at fault. Leaving it unregistered keeps" >&2
  echo "  the queue visible instead." >&2
  echo "  Check: ip link show | grep mtu   — a path MTU below the interface MTU" >&2
  echo "  starves bulk transfer while leaving handshakes fast. That was the" >&2
  echo "  cause on 2026-10-06 (gateway 1492, interface 1500)." >&2
  exit 1
}

# A check that could not RUN is not a check that failed. A broken probe URL or a
# missing curl must not ground the fleet -- it says so loudly and stands aside.
skip() {
  echo "::warning::throughput unverified: $1" >&2
  exit 0
}

command -v curl >/dev/null 2>&1 || skip "curl is not installed"

attempt=1
last=""
while [ "$attempt" -le "$DATUM_PROBE_ATTEMPTS" ]; do
  out=$(curl -sS -L -o /dev/null \
        --max-time "$DATUM_PROBE_MAX_SECONDS" \
        -w '%{http_code} %{size_download} %{time_total} %{speed_download}' \
        "$DATUM_PROBE_URL" 2>/dev/null)
  rc=$?
  set -- $out
  code="${1:-000}"; size="${2:-0}"; secs="${3:-0}"; rate="${4:-0}"

  if [ "$rc" -eq 0 ] && [ "$code" = "200" ] && [ "$size" -ge "$DATUM_PROBE_MIN_BYTES" ]; then
    echo "throughput ok: ${size} bytes in ${secs}s (${rate} B/s)"
    exit 0
  fi

  # 28 is curl's timeout. Reaching the cap on a real payload IS the failure this
  # exists to catch -- the morning it mattered, curl stopped at half a tarball.
  if [ "$rc" -eq 28 ]; then
    last="only ${size} bytes in ${DATUM_PROBE_MAX_SECONDS}s (${rate} B/s)"
  elif [ "$rc" -ne 0 ]; then
    last="curl exit ${rc}"
  elif [ "$code" != "200" ]; then
    last="HTTP ${code}"
  else
    last="only ${size} bytes, below the ${DATUM_PROBE_MIN_BYTES} needed to judge"
  fi
  attempt=$((attempt + 1))
done

# One slow sample is a blip; every sample is a link. Only a timeout is treated
# as evidence of the fault -- anything else means the probe itself is broken,
# and a broken probe is not a reason to take runners offline.
case "$last" in
  "only "*" bytes in "*) refuse "$last — the link cannot sustain an action download" ;;
  *) skip "$last" ;;
esac
