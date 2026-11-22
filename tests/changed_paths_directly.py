#!/usr/bin/env python3
"""`changed-directly` names what the diff actually touched; `changed` names
what must run.

They differ in exactly one situation, and it is the one that costs money: a
shared root file changed, so run-all-on fires, `changed` becomes every folder,
and seven container images rebuild because somebody edited a workflow comment.

A job may key off `changed-directly` ONLY when a shared-root change provably
cannot break it. The default stays `changed`, because the failure mode of
getting this wrong is a config change merging green untested — far worse than
a slow pull request.

Driven with fabricated diffs rather than this repository's own history: whether
run-all fires on a real pull request depends on what that pull request touched,
so an assertion against it is true by accident.

Run: python3 tests/changed_paths_directly.py
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

WF = (pathlib.Path(__file__).resolve().parents[1]
      / ".github" / "workflows" / "changed-paths.yml")

# Lift the detect script out of the workflow, and cut the two lines that reach
# for GitHub context so it can run here. Everything that decides is kept.
raw = WF.read_text()
m = re.search(r"^        run: \|\n(.*?)(?=\n      - name:|\n  [a-z]|\Z)", raw, re.S | re.M)
assert m, "could not find the detect script"
SCRIPT = "\n".join(l[10:] if l.startswith(" " * 10) else l
                   for l in m.group(1).splitlines())
SCRIPT = SCRIPT.replace(
    'if [ "${{ github.event_name }}" = "pull_request" ]; then\n'
    '  base="${{ github.event.pull_request.base.sha }}"\n'
    'else\n'
    '  base="${{ github.event.before }}"\n'
    'fi', 'base="$FAKE_BASE"')
assert "${{" not in SCRIPT, f"unsubstituted expression left in the script"

PATHS = "web-app introspector gitops"
failures = []


def run(files, run_all_on, base="HEAD~1"):
    """Execute the real detect logic against a fabricated `git diff`."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        # A fake `git`: cat-file succeeds, diff prints the files we chose.
        git = tmp / "git"
        git.write_text("#!/usr/bin/env bash\n"
                       'case "$1" in\n'
                       '  cat-file) exit 0 ;;\n'
                       f'  diff) printf \'%s\\n\' {files or "\'\'"} ;;\n'
                       'esac\n')
        git.chmod(0o755)
        out = tmp / "out"
        out.write_text("")
        env = dict(os.environ, PATH=f"{tmp}:{os.environ['PATH']}",
                   PATHS=PATHS, RUN_ALL_ON=run_all_on,
                   FAKE_BASE=base, GITHUB_OUTPUT=str(out))
        p = subprocess.run(["bash", "-c", SCRIPT], capture_output=True,
                           text=True, env=env)
        if p.returncode != 0:
            failures.append(f"script exited {p.returncode}: {p.stderr[-200:]}")
        got = dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l)
        return got


def check(cond, msg):
    if not cond:
        failures.append(msg)


# --- run-all fires: the two outputs must diverge ---------------------------
r = run("'.github/workflows/ci.yml' 'web-app/src/a.ts'", ".github/")
check(r.get("changed") == PATHS,
      f"run-all fired but changed={r.get('changed')!r}, expected every folder")
check(r.get("changed-directly") == "web-app",
      f"changed-directly={r.get('changed-directly')!r}, expected just web-app — "
      f"this is the whole point: the diff touched one component")

# The expensive case. A workflow edit alone must name NO component directly.
r = run("'.github/workflows/ci.yml'", ".github/")
check(r.get("changed") == PATHS, "run-all must still run everything")
check(r.get("changed-directly") == "",
      f"a CI-file-only change named {r.get('changed-directly')!r} as directly "
      f"changed; it touched no component")

# --- run-all does not fire: they must agree --------------------------------
r = run("'introspector/x.py' 'gitops/y.yaml'", ".github/")
check(r.get("changed") == r.get("changed-directly") == "introspector gitops",
      f"without run-all the outputs must match: changed={r.get('changed')!r} "
      f"direct={r.get('changed-directly')!r}")

r = run("'README.md'", ".github/")
check(r.get("changed") == "" and r.get("changed-directly") == "",
      "an unrelated file must name nothing")
check(r.get("any") == "false", f"any={r.get('any')!r}, expected false")

# --- no usable base: everything, both ways ---------------------------------
# Guessing narrower here would skip the gate this branch exists to protect.
r = run("''", ".github/", base="")
check(r.get("changed") == PATHS and r.get("changed-directly") == PATHS,
      f"with no base both outputs must be every folder, got "
      f"changed={r.get('changed')!r} direct={r.get('changed-directly')!r}")

# --- the invariant a caller relies on --------------------------------------
for files in ["'.github/workflows/ci.yml' 'gitops/a.yaml'", "'web-app/b.ts'",
              "'README.md'", "'.github/x' 'introspector/c.py' 'web-app/d.ts'"]:
    r = run(files, ".github/")
    direct = set((r.get("changed-directly") or "").split())
    changed = set((r.get("changed") or "").split())
    check(direct <= changed,
          f"changed-directly is not a subset of changed for {files}: "
          f"{direct - changed} would run a job the safety catch excluded")

if failures:
    print("\n".join(f"FAIL  {f}" for f in failures))
    sys.exit(1)
print("PASS  changed-directly names the real diff; changed still runs everything")
