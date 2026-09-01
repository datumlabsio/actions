#!/usr/bin/env python3
"""The security baseline stops scanning once its release is a year old.

A pinned scanner ages into false assurance: it reports green because its rules
are old, not because the code is clean. The repository most likely to be running
a two-year-old pin is one nobody maintains -- including one belonging to a client
we no longer work with, whose workflow file we cannot delete.

So a release expires. Two properties matter more than the expiry itself, and
most of these cases exist to protect them:

  IT MUST PASS, NEVER FAIL. Breaking the CI of a repository we no longer work on
  is not ours to do. A regression to failing would be a hostile act performed by
  a cron.

  IT MUST FAIL OPEN. An unreadable stamp, a future date, an unstamped working
  copy -- none of those may be the reason a security gate stops scanning.

The script under test is EXTRACTED FROM THE WORKFLOW, not a copy kept beside it.
"""
from __future__ import annotations

import datetime
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/security-baseline.yml"
RELEASE = ROOT / ".github/workflows/release.yml"
MARKER = "DATUM_AGE_CHECK"
TODAY = datetime.date(2026, 9, 1)


def extract(dest: Path) -> Path:
    src = WORKFLOW.read_text()
    m = re.search(rf"<<'{MARKER}'\n(.*?)\n\s*{MARKER}", src, re.S)
    if not m:
        sys.exit(f"FAIL: no {MARKER} heredoc in {WORKFLOW.name} — was the step renamed?")
    body = "\n".join(
        ln[10:] if ln.startswith(" " * 10) else ln for ln in m.group(1).split("\n")
    )
    out = dest / "age.py"
    out.write_text(body)
    return out


def load(path: Path):
    spec = importlib.util.spec_from_file_location("age", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ago(days: int) -> str:
    return (TODAY - datetime.timedelta(days=days)).isoformat()


# The reason is asserted, not just the boolean. It is printed as a ::notice:: on
# every run in every repository that adopted this, so "0000-00-00 is unreadable"
# would read as a bug in our tooling on a perfectly healthy build. Two mutations
# reach the right answer by the wrong route and are only caught here.
CASES = [
    # (name, stamp, expect_expired, expect_in_reason)
    ("a working copy never expires",   "0000-00-00", False, "not a release"),
    ("released today",                 ago(0),       False, "0 days ago"),
    ("one day inside the limit",       ago(364),     False, "364 days ago"),
    ("exactly at the limit",           ago(365),     False, "365 days ago"),
    ("one day past the limit",         ago(366),     True,  "366 days ago"),
    ("two years old",                  ago(730),     True,  "730 days ago"),
    ("an unreadable stamp fails OPEN", "not-a-date", False, "unreadable"),
    ("an empty stamp fails OPEN",      "",           False, "unreadable"),
    ("a future date fails OPEN",       ago(-30),     False, "in the future"),
]


def main() -> int:
    import tempfile

    failures = []
    with tempfile.TemporaryDirectory() as td:
        age = load(extract(Path(td)))
        for name, stamp, want, want_reason in CASES:
            got, reason = age.decide(stamp, 365, TODAY)
            ok = got == want and want_reason in reason
            print(f"    [{'ok' if ok else 'FAIL'}] {name}: expired={got} — {reason}")
            if not ok:
                failures.append(name)

    # The expired path must not be able to fail a build. `decide` returns a
    # boolean and never raises; assert that directly rather than trusting it.
    with tempfile.TemporaryDirectory() as td:
        age = load(extract(Path(td)))
        for stamp in ("0000-00-00", ago(9999), "not-a-date", "", "2026-13-45", None):
            try:
                got, _ = age.decide(stamp if stamp is not None else "", 365, TODAY)
                assert isinstance(got, bool)
            except Exception as e:  # noqa: BLE001
                print(f"    [FAIL] decide() raised on {stamp!r}: {e}")
                failures.append(f"raised on {stamp!r}")
    print("    [ok] decide() never raises, on any stamp")

    # The release workflow must be able to find the line it rewrites, and there
    # must be exactly one of it.
    stamps = WORKFLOW.read_text().count("# datum-release-stamp")
    ok = stamps == 1
    print(f"    [{'ok' if ok else 'FAIL'}] exactly one datum-release-stamp line ({stamps})")
    if not ok:
        failures.append("stamp marker count")

    ok = "Stamp the release date" in RELEASE.read_text()
    print(f"    [{'ok' if ok else 'FAIL'}] release.yml carries the stamping step")
    if not ok:
        failures.append("release stamping step missing")

    # And the shipped default must be the unstamped value: a stamped main would
    # expire this repository's own CI a year after someone forgot.
    shipped = re.search(r'DATUM_RELEASED_ON: "([^"]*)"', WORKFLOW.read_text()).group(1)
    ok = shipped == "0000-00-00"
    print(f"    [{'ok' if ok else 'FAIL'}] main ships unstamped, not a real date ({shipped})")
    if not ok:
        failures.append("main is stamped")

    # The release step's rewrite has never run -- it only fires when a tag is
    # cut. Apply its exact regex to the real file here, so a shape change in the
    # workflow is caught now rather than by a release that silently ships
    # unstamped code to every future adopter.
    text = WORKFLOW.read_text()
    stamped, n = re.subn(
        r'(DATUM_RELEASED_ON: ")[0-9-]+(" # datum-release-stamp)',
        r'\g<1>2026-09-01\g<2>', text, count=1)
    ok = n == 1 and 'DATUM_RELEASED_ON: "2026-09-01" # datum-release-stamp' in stamped
    print(f"    [{'ok' if ok else 'FAIL'}] release.yml's rewrite matches the shipped file")
    if not ok:
        failures.append("stamp regex does not match the file it rewrites")

    # And the stamped result must actually parse as a workflow, and expire.
    import yaml
    try:
        doc = yaml.safe_load(stamped)
        got = doc.get("env", {}).get("DATUM_RELEASED_ON")
        ok = got == "2026-09-01"
    except Exception as e:  # noqa: BLE001
        ok, got = False, f"unparseable: {e}"
    print(f"    [{'ok' if ok else 'FAIL'}] a stamped file is still valid YAML ({got})")
    if not ok:
        failures.append("stamped file does not parse")

    if failures:
        print(f"\nFAIL: {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print(f"\nOK: {len(CASES) + 4} checks — expiry passes, never fails, and fails open")
    return 0


if __name__ == "__main__":
    sys.exit(main())
