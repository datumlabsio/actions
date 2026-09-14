#!/usr/bin/env python3
"""The filing step tells Slack enough to act, and never the secret itself.

    python3 tests/violation_filing.py

The whole point of this path is that a blocked merge does not say "rotate" to
anybody. So the two things worth testing are what the issue CARRIES and what it
must never carry -- plus the dedupe, because a pull request pushed five times
fails five times, and five identical issues is how a channel gets muted.

The step is read out of the workflow rather than copied here. A copy drifts,
and the copy that drifts is the one that still passes.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
WORKFLOW = HERE.parent / ".github/workflows/security-baseline.yml"
FAILURES: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {what}")
    if not ok:
        FAILURES.append(what)


def load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def step(job: dict, prefix: str) -> dict:
    for s in job["steps"]:
        if s.get("name", "").startswith(prefix):
            return s
    sys.exit(f"FAIL: no step starting {prefix!r} -- was it renamed?")


def main() -> int:
    wf = load()

    print("the job only runs when a secret was actually found")
    job = wf["jobs"].get("violation")
    if job is None:
        sys.exit("FAIL: no `violation` job")
    cond = job["if"]
    check("needs.secrets.result == 'failure'" in cond,
          "fires on the secrets job failing, not on any failure")
    check("always()" in cond,
          "always() present, or `needs` on a failed job skips it entirely")
    check(job["needs"] == "secrets" or "secrets" in job["needs"],
          "depends on the secrets job")
    # A separate job is the point: if filing breaks, the finding must stay red.
    # Assert the INVARIANT, not the shape -- the first version of this looked
    # for the word "violation" in the secrets job, which a mutation that moved
    # the filing there would sail straight past.
    filers = [
        name for name, j in wf["jobs"].items()
        if "gh issue create" in str(j.get("steps", ""))
    ]
    check(filers == ["violation"],
          f"exactly one job files issues, and it is `violation` (found {filers})")
    check(job.get("permissions") == {},
          "no GITHUB_TOKEN permissions -- it uses the minted token only")

    print("\nthe token can only touch the mailbox")
    mint = step(job, "Mint a token")
    check(mint["with"].get("repositories") == "${{ inputs.violation-repo }}",
          "token is scoped to the mailbox repository")
    check("bcd2ba49218906704ab6c1aa796996da409d3eb1" in mint["uses"],
          "create-github-app-token is pinned to a sha")

    print("\nabsent credentials are not an error")
    creds = step(job, "Can this repository file")
    check("present=false" in creds["run"] and "exit 1" not in creds["run"],
          "an external caller with no credentials exits clean")
    for s in job["steps"]:
        if s.get("id") == "creds":
            continue
        check(s.get("if", "").strip() == "steps.creds.outputs.present == 'true'",
              f"{s['name']!r} is gated on the credentials being present")

    print("\nthe issue says what to do")
    filing = step(job, "File it")
    body = filing["run"]
    for phrase, why in [
        ("Rotate the credential first", "tells the reader to rotate"),
        ("Deleting the line does not delete it", "kills the wrong remedy"),
        ("not when the pull request is fixed", "separates rotation from the fix"),
    ]:
        # Case-insensitive: this asserts the sentence is there, not how it is
        # capitalised at the start of a line.
        check(phrase.lower() in body.lower(), why)

    print("\nand never the secret")
    env = filing.get("env", {})
    allowed = {"GH_TOKEN", "MAILBOX", "SOURCE", "PR", "PR_URL", "RUN_URL"}
    check(set(env) <= allowed,
          f"no unexpected values reach the issue: {sorted(set(env) - allowed)}")
    # gitleaks writes its findings to the log and to no file this job can read,
    # but an added `cat` of a report would be invisible in review. Comments are
    # stripped WHOLE -- a first pass blanked only the "# " marker, so a comment
    # explaining why we do not read gitleaks output failed the check about not
    # reading gitleaks output.
    code = "\n".join(
        ln for ln in body.split("\n") if not ln.lstrip().startswith("#")
    )
    for bad in ("gitleaks", "$RUNNER_TEMP", "datum-degraded", "cat report",
                "--redact"):
        check(bad not in code, f"the filing step does not touch {bad!r}")

    print("\nit files once per pull request")
    check("--state open --label secret-finding" in body,
          "looks for an existing open issue before filing")
    check("not filing again" in body,
          "says so rather than silently doing nothing")
    check(body.index("gh issue list") < body.index("gh issue create"),
          "checks BEFORE it creates")
    # The lookup existing is not the same as the lookup being USED. A mutation
    # that tested a different variable left the dedupe dead and every string
    # above still present.
    import re as _re
    m = _re.search(r"(\w+)=\$\(gh issue list", body)
    check(m is not None, "the lookup result is captured into a variable")
    if m:
        var = m.group(1)
        guard = _re.search(rf'if \[ -n "\${{?{var}}}?" \]', body)
        check(guard is not None,
              f"the guard tests ${var}, the same variable the lookup filled")
        if guard:
            after = body[guard.end():body.index("gh issue create")]
            check("exit 0" in after,
                  "and that branch exits instead of falling through to create")

    print("\nthe shell is valid")
    for s in job["steps"]:
        if "run" not in s:
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
            f.write(s["run"])
            path = f.name
        r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        check(r.returncode == 0, f"{s['name']!r} parses: {r.stderr.strip()[:60]}")
        os.unlink(path)
    check(any(ln == "EOF" for ln in body.split("\n")),
          "the heredoc terminator survives YAML de-indentation")

    print("\nthe mailbox must be private, and the default is")
    inp = wf[True]["workflow_call"]["inputs"]["violation-repo"]
    check("private" in inp["description"].lower(),
          "the input says the mailbox must be private")
    secs = wf[True]["workflow_call"]["secrets"]
    check(all(not v.get("required") for v in secs.values()),
          "both secrets are optional, so external adopters still pass")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
