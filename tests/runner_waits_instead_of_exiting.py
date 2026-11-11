#!/usr/bin/env python3
"""A runner that is not ready WAITS. It never exits, so systemd never gives up.

    python3 tests/runner_waits_instead_of_exiting.py

On 2026-11-10 the runner VM's disk was full. Each runner refused, exited,
was restarted five seconds later, and refused again. After twenty of those in
five minutes systemd's StartLimitBurst stopped all ten for good, and the fleet
stayed off until somebody ran reset-failed -- eight days after it went down.

wait-until-ready.sh replaces `check-throughput.sh || exit 1`. It checks disk,
network and throughput and does not return until all three pass. These cases
drive the real script: `df` and `sleep` are stubbed on PATH, the throughput
check is stubbed in RUNNER_DIR, and the network check opens real sockets on
loopback -- one listening, one not -- so the /dev/tcp code path actually runs.

`sleep` records each delay and, after a budget, kills the script. A script
that is still looping when the budget runs out was waiting, which is the
behaviour under test; one that exits on its own first was not.
"""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "runners/wait-until-ready.sh"
FAILURES: list[str] = []
BUDGET = 8


def listener() -> int:
    """A port that accepts connections, for the network-up case."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(16)

    def serve():
        while True:
            try:
                c, _ = s.accept()
                c.close()
            except OSError:
                return

    threading.Thread(target=serve, daemon=True).start()
    return s.getsockname()[1]


def closed_port() -> int:
    """A port nothing listens on, for the network-down case."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


OPEN, CLOSED = listener(), closed_port()

# Each stub pops its next value from a file, so a case can change the answer
# between iterations -- which is how recovery is tested.
POP = r'''pop() { f="$1"; v=$(head -n1 "$f"); [ "$(wc -l < "$f")" -gt 1 ] && sed -i.bak 1d "$f"; echo "$v"; }'''

DF = "#!/usr/bin/env bash\n" + POP + r'''
v=$(pop "$STATE/free")
[ "$v" = FAIL ] && exit 1
echo "Filesystem 1048576-blocks Used Available Capacity Mounted on"
echo "/dev/sda2 100604 0 $v 50% /"
'''
SLEEP = r'''#!/usr/bin/env bash
echo "$1" >> "$STATE/sleeps"
[ "$(wc -l < "$STATE/sleeps")" -ge "$BUDGET" ] && kill -TERM "$PPID"
exit 0
'''
THROUGHPUT = "#!/usr/bin/env bash\n" + POP + r'''
exit "$(pop "$STATE/tp")"
'''


def run(free: list[str], port: int, tp: list[str], diag_is_file: bool = False):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        state, stubs, rdir = tmp / "state", tmp / "stubs", tmp / "runner"
        for p in (state, stubs, rdir):
            p.mkdir()
        (state / "free").write_text("\n".join(free) + "\n")
        (state / "tp").write_text("\n".join(tp) + "\n")
        for name, body in (("df", DF), ("sleep", SLEEP)):
            (stubs / name).write_text(body)
            (stubs / name).chmod(0o755)
        # GNU timeout is on the runner VM and on CI, not on macOS. Stand in for
        # it only when it is missing, so CI still drives the real one.
        if not shutil.which("timeout"):
            (stubs / "timeout").write_text('#!/usr/bin/env bash\nshift\nexec "$@"\n')
            (stubs / "timeout").chmod(0o755)
        (rdir / "check-throughput.sh").write_text(THROUGHPUT)
        (rdir / "check-throughput.sh").chmod(0o755)
        if diag_is_file:
            (rdir / "_diag").write_text("not a directory")  # every write fails
        else:
            (rdir / "_diag").mkdir()

        p = subprocess.run(
            ["bash", str(SCRIPT)],
            env={**os.environ,
                 "PATH": f"{stubs}:{os.environ['PATH']}",
                 "STATE": str(state), "BUDGET": str(BUDGET),
                 "RUNNER_DIR": str(rdir),
                 "READY_HOST": "127.0.0.1", "READY_PORT": str(port)},
            capture_output=True, text=True, timeout=60)
        sleeps = (state / "sleeps").read_text().split() if (state / "sleeps").exists() else []
        status_file = rdir / "_diag" / "not-ready"
        status = status_file.read_text() if status_file.is_file() else ""
        return p.returncode, [int(s) for s in sleeps], status, p.stdout + p.stderr


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' -- {detail}'}")
    if not ok:
        FAILURES.append(name)


KILLED = -signal.SIGTERM
BACKOFF = [5, 10, 20, 40, 80, 160, 300, 300]

rc, sl, st, out = run(["50000"], OPEN, ["0"])
check("ready at once: returns 0, never sleeps, leaves no status",
      rc == 0 and sl == [] and st == "", f"rc={rc} sleeps={sl} status={st!r} {out[-200:]}")

rc, sl, st, out = run(["100"], OPEN, ["0"])
check("a full disk WAITS rather than exiting", rc == KILLED,
      f"rc={rc} -- it exited on its own, which is the restart-limit trap")
check("the wait backs off, doubling, capped at 300s", sl == BACKOFF, f"sleeps={sl}")
check("the reason is readable without sudo", st.split("  ", 1)[-1].startswith("disk:"), repr(st))

rc, sl, st, out = run(["50000"], CLOSED, ["0"])
check("no route to GitHub WAITS -- a cold boot before the network is up",
      rc == KILLED and "network:" in st, f"rc={rc} status={st!r}")

rc, sl, st, out = run(["50000"], OPEN, ["1"])
check("a starving link still refuses, now by waiting",
      rc == KILLED and "throughput:" in st, f"rc={rc} status={st!r}")

rc, sl, st, out = run(["100", "100", "50000"], OPEN, ["0"])
check("it rejoins on its own when the disk clears, and clears its status",
      rc == 0 and sl == [5, 10] and st == "", f"rc={rc} sleeps={sl} status={st!r}")

rc, sl, st, out = run(["FAIL"], OPEN, ["0"])
check("a df that fails stands aside instead of holding the runner back",
      rc == 0, f"rc={rc} -- could-not-measure must never ground the fleet")

rc, sl, st, out = run(["100"], CLOSED, ["1"])
check("disk is reported first: the cheapest check, and the one that kills runners",
      st.split("  ", 1)[-1].startswith("disk:"), repr(st))

rc, sl, st, out = run(["100"], OPEN, ["0"], diag_is_file=True)
check("when even the status file cannot be written, it keeps waiting",
      rc == KILLED and len(sl) == BUDGET,
      f"rc={rc} sleeps={len(sl)} -- a failed write ended the loop")


# --- and it comes first -----------------------------------------------------
# Waiting is only worth anything if nothing before it can fail for the same
# reason. Minting the App token needs the network, and it used to sit one line
# above the wait -- so a VM that booted before the office router died at the
# mint, never reaching the wait. Drive the real run-ephemeral.sh with every
# step stubbed to log its name, and read the order back.
EPHEMERAL = ROOT / "runners/run-ephemeral.sh"
LOG_STEP = '#!/usr/bin/env bash\necho {name} >> "$LOG"\n'


def order_of_steps() -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        rdir, stubs, log = tmp / "actions-runner-3", tmp / "stubs", tmp / "log"
        for p in (rdir, stubs):
            p.mkdir()
        log.touch()
        for name in ("wait-until-ready", "config", "run"):
            script = rdir / (name + ".sh")
            script.write_text(LOG_STEP.format(name=name))
            script.chmod(0o755)
        (rdir / "app-token.py").write_text(
            'import os\nopen(os.environ["LOG"], "a").write("token\\n")\nprint("ghs_test")\n')
        (stubs / "curl").write_text(
            '#!/usr/bin/env bash\necho curl >> "$LOG"\necho \'{"token": "reg"}\'\n')
        (stubs / "curl").chmod(0o755)
        p = subprocess.run(
            ["bash", str(EPHEMERAL)],
            env={**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}",
                 "LOG": str(log), "RUNNER_ORG": "acme", "RUNNER_GROUP": "private",
                 "RUNNER_DIR": str(rdir), "APP_ID": "1",
                 "APP_PRIVATE_KEY_PATH": "/dev/null", "GH_TOKEN": ""},
            capture_output=True, text=True, timeout=60)
        steps = log.read_text().split()
        if p.returncode != 0:
            steps.append(f"exit={p.returncode}: {(p.stdout + p.stderr)[-200:]}")
        return steps


steps = order_of_steps()
check("the wait comes before the token, the registration and the job",
      steps == ["wait-until-ready", "token", "curl", "config", "run"],
      f"order={steps}")

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)}: {', '.join(FAILURES)}")
    sys.exit(1)
print("\nOK: a runner that is not ready waits, backs off, and rejoins on its own")
