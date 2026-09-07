#!/usr/bin/env python3
"""An external adopter is audited on what they adopted, and nothing else.

    python3 tests/baseline_only_tier.py

A repository outside our organisation merges ONE file and is told, in writing,
that it "changes nothing about how this repository is built". Auditing it
against the seven §12 checks reported four findings -- no `.copier-answers.yml`,
no `CLAUDE.md`, no `CODEOWNERS`, no `.pre-commit-config.yaml` -- none of which
that team ever agreed to, none fixable without adopting the whole standard, and
all of which the SCHEDULED run would eventually file as issues in their tracker.

A finding nobody can act on is a finding everybody learns to scroll past, and it
takes the real ones with it.

So the tier grades the four things they did adopt. The fourth has no §12
equivalent and is the reason this is worth more than a file-presence sweep:
**whether the gate has ever actually run.** An organisation set to "Allow select
actions" without us on the allowlist SKIPS the workflow, and a skipped workflow
reports success -- so a repository can sit in the register for a year looking
adopted while the gate has never once executed.

No network: the API layer is stubbed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "ca", Path(__file__).resolve().parent / "conformance_audit.py")
ca = importlib.util.module_from_spec(spec)
sys.modules["ca"] = ca
spec.loader.exec_module(ca)

FAILURES: list[str] = []
CURRENT = "v9.9.9"

CALLER = ("jobs:\n  security:\n    uses: datumlabsio/actions/.github/workflows/"
          "security-baseline.yml@%s\n")


def stub(workflows: dict[str, str], *, state="active", runs=1,
         conclusion="success", latest=CURRENT):
    """`workflows` maps a filename under .github/workflows to its content."""
    files = {f".github/workflows/{n}": t for n, t in workflows.items()}
    ca.file_text = lambda repo, path: files.get(path)

    def api(path: str, **kw):
        if path == "/repos/o/r":
            return {"default_branch": "main"}
        if path.endswith("/contents/.github/workflows"):
            return [{"type": "file", "name": n} for n in workflows]
        if "/actions/workflows/" in path and path.endswith("/runs?per_page=1"):
            if not runs:
                return {"workflow_runs": []}
            return {"workflow_runs": [{"created_at": "2026-09-07T00:00:00Z",
                                       "conclusion": conclusion}]}
        if "/actions/workflows/" in path:
            return {"state": state}
        return None

    ca.api = api
    ca._LATEST = latest
    return ca.audit_baseline("o/r")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' — {detail}'}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    # --- the happy path ---------------------------------------------------
    r = stub({"datum-police.yml": CALLER % CURRENT})
    check("a current, pinned, running baseline is conformant",
          r.failed == [], f"unexpected: {r.failed}")
    check("the tier is recorded on the report", r.tier == "baseline", r.tier)

    # --- it is NOT graded on §12 -----------------------------------------
    #
    # The whole point. The stub serves no CLAUDE.md, no CODEOWNERS, no
    # .copier-answers.yml, no .pre-commit-config.yaml -- and that is fine.
    check("no §12 check is applied to a baseline repo",
          not ({ca.BORN, ca.FILES, ca.PRECOMMIT, ca.DOCS, ca.PROTECTION,
                ca.THIN_CALLER} & set(r.failed)),
          f"graded on items they never adopted: {r.failed}")

    # --- the file is gone -------------------------------------------------
    r = stub({"deploy.yml": "jobs:\n  x:\n    steps:\n      - run: echo\n"})
    check("a repo with no baseline call fails `called`", ca.B_CALLER in r.failed)
    check("and does not cascade into three more findings",
          r.failed == [ca.B_CALLER], f"{r.failed}")
    # Without the early return the function runs on through an empty call list
    # and reports "called by:" with nothing after it -- a report line asserting
    # the opposite of the finding directly above it.
    check("and does not then claim it is called by nothing",
          not any(d.startswith("- called by:") for d in r.detail), f"{r.detail}")

    # --- the filename is not hardcoded ------------------------------------
    r = stub({"security.yml": CALLER % CURRENT})
    check("the call is found under any workflow filename",
          r.failed == [], f"renaming the file broke detection: {r.failed}")

    # --- pinning ----------------------------------------------------------
    r = stub({"datum-police.yml": CALLER % "main"})
    check("a moving ref fails `pinned`", ca.B_PINNED in r.failed)
    check("a moving ref is not also reported as a stale pin",
          ca.B_CURRENT not in r.failed, f"{r.failed}")

    r = stub({"datum-police.yml": CALLER % "v1.1.0"})
    check("a stale pin fails `current`", ca.B_CURRENT in r.failed)
    check("the stale finding names both versions",
          any("v1.1.0" in d and CURRENT in d for d in r.detail), f"{r.detail}")

    r = stub({"datum-police.yml": CALLER % "v1.1.0"}, latest=None)
    check("an unreadable release list reports no stale pin",
          r.failed == [], f"failed on our own API error: {r.failed}")

    # --- has it run? ------------------------------------------------------
    r = stub({"datum-police.yml": CALLER % CURRENT}, runs=0)
    check("a workflow that has never run fails `ran`", ca.B_RAN in r.failed)

    r = stub({"datum-police.yml": CALLER % CURRENT}, state="disabled_manually")
    check("a disabled workflow fails `ran`", ca.B_RAN in r.failed)
    check("and says it is disabled rather than never-run",
          any("disabled_manually" in d for d in r.detail), f"{r.detail}")

    # --- THEIR findings are not OUR conformance ---------------------------
    #
    # A red run means the gate is working. Counting it as a conformance failure
    # would punish the repo for the thing we installed it to do.
    r = stub({"datum-police.yml": CALLER % CURRENT}, conclusion="failure")
    check("a FAILING run is not a conformance finding",
          r.failed == [], f"graded them on their own findings: {r.failed}")

    # --- argument splitting ----------------------------------------------
    full, base = ca.split_args(["a/b", "--baseline-only", "c/d", "e/f"])
    check("--baseline-only splits the repo list", full == ["a/b"] and base == ["c/d", "e/f"],
          f"{full} {base}")
    full, base = ca.split_args(["a/b", "c/d"])
    check("no flag means every repo is full-tier", full == ["a/b", "c/d"] and base == [])

    # --- the report keeps the tiers apart --------------------------------
    good = ca.Report(repo="o/ext", tier="baseline", archetype="baseline-only")
    internal = ca.Report(repo="datumlabsio/x", owner_team="@datumlabsio/datum-core")
    md = ca.summarise([internal, good])
    check("the report renders a section per tier",
          "Adopted the standard" in md and "security baseline only" in md, md[:200])
    body = md.split("security baseline only")[0]
    check("a baseline repo is not listed in the §12 table",
          "o/ext" not in body, "it was graded in the wrong table")

    if FAILURES:
        print(f"\nFAIL: {len(FAILURES)} case(s): {', '.join(FAILURES)}")
        return 1
    print(f"\nOK: 20 cases — what they adopted, and whether it ever ran")
    return 0


if __name__ == "__main__":
    sys.exit(main())
