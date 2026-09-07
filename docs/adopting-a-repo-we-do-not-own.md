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
- [ ] That file needs `cooldown: default-days: 7`, **excluding
      `datumlabsio/actions`**. The baseline flags a Dependabot config with no
      cooldown, so without this the first thing our gate reports is the file we
      just added. Below 7 it is still flagged; the exclusion is there because
      our own releases carry the security fixes and delaying those by a week is
      the opposite of the point.
- [ ] `npm`/`pip` ecosystems left out. Their dependency bumps are their call.
- [ ] The body says **what it does not do**. It changes nothing about how they
      build, publishes nothing, reads nothing outside the repo.
- [ ] The body says **the build will go red, and why**, with the findings
      triaged. A red check with no explanation gets the workflow deleted or
      marked not-required, and then the repo looks adopted and is not.

## After it merges

- [ ] **The run actually ran.** Not "the check is green" — open the run and
      confirm the jobs executed. A skipped workflow reports success.
- [ ] **Check the finding count against what you predicted.** Both adoptions so
      far reported one more than the repository had, and both times the extra
      one was in a file we had just added. The gate reads our work too.
- [ ] **A secret finding is a rotation, not a deletion.** Removing the line
      makes the build pass and leaves the credential in history. Say so
      explicitly; it has needed saying every time.
- [ ] **Add the repo to the register below**, in a companion pull request
      opened the same day — the adoption lands in *their* repository and the
      register lives in this one, so it cannot literally be the same pull
      request. A repo that exists only in somebody's memory is not adopted,
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

## Nothing watches these repositories. Read this before adding one.

The conformance audit **cannot see a private repository in someone else's
organisation.** It runs as an App installation token scoped to `datumlabsio`,
and that token gets a 404 on their repo — indistinguishable, from where it
stands, from a repository that was deleted.

Reaching one would need a credential inside their organisation. Three options
were on the table:

| | |
| ---| --- |
| Install `datum-police` there | It holds `workflows: write`. One private-key compromise would span Datum **and every client that installed it**. `workflows: write` is arbitrary code execution in their CI, with their secrets |
| A second, read-only app | Small blast radius, but still a standing grant in a client's org, negotiated per client |
| **Do not audit them** | Chosen, 2026-09-07 |

**So an adopted external repository is not monitored by anything we run.** If
their team deletes `datum-police.yml`, marks the check not-required, or their
org stops allowing our workflows, we find out when somebody looks. That is a
known cost of not holding a credential in a client's organisation, not an
oversight.

What carries the weight instead:

- **Dependabot**, in their repo, keeps the pin current without us. It is not
  optional — without it you are the bump process, and a pin nobody moves is a
  scanner whose rules are a year old.
- **A required status check** on their default branch, if their team will set
  one. Then removing the gate is visible to *them*, which is the only place it
  can be visible.
- **This register**, re-read at engagement review. By a person.

A **public** external repo is different — it needs no credential, so pass it to
the audit's `baseline-only-repos` input by hand.

## Register of external adopters

| Repository | Visibility | Adopted | Pin | Dependabot | Who acts on findings |
| ---| ---| ---| ---| ---| --- |
| `EmberAssetManagement/ecp-frontend` | private | 2026-09-01 | `v1.1.0` → `v1.2.1` 2026-09-07 | yes, 2026-09-07 | Ember, on the Supabase key rotation |
| `Westwise-Group/analytics-clickhouse-pipelines` | private | PR open 2026-09-07 | `v1.3.0` | yes, at adoption | **unassigned** — 33 findings, one a live Google OAuth secret |

Keep the columns filled. `Visibility` decides whether the audit can see it at
all; `Dependabot` decides whether the pin moves without one of us; and the last
column is the one that decides whether any of the rest of this was worth doing
— the first repository to adopt sat red on 26 real findings for a week while it
read `unassigned`.
