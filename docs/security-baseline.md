# `security-baseline` — DES §6, the security half

```yaml
jobs:
  security:
    uses: datumlabsio/actions/.github/workflows/security-baseline.yml@v0.11.0
```

Three tools, all open source, all free:

| Job | Tool | Licence | Behaviour |
|---|---|---|---|
| `semgrep` | Semgrep | LGPL-2.1 | a finding **fails** the job |
| `secrets` | gitleaks | MIT | a detected credential **fails** the job |
| `dependencies` | `pnpm audit` / `pip-audit` | — | **reports**, does not fail |

The paid alternatives are priced per repository or per committer, and 223 of the org's 228 repos are private. That is the whole reason for these three.

## Why gitleaks and not GitHub secret scanning

**GitHub's is better.** It refuses the push, so the credential never reaches the remote. It is also a paid add-on on private repos.

gitleaks fails the pull request instead — by which point the secret is already on a branch and must be rotated regardless. **That is a real reduction in protection, not a like-for-like swap**, and §6 says so rather than pretending otherwise.

Both are enabled on the two public repos, where GitHub's is free.

## Private-key matches that carry no key

Semgrep's `detected-private-key` fires on real PEM header bytes. Setup
documentation that shows how to paste a deploy key contains exactly those bytes,
truncated for display, and is the most common false positive this baseline meets
on a repository it did not scaffold.

Such a finding is dropped **only when the block provably holds no byte of the
private section** — what remains is a fixed format header and, at most, the
public key. Every suppression is printed with its file, line and reason, in the
log and the job summary.

**The test is never length.** A PKCS#8 ed25519 private key is 48 bytes, smaller
than the 52-byte truncated header being suppressed, so any threshold that
catches the placeholder discards a real key. A key with its middle elided is
kept: it still carries private bytes, and partial key recovery is a real attack.

Set `suppress-placeholder-keys: false` for raw output.

## What it scans, and what it deliberately does not

**gitleaks scans the commits this pull request adds**, not all history. A first full-history scan on an old repo surfaces every credential ever committed — all needing rotation, none of them this author's doing. That is a migration, and it is not the same job as stopping the next one.

With no pull request base available it falls back to scanning the working tree.

## Two Semgrep behaviours that will surprise you

**It only scans files tracked by git.** An untracked file is skipped and reported as clean. Run it locally on new work before committing and it will happily scan nothing and pass. In CI this never bites, because checkout tracks everything.

**It skips `tests/` by default**, along with `vendor/` and `node_modules/`, via its built-in ignore list. Test code is not scanned unless you override it. That is usually right and occasionally not — a test that shells out with `shell=True` is still a machine running that code.

## Metrics are off

`--config=auto` and Semgrep's metrics both send project metadata to semgrep.dev — to select rules, and to count usage. On private repos that is telemetry nobody agreed to, and it sits badly beside the no-literal-env-values gate this repo enforces on itself.

So the rulesets are **named explicitly** (`p/default`, `p/secrets`) and metrics are off. Rules are still downloaded from the registry; nothing about the project goes back.

## The Datum rules

`configs/semgrep.yml` is vendored and stamped like the linter configs, and runs **alongside** the community packs rather than instead of them.

| Rule | Why |
|---|---|
| `datum-retired-vocabulary` | RFC-0008 terms in identifiers. A retired word outlives the document that retired it, and the next reader takes it as current. |
| `datum-bare-except` | A bare `except:` swallows `KeyboardInterrupt` and `SystemExit`, so a pipeline that should stop keeps running and reports success. |
| `datum-subprocess-shell-true` | `shell=True` with a constructed command is how a filename becomes code execution. |

**A rule earns its place by having caught something real, or by encoding a rule the specs already state.** Inventing rules that sound sensible is how a scanner becomes noise everybody suppresses.

## Why the dependency audit reports rather than fails

The fix for an advisory is a Renovate bump. Blocking a pull request on something its author cannot resolve inside that pull request is how a gate gets routed around.

If an advisory is not something Renovate can raise, it needs a human — say so on the pull request rather than waiting for the tool to escalate.

## Verified

`self-test` runs all four cases on every pull request: the vulnerable fixture is refused **and each of the three Datum rules is confirmed to fire by name**, the clean fixture passes, a planted credential is refused, and a clean tree passes.

The planted credential is **generated at runtime and never committed** — this repo is public with push protection enabled, so a realistic-looking credential in a fixture would be refused at push time. Correctly.
