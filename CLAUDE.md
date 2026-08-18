# datumlabsio/actions — reusable CI workflows for every repo in the org

## Context

Archetype `docs` for its own purposes, but what it produces is CI. One of the three org repos in DES §2, alongside `datumlabsio/.github` (org defaults) and `datumlabsio/scaffolds` (templates per archetype).

Every repo in the org runs its CI by calling a workflow here, pinned to a version tag. Bespoke CI is forbidden. That means **this repo is a single point of failure for the whole fleet** — a bad change merged here breaks every repo's CI at once, not one repo's. Treat every change as fleet-wide, because it is.

Reusable workflows must live in `.github/workflows/`. GitHub does not find them anywhere else.

## Commands

```bash
# Workflows must parse. A malformed workflow fails at dispatch with a useless message.
python3 -c "import glob,yaml,sys; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('WORKFLOWS PARSE')"

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
- Do not restate rules from the DES here. Link to them. Two copies drift and the copy here is the one nobody updates.

## Docs

- One page per workflow in [`docs/`](docs/) — start with [`docs/docs-ci.md`](docs/docs-ci.md).
- Versioning, releasing, and the access setting private callers depend on: [`README.md`](README.md).
- The rules this machinery enforces: [datumlabsio/datum-standards](https://github.com/datumlabsio/datum-standards).
