# datumlabsio/actions — reusable CI workflows for every repo in the org

## Context

Archetype `docs` for its own purposes, but what it produces is CI. One of the three org repos in DES §2, alongside `datumlabsio/.github` (org defaults) and `datumlabsio/scaffolds` (templates per archetype).

Every repo in the org runs its CI by calling a workflow here, pinned to a version tag. Bespoke CI is forbidden. That means **this repo is a single point of failure for the whole fleet** — a bad change merged here breaks every repo's CI at once, not one repo's. Treat every change as fleet-wide, because it is.

Reusable workflows must live in `.github/workflows/`. GitHub does not find them anywhere else.

## Commands

```bash
# Lint the workflows. Do NOT substitute a YAML parse: it cannot see a duplicated
# job key (PyYAML keeps the last one silently) and knows nothing about Actions
# semantics. Both of those have shipped here and both fail at startup with no
# readable log. Same version CI pins.
#
# shellcheck must be on PATH. actionlint runs it over every `run:` block, and
# SILENTLY SKIPS that half when it is missing — so a locally-clean run can still
# fail in CI, where the runner has it. That has happened here once already.
actionlint            # after: brew install actionlint shellcheck
shellcheck --version  # if this fails, your actionlint run is only half a check

# Third-party actions pinned by SHA; our own repo and local paths pinned by tag (DES §4).
grep -rnE "^[[:space:]]*uses:" .github/workflows/ | grep -vE "uses:[[:space:]]*(\./|datumlabsio/)" | grep -v "@[0-9a-f]\{40\}" || echo "ALL THIRD-PARTY ACTIONS SHA-PINNED"

# Every workflow declares explicit permissions, or says in a comment why it cannot.
for f in .github/workflows/*.yml; do
  grep -q "^permissions:" "$f" && continue
  grep -q "Deliberately no .permissions:. block" "$f" && continue
  echo "MISSING permissions: $f"
done; echo "PERMISSIONS CHECKED"
```

`self-test.yml` runs the real workflows against this repo on every pull request. That is the test that matters; the commands above are what to run before pushing.

**A workflow change is not verified until CI has reported on it.** Two startup failures reached `main` here because a pull request was merged while its checks had not run — and a startup failure produces no job, no step and no log, so there is nothing to read afterwards. Wait for the checks.

## Conventions

- **Callers pin an exact version** (`@v1.4.2`), never a moving tag. Renovate raises the bump PR when a release is cut, which is how a gate fix reaches the fleet — and a moving tag is the one thing Renovate cannot bump. It also means a caller's CI only changes when a reviewed PR lands in that repo.
- **New checks arrive switched off.** Add the input with a default that preserves current behaviour. Repos opt in; making it the default is a separate conversation.
- Workflows are the stage sequence (`lint → test → build → scan → publish → deploy`). Composite actions under `actions/` are the steps inside them. Callers reference workflows only, never the composites.
- One doc per workflow under `docs/`, with its inputs table. A workflow whose inputs are undocumented cannot be adopted by anyone who did not write it.
- Conventional Commits, branches `feat/…` `fix/…` `chore/…`.

## Guardrails

- **Never pin a third-party action by tag.** SHA only. A tag is mutable by someone outside this org.
- **Never widen `permissions:` to make something work.** Find out what the workflow actually needs. `write-all` never ships.
- **A reusable workflow that needs more than `contents: read` declares nothing and lets the caller grant it.** A called workflow cannot request more than its caller has, and asking for more fails the run at *startup* — before any job, with no log to read. `release.yml` is the one case, and it says so in a comment at the top. This is not a style preference; declaring it there breaks every caller that grants less.
- **Never put a cloud credential in a workflow or a secret.** Cloud access is OIDC federation only (DES §4).
- **Never let CI hold production credentials.** Deploy is pull-based: CI publishes an artifact, the install pulls it.
- **Never move the `v1` tag as part of merging a pull request.** Releasing is a separate, deliberate step — see the README.
- Never add a step that writes to another repo without saying so plainly in the pull request. This repo reaches everything.
- **A workflow that runs `copier` against a private template MUST hand git a credential first.** copier shells out to its own `git clone`, and `actions/checkout`'s credential is local to the clone it made — so the template clone gets nothing and git asks for a username on a machine with no terminal:

  ```
  fatal: could not read Username for 'https://github.com'
  ```

  The fix is a global URL rewrite before the copier call, using whichever token can read the template:

  ```bash
  git config --global \
    url."https://x-access-token:${GH_TOKEN}@github.com/".insteadOf \
    "https://github.com/"
  ```

  This has been rediscovered **four times**. Two consequences worth knowing before writing the fifth: the token must be scoped to reach the *template's* repository, not just this one — `create-github-app-token` scopes to the current repo unless given `owner:` — and **a public repository cannot do this at all**, because a fork's pull request must never be handed a credential that reads a private repo. That is why the fixture-drift check lives in `scaffolds` and not here.
- Do not restate rules from the DES here. Link to them. Two copies drift and the copy here is the one nobody updates.

## Docs

- One page per workflow in [`docs/`](docs/) — start with [`docs/docs-ci.md`](docs/docs-ci.md).
- Versioning, releasing, and the access setting private callers depend on: [`README.md`](README.md).
- The rules this machinery enforces: [datumlabsio/datum-standards](https://github.com/datumlabsio/datum-standards).
