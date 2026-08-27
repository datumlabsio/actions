# Adopting the security baseline in a repository we do not own

Two files. No scaffold, no archetype, no opinion about how the repository is
laid out.

`datumlabsio/actions` is public, so **any repository in any organisation can call
it**. This page is what to give a client team, or a Datum engineer working in a
client's repository.

## What it does

| Gate | What it finds |
|---|---|
| **Semgrep** | vulnerable code patterns — injection, unsafe deserialisation, hardcoded credentials |
| **gitleaks** | secrets in the commits a pull request adds |
| **dependency audit** | known advisories in the dependency tree |

It runs on pull requests. It changes nothing, publishes nothing, and reaches
nothing outside the repository it runs in.

## What it does NOT do

Deliberately. This is the subset worth adopting on its own, not a foot in the
door for the rest of the standard.

- No commit-message rules, no branch naming, no required reviewers
- No opinion about languages, layout, or build tooling
- No archetype, no scaffold, no `copier`
- Nothing is published or deployed

## Step 1 — `security-tool-versions.txt` in the repository root

```
# datum-config: security-tool-versions v1
# Vendored from datumlabsio/actions/configs/security-tool-versions.txt. Bump it,
# do not edit it.
semgrep=1.174.0
gitleaks=8.30.1
```

**Why this file rather than versions baked into the workflow:** the repository
that runs the scan controls when its tooling changes. A new Semgrep release
cannot alter what your CI accepts overnight — it arrives as a pull request
changing this file, which somebody reads.

## Step 2 — `.github/workflows/datum-security.yml`

```yaml
name: security

on:
  pull_request:

permissions:
  contents: read

jobs:
  security:
    uses: datumlabsio/actions/.github/workflows/security-baseline.yml@v0.22.0
```

Pin the version. `@main` would mean a change in our repository silently changes
what your CI does, which is the thing this gate exists to prevent.

## What you will see on the first run

Probably findings. A repository that has never been scanned usually has some,
and they are almost always older than the pull request that surfaced them.

**A secret that Semgrep or gitleaks finds is a compromised secret.** It reached a
git remote. Removing the line is not enough — rotate the credential. That is the
one rule worth reading twice, because deleting the line makes the build pass and
leaves the secret in history.

## Turning parts off

Each gate has a switch, and using them is better than not adopting at all:

```yaml
    with:
      semgrep: true
      gitleaks: true
      dependency-audit: false
```

## What we get, and why you should know

Nothing automatic. Findings appear in **your** Actions tab, not ours — we have no
dashboard, no webhook, no visibility into your repository.

What Datum gets is indirect: engineers working in your repository are held to the
same checks they are held to in ours.

## Known limits, stated up front

- **`datumlabsio/.github` does not cross organisations.** Community health files
  — pull request templates, issue forms, `SECURITY.md` — serve only the
  organisation that owns them. You get the workflows and none of that.
- **Semgrep runs community rule packs only** unless you also vendor our
  `semgrep.yml`. The workflow says so on every run rather than implying full
  coverage.
- **Pinned versions are yours to bump.** Nothing here updates itself, by design.

## Where this came from

`datumlabsio/actions`, the same workflows every Datum repository runs. The gates
are the ones our own code passes, not a reduced set written for external use.
