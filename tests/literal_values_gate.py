#!/usr/bin/env python3
"""The gate reads prose as well as workflows, and `#` means different things.

    python3 tests/literal_values_gate.py

`no_literal_env_values.py` grew from workflows to `docs/`, and the move has one
trap in it: the allowance for "a comment explaining the rule itself" was
`^\\s*#\\s`. In YAML that is a comment. In Markdown it is a level-one heading --
so shared, that allowance would have exempted the single most prominent line on
every page. It was found by probing, not by a test, which is why this file
exists.

FIXTURES ARE GENERATED AT RUN TIME, never committed. A fixture that trips the
client-name rule has to contain a client name, and committing one to a public
repository to prove we do not commit them to a public repository is a joke that
tells itself. They live in a temp directory for the length of one assertion.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import no_literal_env_values as gate  # noqa: E402

CLIENT = "ember"  # on the rule's list; only ever written to a temp file
FAILURES: list[str] = []


def scan(files: dict[str, str]) -> list[str]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for name, body in files.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        return gate.scan(root)


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' — {detail}'}")
    if not ok:
        FAILURES.append(name)


# --- the regression this file was written for -----------------------------
found = scan({"a.md": f"# {CLIENT.title()} adoption notes\n"})
check("a client name in a MARKDOWN HEADING is caught",
      len(found) == 1 and "client name" in found[0],
      "`# ` is a heading here, not a comment — the loudest line on the page")

found = scan({"a.md": f"#  {CLIENT} again\n## {CLIENT} twice\n"})
check("...at any heading level, and indented", len(found) == 2, str(found))

# A finding has to say what to DO. The rule name alone sends someone hunting.
check("...and the finding says how to fix it, not just what matched",
      "use a neutral fixture name" in found[0], found[0])

# --- but the YAML allowance it came from still works ----------------------
found = scan({"w.yml": f"# never name a client, e.g. {CLIENT}, in shared CI\n"})
check("a YAML comment explaining the rule is still allowed", found == [], str(found))

found = scan({"w.yml": f"  name: deploy to {CLIENT}\n"})
check("...but only in a comment, not in YAML content",
      len(found) == 1, str(found))

# --- prose gets scanned at all --------------------------------------------
found = scan({"d.md": f"We adopted `{CLIENT.title()}Assets/app` on Monday.\n"})
check("markdown is scanned, not just .yml/.yaml", len(found) == 1, str(found))

found = scan({"n.txt": f"{CLIENT}\n", "n.rst": f"{CLIENT}\n"})
check("other extensions are not scanned, and that is reported",
      len(found) == 1 and "no .yml, .yaml or .md files found" in found[0], str(found))

# --- the other rules reach prose too --------------------------------------
found = scan({"d.md": "SSH to 192.168.100.46 and run the installer.\n"})
check("an internal IP in prose is caught", len(found) == 1
      and "IP address" in found[0], str(found))
found = scan({"d.md": "Runner pinned to v2.337.0, config v1.2.3.\n"})
check("...and a version string is not mistaken for one", found == [], str(found))

found = scan({"d.md": "Grant it on projects/some-proj/locations/global.\n"})
check("a workload identity path in prose is caught", len(found) == 1, str(found))

# --- allowances must not swallow the rest of the line ---------------------
sha = "a" * 40
found = scan({"w.yml": f"      uses: actions/checkout@{sha}\n"})
check("a SHA-pinned action is allowed", found == [], str(found))
found = scan({"w.yml": f"      uses: {CLIENT}/act@{sha}  # {CLIENT}\n"})
check("...but the SHA allowance is line-wide, and that is a known hole",
      found == [],
      "documented, not asserted away: tighten it if a client name ever "
      "ships on a pinned-action line")

# --- the trailing-boundary fix, and what it costs -------------------------
found = scan({"d.md": f"We adopted `{CLIENT.title()}AssetManagement/app`.\n"})
check("a client name glued to an org suffix is caught",
      len(found) == 1,
      "`EmberAssetManagement` escaped a trailing \\b — the register row was "
      "only ever caught by the bare `Ember` later on the same line")
found = scan({"d.md": "member remember membership assembler November\n"})
check("...and the leading boundary still protects ordinary words", found == [],
      str(found))
found = scan({"d.md": "Built with Ember.js.\n"})
check("KNOWN false positive: a framework sharing a client's name is flagged",
      len(found) == 1,
      "deliberate. A false positive costs a reword; a false negative is a leak")

# --- clean input ----------------------------------------------------------
found = scan({"d.md": "# Adopting a repo\n\nPass the account as an input.\n",
              "w.yml": "on: [push]\n"})
check("a clean tree reports nothing", found == [], str(found))

# --- the entry point still exits non-zero ---------------------------------
import subprocess  # noqa: E402
with tempfile.TemporaryDirectory() as td:
    (Path(td) / "a.md").write_text(f"# {CLIENT}\n")
    r = subprocess.run([sys.executable, str(Path(__file__).parent
                                            / "no_literal_env_values.py"), td],
                       capture_output=True, text=True)
check("the script exits 1 and names the file and line",
      r.returncode == 1 and "a.md:1" in r.stdout, f"exit {r.returncode}")

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)}: {', '.join(FAILURES)}")
    sys.exit(1)
print("\nOK: prose is scanned, and `#` is read per file type")
