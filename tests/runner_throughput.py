#!/usr/bin/env python3
"""A starving runner must not register, and a broken probe must not ground one.

    python3 tests/runner_throughput.py

On 2026-10-06 every runner here ran at 6 KB/s for a morning: path MTU 1492
against an interface set to 1500, so full-size packets were dropped and bulk
transfer collapsed while handshakes stayed fast. Jobs landed, downloaded an
action, and died at GitHub's 100-second timeout -- reading as broken branches,
not a broken network.

TWO OUTCOMES, AND THEY MUST NOT BE CONFUSED:

    measured, and too slow   -> REFUSE to register. The job queues, visibly.
    could not measure at all -> WARN and stand aside. A broken probe URL or a
                                missing curl is not evidence about the link,
                                and must never take the fleet offline.

That is the same distinction preflight.sh had to learn the hard way, where a
discarded error reported a working team as broken.

`curl` is stubbed on PATH. Nothing here touches the network.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "runners/check-throughput.sh"
SRC = SCRIPT.read_text()
FAILURES: list[str] = []

# Read the script's own numbers rather than restating them. The first version
# of this file hardcoded a payload size into the stub that did not match the
# artifact the script actually fetched, so the "healthy link" case passed in
# CI while every real run stood aside, verifying nothing.
PROBE_BYTES = int(re.search(r"DATUM_PROBE_BYTES=(\d+)", SRC).group(1))
MAX_SECONDS = int(re.search(r"DATUM_PROBE_MAX_SECONDS:=(\d+)", SRC).group(1))
MIN_BYTES = PROBE_BYTES * 85 // 100

# Measured on the runner VM, 2026-10-06, either side of the MTU fix.
RATE_THAT_BROKE_US = 6238
RATE_WHEN_HEALTHY = 1413805

# MODE picks what the fake curl reports. The shapes are the real ones: a healthy
# fetch, the exit-28-with-partial-bytes that the bad morning actually produced,
# a DNS failure, a 404, and a 200 too small to judge.
STUB = r'''#!/usr/bin/env bash
case "${MODE}" in
  fast)     echo -n "200 ${PROBE_BYTES} 1.64 ${RATE_HEALTHY}" ;;
  slow)     echo -n "200 1122970 20.00 56148"; exit 28 ;;
  # Exactly one byte under the floor: the shape of the bug that shipped.
  underfloor) echo -n "200 $((MIN_BYTES - 1)) 1.20 400000" ;;
  dns)      echo -n "000 0 0.00 0"; exit 6 ;;
  notfound) echo -n "404 14 0.12 116" ;;
  tiny)     echo -n "200 2048 0.30 6826" ;;
  # A big error page: fast, 404, and well over the minimum size. Only the
  # status check catches this one.
  bigerror) echo -n "404 900000 1.00 900000" ;;
  # Times out once, then succeeds. One blip must not ground a runner; it is
  # the SECOND failure that is evidence.
  flaky)    n=$(cat "$COUNTER" 2>/dev/null || echo 0); echo $((n + 1)) > "$COUNTER"
            if [ "$n" -eq 0 ]; then echo -n "200 1122970 20.00 56148"; exit 28
            else echo -n "200 2318343 1.64 1413805"; fi ;;
esac
'''


def run(mode: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as td:
        binn = Path(td) / "bin"
        binn.mkdir()
        (binn / "curl").write_text(STUB)
        (binn / "curl").chmod(0o755)
        r = subprocess.run(
            ["bash", str(SCRIPT)],
            env={**os.environ, "PATH": f"{binn}:{os.environ['PATH']}",
                 "MODE": mode, "COUNTER": str(Path(td) / "n"),
                 "PROBE_BYTES": str(PROBE_BYTES), "MIN_BYTES": str(MIN_BYTES),
                 "RATE_HEALTHY": str(RATE_WHEN_HEALTHY), **(env or {})},
            capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' — {detail}'}")
    if not ok:
        FAILURES.append(name)


# --- the failure this exists for -----------------------------------------
code, out = run("slow")
check("a link that times out on a real payload REFUSES to register",
      code == 1 and "REFUSING TO REGISTER" in out,
      f"exit {code}: {out[:160]}")
check("...and says why a queue is better than a job that lands and fails",
      "queue" in out.lower(), out)
check("...and points at the cause that actually did this",
      "mtu" in out.lower(), "the next person should not spend a morning in the repo")
check("...and reports what it measured, not just a verdict",
      "1122970" in out and "56148" in out, out)

# --- the healthy case -----------------------------------------------------
code, out = run("fast")
check("a healthy link registers", code == 0 and "REFUSING" not in out, f"exit {code}")
check("...and still records the number, so a trend is visible in the journal",
      "1413805" in out, out)

# --- could not measure: warn, never refuse -------------------------------
for mode, why in [("dns", "curl failed outright"),
                  ("notfound", "the probe URL 404s"),
                  ("tiny", "the payload was too small to judge")]:
    code, out = run(mode)
    check(f"{why} -> warns and stands aside",
          code == 0 and "REFUSING" not in out and "warning" in out.lower(),
          f"exit {code}: {out[:140]}")

# A 404 is instant. A check that only looked at elapsed time would call that
# the fastest link it had ever seen.
code, out = run("notfound")
check("a 404 is NOT mistaken for a fast link",
      "throughput ok" not in out, out)

code, out = run("tiny")
check("a 200 carrying almost nothing is NOT mistaken for a fast link",
      "throughput ok" not in out, out)

# A large error page clears the size floor. Only the status check stops it.
code, out = run("bigerror")
check("a BIG 404 is not mistaken for a healthy fetch",
      "throughput ok" not in out and code == 0,
      "a size floor alone lets a fat error page look like a fast link")

# --- one blip is not a verdict -------------------------------------------
code, out = run("flaky")
check("a single timeout followed by a good fetch still registers",
      code == 0 and "REFUSING" not in out,
      f"exit {code}: {out[:140]} — retries exist so a blip does not ground a runner")

# --- missing curl ---------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    # Absolute interpreter: emptying PATH removes curl, and would otherwise
    # remove bash too, which tests the harness rather than the script.
    r = subprocess.run(["/bin/bash", str(SCRIPT)],
                       env={**os.environ, "PATH": td}, capture_output=True, text=True)
check("no curl at all -> warns, does not refuse",
      r.returncode == 0 and "REFUSING" not in (r.stdout + r.stderr),
      f"exit {r.returncode}")

# --- the threshold is configurable, and it is the real budget ------------
src = SCRIPT.read_text()
check("the probe fetches a real action tarball over codeload, not a speed test",
      "codeload.github.com" in src,
      "measuring a synthetic host measures a different path than a job uses")
check("the default budget is a fraction of the runner's 100s action timeout",
      "DATUM_PROBE_MAX_SECONDS:=20" in src, "20s of a 100s budget")
check("a minimum payload size is required",
      "DATUM_PROBE_MIN_BYTES" in src, "otherwise a 404 passes")
check("the retry count is configurable",
      "DATUM_PROBE_ATTEMPTS" in src)

# --- the floor has to be REACHABLE -------------------------------------
# A floor above the payload is a check that can never pass. It shipped that
# way: a 500000-byte floor against a 424625-byte artifact, so every run stood
# aside with a warning and nothing was ever verified.
check("the floor is below the artifact the probe actually fetches",
      MIN_BYTES < PROBE_BYTES,
      f"floor {MIN_BYTES} vs payload {PROBE_BYTES} — the check could never pass")
check("...and the size is recorded, not guessed",
      "DATUM_PROBE_BYTES=" in SRC,
      "a floor picked without measuring the artifact is how this broke")

# The URL must be CONSTRUCTED from the identity whose size was measured.
# Written out separately, someone can repoint the probe at a different
# artifact and leave the byte count behind — and no offline test can weigh a
# remote file to notice.
check("the probe URL is built from the measured identity, not written out",
      "${DATUM_PROBE_ID%@*}" in SRC and "${DATUM_PROBE_ID#*@}" in SRC
      and "DATUM_PROBE_ID=" in SRC,
      "a hardcoded URL can drift from the size recorded beside it")
id_line = next(i for i, l in enumerate(SRC.splitlines()) if "DATUM_PROBE_ID=" in l)
bytes_line = next(i for i, l in enumerate(SRC.splitlines()) if "DATUM_PROBE_BYTES=" in l)
check("...and the size sits directly beneath it, so a diff shows both",
      bytes_line == id_line + 1,
      f"ID on line {id_line + 1}, size on line {bytes_line + 1}")

implied = MIN_BYTES // MAX_SECONDS
check("the threshold rejects the rate that actually broke us",
      implied > RATE_THAT_BROKE_US * 5,
      f"{implied} B/s floor vs {RATE_THAT_BROKE_US} B/s measured — too close")
check("...and accepts the rate a healthy link here sustains",
      implied < RATE_WHEN_HEALTHY // 5,
      f"{implied} B/s floor vs {RATE_WHEN_HEALTHY} B/s healthy — too close")

code, out = run("underfloor")
check("a payload just under the floor stands aside rather than refusing",
      code == 0 and "REFUSING" not in out and "warning" in out.lower(),
      f"exit {code}: {out[:140]}")

# --- ordering is the property --------------------------------------------
eph = (ROOT / "runners/run-ephemeral.sh").read_text()
check("run-ephemeral.sh runs the check BEFORE registering",
      "check-throughput.sh" in eph
      and eph.index("check-throughput.sh") < eph.index("./config.sh"),
      "checking after registration is checking nothing: the job already landed")

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)}: {', '.join(FAILURES)}")
    sys.exit(1)
print("\nOK: starving refuses, unmeasurable stands aside")
