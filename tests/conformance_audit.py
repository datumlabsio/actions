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

# Returned when the API says 403. Distinct from None (absent) on purpose: a
# check that cannot see its subject must report "unverified", never "missing".
FORBIDDEN = object()
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

# BASELINE-ONLY. An external adopter merged one file and was told, in writing,
# that it "changes nothing about how this repository is built". Grading them on
# CLAUDE.md, a scaffold marker or a pre-commit config audits them against
# something they never agreed to -- and the scheduled run FILES ISSUES. A
# finding nobody can act on is a finding everybody learns to scroll past, and
# it takes the real ones with it.
#
# So the tier checks the four things they DID adopt. The fourth is the one with
# teeth and has no equivalent in the §12 list: whether the gate has ever
# actually run. If an organisation is set to "Allow select actions" and we are
# not on the allowlist, the workflow SKIPS -- and a skipped workflow reports
# success. A repository can sit in the register for a year looking adopted
# while the gate has never once executed.
B_CALLER = "Security baseline is called"
B_PINNED = "Called at a pinned version"
B_CURRENT = "Pin is the current release"
B_RAN = "The gate has actually run"

BASELINE_COLUMNS = [
    ("called", B_CALLER),
    ("pinned", B_PINNED),
    ("current", B_CURRENT),
    ("ran", B_RAN),
]

BASELINE_CALL = "datumlabsio/actions/.github/workflows/security-baseline.yml@"


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
        # 403 is NOT 404. "I may not look" and "it is not there" are different
        # facts, and collapsing them makes the audit assert absence it never
        # checked. The rules endpoint answers 403 on any repository we do not
        # administer -- every repository in a client's organisation -- and this
        # used to raise, so one external repo aborted the whole run and took
        # every internal report with it.
        if e.code == 403:
            return FORBIDDEN
        raise


def file_text(repo: str, path: str) -> str | None:
    d = api(f"/repos/{repo}/contents/{path}")
    if d is FORBIDDEN or not d or "content" not in d:
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
    # "full" = the seven §12 checks. "baseline" = the four an external adopter
    # actually signed up for. Set explicitly by the caller, never inferred from
    # the owner: a client repository can live in our organisation, and we may
    # fully adopt one in theirs.
    tier: str = "full"

    def fail(self, check: str, why: str) -> None:
        if check not in self.failed:
            self.failed.append(check)
        self.detail.append(f"- **{check}** — {why}")


_UNSET = object()
_LATEST: object = _UNSET


def latest_release() -> str | None:
    """The current `datumlabsio/actions` release tag, or None if unreadable.

    Fails OPEN on purpose. If the releases endpoint cannot be read, a stale pin
    goes unreported -- which is the same state as before this check existed. The
    alternative is failing every repo in the fleet on our own API error.
    """
    global _LATEST
    if _LATEST is _UNSET:
        rel = api("/repos/datumlabsio/actions/releases/latest")
        _LATEST = None if rel is FORBIDDEN else ((rel or {}).get("tag_name") or None)
    return _LATEST  # type: ignore[return-value]


def canonical_stamps() -> dict[str, str]:
    """The `# datum-config:` line each vendored config should carry."""
    listing = api(f"/repos/datumlabsio/actions/contents/configs?ref={CANONICAL_REF}")
    listing = [] if listing is FORBIDDEN else (listing or [])
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
    if meta is FORBIDDEN or meta is None:
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
                if perm is FORBIDDEN:
                    continue        # cannot see the team's grant; do not guess
                if perm is None:
                    r.fail(
                        FILES,
                        f"CODEOWNERS names `@datumlabsio/{team}`, which has no access to this repo. "
                        f"GitHub ignores an owner without write access silently — no error, and reviews are never requested",
                    )
                elif not (perm.get("permissions") or {}).get("push"):
                    r.fail(FILES, f"`@datumlabsio/{team}` has access but not write, so CODEOWNERS is ignored")

    # --- branch protection ------------------------------------------------
    rules = api(f"/repos/{repo}/rules/branches/{default_branch}")
    if rules is FORBIDDEN:
        r.fail(
            PROTECTION,
            f"cannot read `{default_branch}`'s rules — the audit identity does not "
            f"administer this repository. **Unverified, not missing.** Expected on a "
            f"repository outside our organisation, where branch protection is theirs "
            f"to set; on one of ours it means the audit App is missing admin",
        )
    else:
        rules = rules or []
        have = {rule["type"] for rule in rules} if isinstance(rules, list) else set()
        want = {"pull_request", "deletion", "non_fast_forward"}
        if not want <= have:
            r.fail(PROTECTION, f"`{default_branch}` is missing: {', '.join(sorted(want - have))}")

    # --- CI is a pinned thin caller ---------------------------------------
    #
    # Only for repos born from a scaffold. `actions` and `scaffolds` are the
    # machinery, not archetype repos — `actions` IS the callee — and asserting
    # they should be thin callers produces findings with no possible fix.
    # A RETROFIT ships `datum-ci.yml`, not `ci.yml` -- deliberately, so it cannot
    # collide with the CI an existing repo already has. Reading only `ci.yml`
    # therefore graded every adopted repo on a file that is not ours:
    # `dl-assessment-platform` was reported as running no Datum workflow and no
    # security baseline while `datum-ci.yml` sat beside it doing both.
    #
    # Ours first, then the scaffold-born name. Never the repo's own `ci.yml`
    # when a Datum caller exists -- what their pipeline does is theirs.
    ci_path, ci = None, None
    if scaffolded:
        for candidate in (".github/workflows/datum-ci.yml", ".github/workflows/ci.yml"):
            text = file_text(repo, candidate)
            if text is not None:
                ci_path, ci = candidate, text
                break
    if scaffolded and ci is None:
        r.fail(THIN_CALLER, "no `.github/workflows/datum-ci.yml` and no `.github/workflows/ci.yml`")
        # SECURITY used to live inside the `elif` below, so a repo with no
        # caller at all was never checked for a baseline -- and an unchecked
        # check reports as a pass. The absence of a caller IS the absence of
        # the baseline, and it is reported as such.
        r.fail(SECURITY, "no Datum caller, so `security-baseline` cannot be running (§6)")
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
                r.fail(THIN_CALLER, f"`{ci_path.rsplit('/', 1)[1]}` has a `run:` step in job(s) {', '.join(f'`{j}`' for j in sorted(set(runs)))} — a thin caller runs nothing of its own (§4)")
        except yaml.YAMLError as exc:
            r.fail(THIN_CALLER, f"`{ci_path.rsplit('/', 1)[1]}` will not parse as YAML: {exc}")
        pins = [
            line.split("@", 1)[1].strip()
            for line in ci.splitlines()
            if "uses: datumlabsio/actions/" in line and "@" in line
        ]
        if not pins:
            r.fail(THIN_CALLER, f"`{ci_path.rsplit('/', 1)[1]}` calls no `datumlabsio/actions` workflow")
        else:
            unpinned = [p for p in pins if not p.startswith("v")]
            if unpinned:
                r.fail(THIN_CALLER, f"not pinned to a version tag: {', '.join(f'`{p}`' for p in unpinned)}")
            else:
                r.detail.append(f"- CI pins: {', '.join(sorted({f'`{p}`' for p in pins}))}")
                # "Starts with v" was the whole pin check, so `polaris` audited
                # CONFORMANT while pinned thirteen releases back -- without the
                # fix that stopped a real private key being suppressed. A pin is
                # a decision to stay on a version; a stale one is still a
                # finding, because the gate fixes never arrive.
                latest = latest_release()
                stale = sorted({p for p in pins if latest and p != latest})
                if stale:
                    r.fail(
                        THIN_CALLER,
                        f"pinned to {', '.join(f'`{p}`' for p in stale)}; current release is "
                        f"`{latest}`. Every gate fix since then is absent -- Renovate opens "
                        f"the bump, so this means the pull request was never merged",
                    )
        if "security-baseline" not in ci and "application.yml" not in ci:
            r.fail(SECURITY, f"`{ci_path.rsplit('/', 1)[1]}` does not call `security-baseline` (§6)")

    # --- pre-commit --------------------------------------------------------
    if file_text(repo, ".pre-commit-config.yaml") is None:
        r.fail(PRECOMMIT, "no `.pre-commit-config.yaml` (§3)")

    # --- docs/ where the archetype requires it -----------------------------
    if scaffolded and r.archetype in ARCHETYPES_NEEDING_DOCS:
        if api(f"/repos/{repo}/contents/docs") in (None, FORBIDDEN):
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


def audit_baseline(repo: str) -> Report:
    """The four checks an external adopter agreed to, and no others."""
    r = Report(repo=repo, tier="baseline", archetype="baseline-only")
    meta = api(f"/repos/{repo}")
    if meta is FORBIDDEN or meta is None:
        r.fail(B_CALLER, "repository not found, or the audit identity cannot see it")
        return r

    # ANY workflow file, not a fixed name. Externally the file is conventionally
    # `datum-police.yml`, but nothing enforces that and a repo renaming it has
    # not stopped being adopted.
    listing = api(f"/repos/{repo}/contents/.github/workflows")
    entries = [] if listing in (None, FORBIDDEN) else listing
    calling: list[tuple[str, str]] = []          # (filename, pinned ref)
    for entry in entries if isinstance(entries, list) else []:
        if entry.get("type") != "file" or not entry["name"].endswith((".yml", ".yaml")):
            continue
        text = file_text(repo, f".github/workflows/{entry['name']}")
        if not text:
            continue
        for line in text.splitlines():
            if BASELINE_CALL in line:
                calling.append((entry["name"], line.split(BASELINE_CALL, 1)[1].strip()))

    if not calling:
        r.fail(B_CALLER, "no workflow calls `security-baseline.yml` — the file was "
                         "removed, renamed away from the call, or never merged")
        return r

    r.detail.append("- called by: " + ", ".join(f"`{f}`" for f, _ in sorted(calling)))

    refs = {ref for _, ref in calling}
    unpinned = sorted(x for x in refs if not x.startswith("v"))
    if unpinned:
        r.fail(B_PINNED, "not a version tag: " + ", ".join(f"`{x}`" for x in unpinned)
                         + " — a moving ref lets a change in our repository silently "
                           "change what their CI does")
    pinned = sorted(refs - set(unpinned))
    if pinned:
        r.detail.append("- pinned at: " + ", ".join(f"`{x}`" for x in pinned))
        latest = latest_release()
        stale = [x for x in pinned if latest and x != latest]
        if stale:
            r.fail(B_CURRENT, "pinned to " + ", ".join(f"`{x}`" for x in stale)
                              + f"; current release is `{latest}`")

    # --- has it ever actually run? ---------------------------------------
    #
    # The one check with no §12 equivalent, and the reason this tier is worth
    # more than a file-presence sweep. Presence proves a merge; it does not
    # prove a run.
    ran_any = False
    disabled = []
    never = []
    for name, _ in sorted(set(calling)):
        wf = api(f"/repos/{repo}/actions/workflows/{name}")
        if wf in (None, FORBIDDEN) or not isinstance(wf, dict):
            continue
        if wf.get("state", "active") != "active":
            disabled.append(f"`{name}` is {wf['state']}")
            continue
        runs = api(f"/repos/{repo}/actions/workflows/{name}/runs?per_page=1")
        items = (runs or {}).get("workflow_runs") if isinstance(runs, dict) else None
        if not items:
            never.append(f"`{name}`")
            continue
        ran_any = True
        last = items[0]
        r.detail.append(
            f"- last run of `{name}`: {(last.get('created_at') or '?')[:10]}"
            f" — {last.get('conclusion') or last.get('status')}")

    if disabled:
        r.fail(B_RAN, "disabled, so it cannot run: " + "; ".join(disabled))
    elif never and not ran_any:
        r.fail(B_RAN, "never executed: " + ", ".join(never) + ". A workflow that is "
               "present but has never run is the shape of an organisation set to "
               "*Allow select actions* without `datumlabsio/*` on the allowlist — "
               "it skips, and a skipped workflow reports success")

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


# The seven §12 checks, in the order a reader cares about: can we see it at
# all, is it protected, is it scanned, then the rest.
CHECK_COLUMNS = [
    ("born", BORN),
    ("files", FILES),
    ("protection", PROTECTION),
    ("caller", THIN_CALLER),
    ("security", SECURITY),
    ("hooks", PRECOMMIT),
    ("docs", DOCS),
]


def summarise(reports: list[Report]) -> str:
    """One table: every audited repo, every check, pass or fail.

    Deliberately includes the repos that PASS. An issue tracker shows what is
    broken; it cannot show coverage, because a conformant repo files nothing.
    """
    if not reports:
        return "## Conformance\n\n_No repositories audited._\n"

    clean = [r for r in reports if not r.failed]
    full = [r for r in reports if r.tier == "full"]
    baseline = [r for r in reports if r.tier == "baseline"]

    out = [
        "## Conformance",
        "",
        f"**{len(clean)} of {len(reports)}** audited repositories are conformant.",
        "",
    ]

    # TWO TABLES, NOT ONE. Putting both tiers in one grid needs a shared column
    # set, and any shared set either grades an external adopter on §12 items
    # they never agreed to or drops the run check that only applies to them.
    # Either way one tier gets a column it cannot answer, and a blank cell in a
    # conformance table gets read as a pass.
    for tier, rows, columns, title in (
        ("full", full, CHECK_COLUMNS, "Adopted the standard"),
        ("baseline", baseline, BASELINE_COLUMNS, "Adopted the security baseline only"),
    ):
        if not rows:
            continue
        out += [f"### {title} ({len(rows)})", ""]
        if tier == "full":
            header = ("| Repo | Archetype | Owner | "
                      + " | ".join(k for k, _ in columns) + " |")
            out += [header, "|" + "---|" * (3 + len(columns))]
        else:
            out += ["| Repo | " + " | ".join(k for k, _ in columns) + " |",
                    "|" + "---|" * (1 + len(columns))]

        # Worst first. A table sorted by name buries the thing you opened it for.
        for r in sorted(rows, key=lambda x: (-len(x.failed), x.repo)):
            cells = ["-" if c in r.failed else "ok" for _, c in columns]
            if tier == "full":
                owner = r.owner_team or "**none**"
                out.append(f"| `{r.repo}` | {r.archetype} | {owner} | "
                           + " | ".join(cells) + " |")
            else:
                out.append(f"| `{r.repo}` | " + " | ".join(cells) + " |")
        out.append("")

    if baseline:
        out += [
            "Baseline-only repositories are graded on the **four things they "
            "adopted**, not the seven §12 checks. They merged one file and were "
            "told it changes nothing about how their repository is built; "
            "auditing them against the rest would be grading them on something "
            "they never agreed to.",
            "",
        ]

    out += [
        "`-` is a failed check, not an untested one — every column is checked on "
        "every repo in its tier.",
        "",
        "This audits what is observable from OUTSIDE a repo: settings, files, pins, "
        "config stamps. It does not re-run what the repo's own CI decides, so a full "
        "row of `ok` means *this repo is set up to be checked*, not *this repo is "
        "correct*.",
        "",
    ]

    # The gap that matters more than any single failing check.
    unowned = [r.repo for r in full if not r.owner_team]
    if unowned:
        out += [
            f"**{len(unowned)} repositor{'y has' if len(unowned) == 1 else 'ies have'} "
            "no owning team.** A CODEOWNERS entry naming a team without write access is "
            "silently ignored by GitHub, so these look reviewed and are not: "
            + ", ".join(f"`{r}`" for r in unowned),
            "",
        ]
    return "\n".join(out) + "\n"


def split_args(argv: list[str]) -> tuple[list[str], list[str]]:
    """Repos before `--baseline-only`, repos after it.

    EXPLICIT, not inferred from the owner. "external" is not the same as "not in
    our organisation": a client's repository can live in our org, and we may
    fully adopt one in theirs. Which standard binds a repository is a decision
    somebody makes, so it is typed out.
    """
    if "--baseline-only" not in argv:
        return argv, []
    i = argv.index("--baseline-only")
    return argv[:i], argv[i + 1:]


def main(argv: list[str]) -> int:
    full, baseline = split_args(argv[1:])
    if not full and not baseline:
        print("usage: conformance_audit.py [owner/repo ...] "
              "[--baseline-only owner/repo ...]", file=sys.stderr)
        return 2

    stamps = canonical_stamps() if full else {}
    if full:
        print(f"Canonical config stamps: {len(stamps)} known\n")

    reports = [audit(repo, stamps) for repo in full]
    reports += [audit_baseline(repo) for repo in baseline]
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

    # EVERY repo, not just the drifted ones. Issues answer "what is broken";
    # they cannot answer "where do we stand", because a conformant repo files
    # nothing and is therefore indistinguishable from one nobody has looked at.
    #
    # That distinction is the whole rollout question: 1 of 59 and 40 of 59 look
    # identical in an issue list.
    summary = summarise(reports)
    with open("conformance-report.md", "w") as fh:
        fh.write(summary)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a") as fh:
            fh.write(summary)

    print(f"{len(drifted)} of {len(reports)} repo(s) have drift.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
