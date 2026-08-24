#!/usr/bin/env python3
"""DES §12: compliance that is not checked does not exist.

Audits repos against the checks that are observable from OUTSIDE the repo — its
settings, its files, its pins. It deliberately does not try to reproduce what the
repo's own CI already enforces.

WHAT THIS CAN AND CANNOT SEE, because the difference matters more than the
check list:

  Observable here      settings, file presence, pin versions, config stamps,
                       CODEOWNERS naming a team that actually has write access.

  Not observable here  "linters pass", "coverage did not fall", "no tag was
                       moved". Those are facts about a RUN, not about a repo,
                       and the repo's own CI is where they are decided. An audit
                       that re-ran them would be a slower second CI that
                       disagrees with the first.

So a green audit means "this repo is set up to be checked", not "this repo is
correct". Those are different claims and conflating them is how a dashboard
starts lying.

Usage:  conformance_audit.py owner/repo [owner/repo ...]
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

import yaml
from dataclasses import dataclass, field

API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN", "")
CANONICAL_REF = os.environ.get("CANONICAL_REF", "main")

# The §12 checklist labels, verbatim, so a finding maps onto the issue form
# without anyone translating it by hand.
BORN = "Born from current scaffold; archetype declared"
FILES = "CLAUDE.md, README and CODEOWNERS present"
PROTECTION = "Branch protection per phase policy"
THIN_CALLER = "CI is a pinned thin caller; stages green"
SECURITY = "Security baseline active"
PRECOMMIT = "Pre-commit config present; CI runs the same hooks"
DOCS = "docs/ present where the archetype requires it"

ARCHETYPES_NEEDING_DOCS = {"application", "web-app"}


def api(path: str, *, raw: bool = False, accept: str = "application/vnd.github+json"):
    """GET, returning parsed JSON, or None for 404, or {} for an empty 204.

    The team-permission endpoint answers 204 with NO BODY when a team has access
    and you did not ask for the repository media type. Parsing that as JSON
    raises, and the first version of this script died on the first repo whose
    CODEOWNERS named a real team — which is every repo we own.
    """
    url = path if path.startswith("http") else f"{API}{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", accept)
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read()
            if raw:
                return body
            if not body.strip():
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def file_text(repo: str, path: str) -> str | None:
    d = api(f"/repos/{repo}/contents/{path}")
    if not d or "content" not in d:
        return None
    import base64

    return base64.b64decode(d["content"]).decode("utf-8", "replace")


@dataclass
class Report:
    repo: str
    archetype: str = "not declared"
    owner_team: str = ""
    failed: list[str] = field(default_factory=list)
    detail: list[str] = field(default_factory=list)

    def fail(self, check: str, why: str) -> None:
        if check not in self.failed:
            self.failed.append(check)
        self.detail.append(f"- **{check}** — {why}")


def canonical_stamps() -> dict[str, str]:
    """The `# datum-config:` line each vendored config should carry."""
    listing = api(f"/repos/datumlabsio/actions/contents/configs?ref={CANONICAL_REF}") or []
    out: dict[str, str] = {}
    for entry in listing:
        if entry["type"] != "file" or entry["name"] == "README.md":
            continue
        text = file_text("datumlabsio/actions", f"configs/{entry['name']}")
        if not text:
            continue
        for line in text.splitlines()[:3]:
            if line.startswith("# datum-config:"):
                out[entry["name"]] = line.strip()
                break
    return out


def audit(repo: str, stamps: dict[str, str]) -> Report:
    r = Report(repo=repo)
    meta = api(f"/repos/{repo}")
    if meta is None:
        r.fail(BORN, "repository not found, or the audit identity cannot see it")
        return r
    default_branch = meta.get("default_branch", "main")

    # --- born from the scaffold, archetype declared -----------------------
    answers = file_text(repo, ".copier-answers.yml")
    scaffolded = answers is not None
    if not answers:
        r.fail(
            BORN,
            "no `.copier-answers.yml` — not born from a scaffold, or the file was deleted. "
            "The archetype-specific checks below are skipped, because they presuppose one: "
            "reporting five symptoms of a single cause is how a report gets ignored",
        )
    else:
        for line in answers.splitlines():
            if line.startswith("archetype:"):
                r.archetype = line.split(":", 1)[1].strip()
            if line.startswith("_commit:"):
                r.detail.append(f"- scaffold version: `{line.split(':', 1)[1].strip()}`")
        if r.archetype == "not declared":
            r.fail(BORN, "`.copier-answers.yml` present but declares no archetype")

    # --- the three files that cannot be inherited -------------------------
    missing = [f for f in ("CLAUDE.md", "README.md") if file_text(repo, f) is None]
    codeowners = file_text(repo, ".github/CODEOWNERS") or file_text(repo, "CODEOWNERS")
    if codeowners is None:
        missing.append("CODEOWNERS")
    if missing:
        r.fail(FILES, f"missing: {', '.join(f'`{m}`' for m in missing)}")

    # --- CODEOWNERS names a team that actually has write ------------------
    if codeowners:
        teams = {
            tok.split("/", 1)[1]
            for line in codeowners.splitlines()
            if not line.strip().startswith("#")
            for tok in line.split()
            if tok.startswith("@datumlabsio/")
        }
        if not teams:
            r.fail(FILES, "CODEOWNERS names no `@datumlabsio/` team — a repo with no owning crew is itself a finding")
        else:
            r.owner_team = "@datumlabsio/" + sorted(teams)[0]
            for team in sorted(teams):
                # The repository media type is what makes this return the
                # permission object rather than a bare 204.
                perm = api(
                    f"/orgs/datumlabsio/teams/{team}/repos/{repo}",
                    accept="application/vnd.github.v3.repository+json",
                )
                if perm is None:
                    r.fail(
                        FILES,
                        f"CODEOWNERS names `@datumlabsio/{team}`, which has no access to this repo. "
                        f"GitHub ignores an owner without write access silently — no error, and reviews are never requested",
                    )
                elif not (perm.get("permissions") or {}).get("push"):
                    r.fail(FILES, f"`@datumlabsio/{team}` has access but not write, so CODEOWNERS is ignored")

    # --- branch protection ------------------------------------------------
    rules = api(f"/repos/{repo}/rules/branches/{default_branch}") or []
    have = {rule["type"] for rule in rules} if isinstance(rules, list) else set()
    want = {"pull_request", "deletion", "non_fast_forward"}
    if not want <= have:
        r.fail(PROTECTION, f"`{default_branch}` is missing: {', '.join(sorted(want - have))}")

    # --- CI is a pinned thin caller ---------------------------------------
    #
    # Only for repos born from a scaffold. `actions` and `scaffolds` are the
    # machinery, not archetype repos — `actions` IS the callee — and asserting
    # they should be thin callers produces findings with no possible fix.
    ci = file_text(repo, ".github/workflows/ci.yml") if scaffolded else None
    if scaffolded and ci is None:
        r.fail(THIN_CALLER, "no `.github/workflows/ci.yml`")
    elif ci is not None:
        # Parsed, not grepped. The first version matched the substring "run:" and
        # flagged polaris for a COMMENT reading "It is a call, not a `run:` step"
        # — a check that fails on prose describing the rule it enforces.
        try:
            doc = yaml.safe_load(ci) or {}
            runs = [
                name
                for name, job in (doc.get("jobs") or {}).items()
                if isinstance(job, dict)
                for step in (job.get("steps") or [])
                if isinstance(step, dict) and "run" in step
            ]
            if runs:
                r.fail(THIN_CALLER, f"`ci.yml` has a `run:` step in job(s) {', '.join(f'`{j}`' for j in sorted(set(runs)))} — a thin caller runs nothing of its own (§4)")
        except yaml.YAMLError as exc:
            r.fail(THIN_CALLER, f"`ci.yml` will not parse as YAML: {exc}")
        pins = [
            line.split("@", 1)[1].strip()
            for line in ci.splitlines()
            if "uses: datumlabsio/actions/" in line and "@" in line
        ]
        if not pins:
            r.fail(THIN_CALLER, "`ci.yml` calls no `datumlabsio/actions` workflow")
        else:
            unpinned = [p for p in pins if not p.startswith("v")]
            if unpinned:
                r.fail(THIN_CALLER, f"not pinned to a version tag: {', '.join(f'`{p}`' for p in unpinned)}")
            else:
                r.detail.append(f"- CI pins: {', '.join(sorted({f'`{p}`' for p in pins}))}")
        if "security-baseline" not in ci and "application.yml" not in ci:
            r.fail(SECURITY, "`ci.yml` does not call `security-baseline` (§6)")

    # --- pre-commit --------------------------------------------------------
    if file_text(repo, ".pre-commit-config.yaml") is None:
        r.fail(PRECOMMIT, "no `.pre-commit-config.yaml` (§3)")

    # --- docs/ where the archetype requires it -----------------------------
    if scaffolded and r.archetype in ARCHETYPES_NEEDING_DOCS:
        if api(f"/repos/{repo}/contents/docs") is None:
            r.fail(DOCS, f"archetype `{r.archetype}` has external consumers, so §3 requires a `docs/` folder")

    # --- vendored configs are current --------------------------------------
    stale = []
    for name, canonical in stamps.items():
        text = file_text(repo, name)
        if text is None:
            continue  # not every repo vendors every config
        first = next((ln.strip() for ln in text.splitlines()[:3] if ln.startswith("# datum-config:")), None)
        if first is None:
            stale.append(f"`{name}` carries no version stamp")
        elif first != canonical:
            stale.append(f"`{name}` is `{first.split(':', 1)[1].strip()}`, canonical is `{canonical.split(':', 1)[1].strip()}`")
    if stale:
        r.fail(THIN_CALLER, "vendored config drift — " + "; ".join(stale))

    return r


def render(r: Report) -> str:
    lines = [
        f"**Repo:** `{r.repo}`",
        f"**Archetype:** {r.archetype}",
        f"**Owning crew:** {r.owner_team or '_none named — this is itself a finding_'}",
        "",
        "### Which checks failed",
        "",
    ]
    lines += [f"- [x] {c}" for c in r.failed]
    lines += ["", "### Detail", ""]
    lines += r.detail or ["_none_"]
    lines += [
        "",
        "---",
        "",
        "Filed by the org conformance workflow (DES §12). It audits what is observable "
        "from outside a repo — settings, files, pins, config stamps. It does not re-run "
        "what the repo's own CI already decides, so a green audit means *this repo is set "
        "up to be checked*, not *this repo is correct*.",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    repos = argv[1:]
    if not repos:
        print("usage: conformance_audit.py owner/repo [owner/repo ...]", file=sys.stderr)
        return 2

    stamps = canonical_stamps()
    print(f"Canonical config stamps: {len(stamps)} known\n")

    reports = [audit(repo, stamps) for repo in repos]
    drifted = [r for r in reports if r.failed]

    for r in reports:
        state = f"{len(r.failed)} finding(s)" if r.failed else "conformant"
        print(f"{r.repo}: {state}")
        for line in r.detail:
            print(f"    {line}")
    print()

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"drifted={len(drifted)}\n")
            fh.write(f"audited={len(reports)}\n")

    payload = [{"repo": r.repo, "archetype": r.archetype, "owner": r.owner_team,
                "failed": r.failed, "body": render(r)} for r in drifted]
    with open("conformance-findings.json", "w") as fh:
        json.dump(payload, fh, indent=2)

    print(f"{len(drifted)} of {len(reports)} repo(s) have drift.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
