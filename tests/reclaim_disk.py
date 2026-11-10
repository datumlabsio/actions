#!/usr/bin/env python3
"""The disk reclaimer cleans every runner, the things that actually fill it,
and never anything under a running job.

    python3 tests/reclaim_disk.py

The version before this pruned Docker -- not installed on the runner VM --
and looked in /opt/actions-runner, which no runner had used since there were
ten of them. It cleaned nothing for six weeks, and on 2026-11-10 the disk was
100% full and every runner dead. The 65 GB that came back was download caches
in each runner's home and the runner's own leftover versions.

Each case builds a fake /opt: three runners, one mid-job, a directory that
looks like a runner but is not, every kind of cache, and runner versions old,
current and still unpacking. `df` reports a usage that drops as the right
things are deleted, so each tier is reached the way it would be for real.

The busy runner is actions-runner-10, deliberately: if the mid-job check lost
the boundary after the directory, actions-runner-1 would be mistaken for it.

PATH is built from a whitelist of real tools plus the stubs, so no real
`docker` or `pgrep` is ever reached from here.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "runners/reclaim-disk.sh"
FAILURES: list[str] = []
DAY = 86400
TOOLS = ["bash", "awk", "find", "rm", "readlink", "date", "sed", "head", "wc",
         "grep", "mkdir", "cat", "env", "sort", "printf", "tr"]

# Usage falls as the right things go: runner-2's caches first, then its .local.
DF = r'''#!/usr/bin/env bash
if   [ -e "$R/actions-runner-2/.pnpm-store" ]; then p=$PCT_CACHES
elif [ -e "$R/actions-runner-2/.local" ];      then p=$PCT_LOCAL
else p=$PCT_CLEAN; fi
echo "Filesystem 1024-blocks Used Available Capacity Mounted on"
echo "/dev/sda2 100 0 0 ${p}% /"
'''
# A real process table of one: runner-10 is mid-job. The pattern the script
# passes is matched against it with grep -E, so the regex itself is under test.
PGREP = r'''#!/usr/bin/env bash
pat="${@: -1}"
printf '%s\n' "$R/actions-runner-10/bin/Runner.Worker spawnclient 101 102" | grep -qE -- "$pat"
'''
DOCKER = '#!/usr/bin/env bash\necho "$*" >> "$R/../docker-calls"\n'

RUNNER_LAYOUT = [
    ".pnpm-store/v3/x", ".cache/uv/x", ".npm/_cacache/x", "_work/_tool/uv/x",
    "_work/polaris/polaris/x", ".local/pipx/x",
    "bin.2.338.0/Runner.Listener", "externals.2.338.0/node/x",   # in use
    "bin.2.337.0/Runner.Listener", "externals.2.337.0/node/x",   # left over
    "bin.2.339.0/Runner.Listener",                               # still unpacking
    "_diag/old.log", "_diag/new.log",
]


def build(root: Path) -> None:
    now = time.time()
    for name in ("actions-runner-1", "actions-runner-2", "actions-runner-10"):
        d = root / name
        for rel in RUNNER_LAYOUT:
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text("x")
        (d / "run-ephemeral.sh").write_text("#!/bin/sh\n")
        (d / "bin").symlink_to(d / "bin.2.338.0")              # absolute, as the updater writes it
        for old in ("bin.2.337.0", "externals.2.337.0"):
            os.utime(d / old, (now - 3 * DAY, now - 3 * DAY))
        for keep in ("bin.2.338.0", "externals.2.338.0"):       # current, AND old
            os.utime(d / keep, (now - 30 * DAY, now - 30 * DAY))
        os.utime(d / "_diag/old.log", (now - 10 * DAY, now - 10 * DAY))
    # Looks like a runner, is not one: no run-ephemeral.sh.
    t = root / "actions-runner-template"
    (t / ".pnpm-store").mkdir(parents=True)
    (t / "bin.2.337.0").mkdir()
    os.utime(t / "bin.2.337.0", (now - 3 * DAY, now - 3 * DAY))


def run(pct_caches: int, pct_local: int, pct_clean: int, docker: bool = False,
        tweak=None):
    tmp = Path(tempfile.mkdtemp())
    root, stubs, tools = tmp / "opt", tmp / "stubs", tmp / "tools"
    for p in (root, stubs, tools):
        p.mkdir()
    build(root)
    if tweak:
        tweak(root)
    for t in TOOLS:
        real = shutil.which(t)
        if real:
            (tools / t).symlink_to(real)
    stubs_list = [("df", DF), ("pgrep", PGREP)] + ([("docker", DOCKER)] if docker else [])
    for name, body in stubs_list:
        (stubs / name).write_text(body)
        (stubs / name).chmod(0o755)
    p = subprocess.run(
        [shutil.which("bash"), str(SCRIPT)],
        env={"PATH": f"{stubs}:{tools}", "R": str(root), "RUNNER_ROOT": str(root),
             "PCT_CACHES": str(pct_caches), "PCT_LOCAL": str(pct_local),
             "PCT_CLEAN": str(pct_clean), "HOME": str(tmp)},
        capture_output=True, text=True, timeout=60)
    calls = (tmp / "docker-calls").read_text() if (tmp / "docker-calls").exists() else ""
    return p.returncode, root, p.stdout + p.stderr, calls


def has(root: Path, runner: str, rel: str) -> bool:
    return (root / runner / rel).exists()


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' -- {detail}'}")
    if not ok:
        FAILURES.append(name)


CACHES = [".pnpm-store", ".cache", ".npm/_cacache", "_work/_tool"]

# --- a healthy disk: only what is never needed again ----------------------
rc, r, out, _ = run(50, 50, 50)
check("healthy disk: exits 0", rc == 0, out[-300:])
check("every runner's leftover version is removed",
      all(not has(r, n, v) for n in ("actions-runner-1", "actions-runner-2", "actions-runner-10")
          for v in ("bin.2.337.0", "externals.2.337.0")))
check("the version in use stays, however old it is",
      all(has(r, n, v) for n in ("actions-runner-1", "actions-runner-2", "actions-runner-10")
          for v in ("bin.2.338.0", "externals.2.338.0")))
check("a version still unpacking is never touched",
      all(has(r, n, "bin.2.339.0") for n in ("actions-runner-1", "actions-runner-2")))
check("diag logs over a week go, recent ones stay",
      not has(r, "actions-runner-1", "_diag/old.log") and has(r, "actions-runner-1", "_diag/new.log"))
check("caches are left warm while the disk is fine",
      all(has(r, "actions-runner-2", c) for c in CACHES))
check("a directory without run-ephemeral.sh is not a runner, and is not touched",
      has(r, "actions-runner-template", ".pnpm-store") and has(r, "actions-runner-template", "bin.2.337.0"))

# --- warn: the caches go, from idle runners only --------------------------
rc, r, out, _ = run(75, 50, 50)
check("warn: idle runners lose their download and tool caches",
      all(not has(r, n, c) for n in ("actions-runner-1", "actions-runner-2") for c in CACHES),
      out[-300:])
check("warn: the work tree and pipx's tools are kept",
      has(r, "actions-runner-1", "_work/polaris") and has(r, "actions-runner-1", ".local"))
check("warn: the runner mid-job keeps every cache",
      all(has(r, "actions-runner-10", c) for c in CACHES))
check("warn: a lookalike without run-ephemeral.sh still keeps its caches",
      has(r, "actions-runner-template", ".pnpm-store"),
      "checked at warn, not only when the disk is healthy -- at 50% nothing is "
      "deleted anyway, so that check could not fail")
check("actions-runner-1 is not mistaken for actions-runner-10",
      not has(r, "actions-runner-1", ".pnpm-store"),
      "the mid-job check matched the wrong runner")

# --- critical: everything an idle runner can rebuild ----------------------
rc, r, out, _ = run(90, 88, 40)
check("critical: idle runners lose their work tree and pipx's tools",
      all(not has(r, n, x) for n in ("actions-runner-1", "actions-runner-2")
          for x in ("_work/polaris", ".local")), out[-300:])
check("critical: still nothing under the running job",
      has(r, "actions-runner-10", "_work/polaris") and has(r, "actions-runner-10", ".local"))
check("critical, and cleaning was enough: exits 0", rc == 0, f"rc={rc}")

rc, r, out, _ = run(90, 88, 90)
check("critical, and cleaning was not enough: exits 1 and says where to look",
      rc == 1 and "du -xsh" in out, f"rc={rc} {out[-200:]}")

# --- odd layouts: when unsure, leave it ------------------------------------
def real_bin_dir(root: Path) -> None:
    d = root / "actions-runner-1"
    (d / "bin").unlink()
    (d / "bin").mkdir()

rc, r, out, _ = run(50, 50, 50, tweak=real_bin_dir)
check("a runner that never updated keeps every version directory",
      has(r, "actions-runner-1", "bin.2.337.0"), "with no symlink, nothing says which is current")

def odd_link(root: Path) -> None:
    d = root / "actions-runner-1"
    (d / "bin").unlink()
    (d / "bin").symlink_to(d / "bin-custom")

rc, r, out, _ = run(50, 50, 50, tweak=odd_link)
check("a symlink that does not end in a version is not guessed at",
      has(r, "actions-runner-1", "bin.2.338.0") and has(r, "actions-runner-1", "bin.2.337.0"))

# --- docker: only if it exists ---------------------------------------------
rc, r, out, calls = run(50, 50, 50)
check("no docker on the box: no docker anything, and still exits 0", rc == 0 and calls == "")
rc, r, out, calls = run(50, 50, 50, docker=True)
check("docker present: its prune still runs", "container prune" in calls, repr(calls))

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)}: {', '.join(FAILURES)}")
    sys.exit(1)
print("\nOK: every runner, the right things, never under a running job")
