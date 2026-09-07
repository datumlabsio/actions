# Checklist — adopting a repository in someone else's organisation

For the Datum engineer doing it. The client-facing page is
[adopting-security-baseline.md](adopting-security-baseline.md); this is the
operator's side.

**Why a checklist rather than a paragraph.** Internal adoption shipped with 30
passing tests and six green checks, then failed five times in a row on real
repositories — and not one failure was in the code. Every one was a setting
nobody had written down (B-80). Cross-org has the same shape and one more
organisation's settings to be wrong.

**No app is installed in their organisation.** Nothing here needs a credential
from them or grants one to us. `datumlabsio/actions` is public, which is the
only reason this works from another org. If a step seems to need an app, stop:
that is a decision, not a step.

## Before you open anything

- [ ] **Actions is enabled** on the repository. `Settings → Actions → General`.
- [ ] **Their org allows our workflows.** If the org is set to *Allow select
      actions*, `datumlabsio/*` must be on the allowlist. This fails **silently
      as a skipped run** — the most expensive shape of failure, because green
      and never-ran look identical.
- [ ] **You know who acts on a finding**, by name, before the first run. Not the
      team, a person. The first repo we adopted stayed red on 26 real findings
      because this was never agreed.
- [ ] **You know the current release** — `gh release view -R datumlabsio/actions
      --json tagName`. Do not copy the tag out of another repo; that is how a
      stale pin propagates.

## The pull request

- [ ] One file: `.github/workflows/datum-police.yml`, exactly as in the
      client-facing page, pinned to the **current** tag.
- [ ] Second file: `.github/dependabot.yml`, `github-actions` ecosystem,
      grouped. Without it the pin never moves and you are the bump process.
      Native GitHub — no app, no grant.
- [ ] `npm`/`pip` ecosystems left out. Their dependency bumps are their call.
- [ ] The body says **what it does not do**. It changes nothing about how they
      build, publishes nothing, reads nothing outside the repo.
- [ ] The body says **the build will go red, and why**, with the findings
      triaged. A red check with no explanation gets the workflow deleted or
      marked not-required, and then the repo looks adopted and is not.

## After it merges

- [ ] **The run actually ran.** Not "the check is green" — open the run and
      confirm the jobs executed. A skipped workflow reports success.
- [ ] **A secret finding is a rotation, not a deletion.** Removing the line
      makes the build pass and leaves the credential in history. Say so
      explicitly; it has needed saying every time.
- [ ] **Add the repo to the register below**, in the same pull request that
      adopts it. A repo that exists only in somebody's memory is not adopted,
      it is remembered.
- [ ] File the findings somewhere with an owner. Ours or theirs, but somewhere.

## What they get, and what they do not

`security-baseline` only: Semgrep, gitleaks over the pull request's commits, and
a dependency audit. **Not** lint, types, tests, pre-commit, commit-lint, image
scanning or branch protection. Those six workflows refuse to run without our
vendored configs in their repository, so adopting them means changing how their
team works — a conversation, not a checklist item.

Two things worth knowing about the gaps, because both have already bitten:

- **gitleaks scans `$BASE..$HEAD`, not history.** A credential committed before
  adoption is invisible to it. On the first external repo a full-history scan
  found two live keys the adopted gate structurally could not see.
- **Branch protection is unverifiable.** The rules endpoint answers 403 on a
  repository we do not administer. The audit reports this as *unverified, not
  missing* — do not read it as a finding against them.

## Register of external adopters

The conformance audit takes an explicit repo list; it does not discover
anything. Nothing notices a deleted `datum-police.yml` unless the repo is on a
list somebody maintains. This is that list.

| Repository | Adopted | Pinned at adoption | Who acts on findings |
| ---| ---| ---| --- |
| `EmberAssetManagement/ecp-frontend` | 2026-09-01 | `v1.1.0` → `v1.2.1` 2026-09-07 | **unassigned** |

`unassigned` is not a formatting gap. It is the open item, and it is the one
that decides whether any of the rest of this was worth doing.
