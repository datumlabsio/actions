# Adopting the security baseline in a repository we do not own

**One file.** No scaffold, no archetype, no configuration, no secrets, and no
opinion about how the repository is laid out.

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

## The whole of it — `.github/workflows/datum-police.yml`

```yaml
name: datum-police

on:
  pull_request:

permissions:
  contents: read

jobs:
  security:
    uses: datumlabsio/actions/.github/workflows/security-baseline.yml@v0.27.0
```

That is everything. The tool versions are pinned **inside** the workflow this
calls, so the run is reproducible without you vendoring anything.

**Pin the version.** `@main` would mean a change in our repository silently
changes what your CI does, which is the thing this gate exists to prevent.

## Keeping it current

The pin above does not move on its own. Two ways to keep it fresh, and doing
neither is a choice too — a year-old scanner passes because its rules are old,
not because your code is clean.

**Renovate**, if you run it. One line, and our releases arrive as a pull request
you review like any other:

```json
{ "extends": ["github>datumlabsio/.github"] }
```

**Or bump it by hand** when we tell you there is a reason to.

## Optional — pinning the tools yourself

Skip this unless you want it. By default the tool versions come from our
workflow. If you would rather control when *your* tooling changes, drop this at
the repository root and the workflow will prefer it:

```
# datum-config: security-tool-versions v1
# Vendored from datumlabsio/actions/configs/security-tool-versions.txt. Bump it,
# do not edit it.
semgrep=1.174.0
gitleaks=8.30.1
```

Then a new Semgrep release cannot alter what your CI accepts overnight — it
arrives as a pull request changing this file, which somebody reads.

**If you add it, it must keep the `# datum-config:` stamp.** A file without one
is refused, because a vendored config is bumped, never hand-written. The run log
says which of the two was used either way.

## What you will see on the first run

Probably findings. A repository that has never been scanned usually has some,
and they are almost always older than the pull request that surfaced them.

**A secret that Semgrep or gitleaks finds is a compromised secret.** It reached a
git remote. Removing the line is not enough — rotate the credential. That is the
one rule worth reading twice, because deleting the line makes the build pass and
leaves the secret in history.

## Private keys in your setup docs

Documentation that shows someone how to paste a deploy key normally looks like
this, and it is **not** a finding:

```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
... (full private key) ...
-----END OPENSSH PRIVATE KEY-----
```

Semgrep's rule fires, correctly, on real key header bytes. What it cannot see is
that the block stops before any private material — those leading bytes are a
fixed format header and, at most, the public key. Neither is secret.

The baseline drops these, and **prints every one it drops** with the file, line
and the reason, in the log and in the job summary. Nothing is suppressed
quietly.

**Length is never the test.** A PKCS#8 ed25519 private key is 48 bytes — smaller
than the 52-byte truncated header this exists to suppress — so any size
threshold that catches the placeholder also throws away a real key. The test is
whether the block contains a byte of the private section. It does not, or it is
a finding.

A real key with its middle elided for display is **kept**, because it still
carries private bytes and partial key recovery is a real attack.

To see raw Semgrep output instead:

```yaml
    with:
      suppress-placeholder-keys: false
```

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
- **The pull request gate scans the commits a pull request adds, not history.**
  It protects you from the next secret, not the ones already committed. A
  first-time full-history scan is a separate, deliberate exercise — and on an
  older repository it usually finds something.
- **Nothing here updates itself**, by design. See *Keeping it current* above — Renovate is one line, and doing neither is a choice with a cost: a scanner ages into passing because its rules are old.

## Where this came from

`datumlabsio/actions`, the same workflows every Datum repository runs. The gates
are the ones our own code passes, not a reduced set written for external use.
