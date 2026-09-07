#!/usr/bin/env python3
"""The audit grades OUR caller, and a stale pin is a finding.

    python3 tests/audit_reads_the_datum_caller.py

Two bugs, both of which made the audit report the opposite of the truth about
the repositories we had actually adopted.

**It read `ci.yml`.** A retrofit ships `datum-ci.yml`, on purpose, so it cannot
collide with the CI an existing repository already has. So the audit graded
every adopted repo on a file that is not ours. `dl-assessment-platform` came
back as running no Datum workflow and no security baseline, while
`datum-ci.yml` sat beside it doing both. And where a repo had no `ci.yml` at
all the SECURITY check was never reached -- an unrun check reports as a pass.

**The pin check was `startswith("v")`.** `polaris` audited CONFORMANT while
pinned thirteen releases behind, without the fix that stopped a real private
key being suppressed. A conformance report that cannot see a stale pin is
worse than no report, because somebody acts on it.

No network. The API layer is stubbed, so these are assertions about the
grading logic rather than about the fleet on the day they run.
"""
from __future__ import annotations

import importlib.util
import sys
import urllib.error
import urllib.request
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "ca", Path(__file__).resolve().parent / "conformance_audit.py")
ca = importlib.util.module_from_spec(spec)
sys.modules["ca"] = ca
spec.loader.exec_module(ca)

FAILURES: list[str] = []

CURRENT = "v9.9.9"

GOOD_CALLER = """
name: datum-ci
on: pull_request
jobs:
  security:
    uses: datumlabsio/actions/.github/workflows/security-baseline.yml@%s
""".strip()

# What a repository's OWN pipeline looks like: real steps, no Datum call. Being
# graded on this file is the bug.
THEIR_OWN_CI = """
name: ci
on: pull_request
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: pnpm build
""".strip()


def stub(files: dict[str, str], latest: str | None = CURRENT,
         rules_forbidden: bool = False):
    """Serve `files`; everything else absent. Settings all pass, so a finding
    that appears is attributable to the caller logic and nothing else."""
    ca.file_text = lambda repo, path: files.get(path)

    def api(path: str, **kw):
        if path.endswith("/rules/branches/main"):
            if rules_forbidden:
                return ca.FORBIDDEN
            return [{"type": t} for t in ("pull_request", "deletion", "non_fast_forward")]
        if "/teams/" in path:
            return {"permissions": {"push": True}}
        if path == "/repos/datumlabsio/demo":
            return {"default_branch": "main"}
        return None

    ca.api = api
    ca._LATEST = latest
    return ca.audit("datumlabsio/demo", {})


def base(**extra) -> dict[str, str]:
    f = {
        ".copier-answers.yml": "archetype: dbt-project\n",
        "CLAUDE.md": "x", "README.md": "x",
        ".github/CODEOWNERS": "* @datumlabsio/datum-core\n",
        ".pre-commit-config.yaml": "x",
    }
    f.update(extra)
    return f


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' — {detail}'}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    # --- the retrofit shape: datum-ci.yml is the caller ------------------
    r = stub(base(**{".github/workflows/datum-ci.yml": GOOD_CALLER % CURRENT}))
    check("datum-ci.yml alone is read as the caller",
          r.failed == [], f"unexpected: {r.failed}")

    # --- the shape that produced three false findings on a real repo -----
    r = stub(base(**{".github/workflows/datum-ci.yml": GOOD_CALLER % CURRENT,
                     ".github/workflows/ci.yml": THEIR_OWN_CI}))
    check("a repo's own ci.yml beside ours is not graded",
          r.failed == [], f"graded their pipeline: {r.failed}")

    # --- the scaffold-born shape still works ----------------------------
    r = stub(base(**{".github/workflows/ci.yml": GOOD_CALLER % CURRENT}))
    check("ci.yml is still read when there is no datum-ci.yml",
          r.failed == [], f"unexpected: {r.failed}")

    # --- no caller at all: SECURITY must be REPORTED, not skipped -------
    r = stub(base())
    check("no caller fails the caller check", ca.THIN_CALLER in r.failed)
    check("no caller fails SECURITY rather than silently passing",
          ca.SECURITY in r.failed,
          "security was never evaluated, which reads as a pass")

    # --- pin freshness ---------------------------------------------------
    r = stub(base(**{".github/workflows/datum-ci.yml": GOOD_CALLER % "v0.27.1"}))
    check("a stale pin is a finding", ca.THIN_CALLER in r.failed)
    check("the finding names both versions",
          any("v0.27.1" in d and CURRENT in d for d in r.detail),
          f"detail: {r.detail}")

    r = stub(base(**{".github/workflows/datum-ci.yml": GOOD_CALLER % CURRENT}))
    check("the current pin is not a finding", r.failed == [], f"unexpected: {r.failed}")

    # --- fail open: our own API error must not fail the whole fleet -----
    r = stub(base(**{".github/workflows/datum-ci.yml": GOOD_CALLER % "v0.27.1"}),
             latest=None)
    check("an unreadable release list reports no stale pin",
          r.failed == [], f"failed the repo on our own API error: {r.failed}")

    # --- 403 is not 404 --------------------------------------------------
    #
    # The rules endpoint answers 403 on any repository we do not administer,
    # which is every repository in a client's organisation. `api` re-raised
    # anything that was not 404, so ONE external repo aborted the whole run and
    # took every internal report with it -- verified against
    # EmberAssetManagement/ecp-frontend, which died on an uncaught HTTPError.
    r = stub(base(**{".github/workflows/datum-ci.yml": GOOD_CALLER % CURRENT}),
             rules_forbidden=True)
    check("a 403 on the rules endpoint does not raise", True)
    check("403 is reported against branch protection", ca.PROTECTION in r.failed)
    detail = " ".join(r.detail)
    check("403 reads as unverified, NOT as missing",
          "Unverified, not missing" in detail and "is missing:" not in detail,
          f"claimed absence it never checked: {detail}")

    # A 403 must not become a second, invented finding somewhere else.
    check("403 costs exactly one finding", r.failed == [ca.PROTECTION],
          f"{r.failed}")

    # --- and the mapping itself, through api() ---------------------------
    #
    # The cases above stub `api` and so assert only what happens DOWNSTREAM of
    # the status code. Collapsing 403 into `return None` passed all of them.
    # This drives the real function, because the bug being fixed was an
    # uncaught HTTPError inside it.
    def raises(code: int):
        def urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                "https://api.github.com/x", code, "nope", {}, None)
        return urlopen

    real_api = ca.api  # the stubs above replaced it
    spec.loader.exec_module(ca)          # restore the module's own api()
    saved = urllib.request.urlopen
    try:
        urllib.request.urlopen = raises(403)
        check("api() maps 403 to FORBIDDEN, not to None",
              ca.api("/x") is ca.FORBIDDEN,
              "a 403 that returns None makes every unreadable check read as absent")

        urllib.request.urlopen = raises(404)
        check("api() still maps 404 to None", ca.api("/x") is None)

        urllib.request.urlopen = raises(500)
        try:
            ca.api("/x")
            check("api() still raises on a real error", False,
                  "a 500 was swallowed — the audit would report on nothing")
        except urllib.error.HTTPError:
            check("api() still raises on a real error", True)
    finally:
        urllib.request.urlopen = saved
        ca.api = real_api

    if FAILURES:
        print(f"\nFAIL: {len(FAILURES)} case(s): {', '.join(FAILURES)}")
        return 1
    print("\nOK: 16 cases — the caller we ship, the version it pins, "
          "and the difference between may-not-look and not-there")
    return 0


if __name__ == "__main__":
    sys.exit(main())
