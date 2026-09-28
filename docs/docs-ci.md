# docs-ci

CI for the `docs` archetype (DES §8): standards repos, documentation repos, anything whose product is prose.

## Calling it

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  ci:
    uses: datumlabsio/actions/.github/workflows/docs-ci.yml@v0.1.0
```

That gives you the two checks that are on by default. Everything else you switch on for your repo.

## Inputs

| Input | Type | Default | What it does |
|---|---|---|---|
| `link-check` | boolean | `true` | Every relative markdown link must resolve to a file that exists. |
| `placeholder-paths` | string | `""` | Space-separated paths where `TODO` and `TBD` must not appear. Empty skips the check. |
| `vocabulary-denylist` | string | `""` | Pipe-separated terms that must not appear. Empty skips the check. |
| `vocabulary-scan-paths` | string | `"."` | Space-separated paths to scan for the denylist. |
| `vocabulary-allow-files` | string | `""` | Pipe-separated path fragments exempt from the denylist. |
| `rfc-dir` | string | `""` | Directory of numbered proposals. Set with `spec-dir`. |
| `spec-dir` | string | `""` | Directory of specs that proposals change. Set with `rfc-dir`. |

## A failing gate does not hide the next one

Every gate runs once setup has succeeded, whatever the gates before it did. The
job fails if any of them failed, so a run that was red stays red. What changes
is that you see every failure, not only the first.

Before this, a step's implicit `success()` meant one failing gate skipped every
gate after it, with nothing on the run to say so. In polaris, pre-existing mypy
errors meant the introspector's tests had not run on any pull request that
touched them.

If setup fails (checkout, vendored configs, installing dependencies), no gate
runs, because there is nothing to run one against.

The run summary reports what each gate **did**:

| Row | Means |
|---|---|
| Passed | ran, and succeeded |
| **Failed** | ran, and failed |
| **Skipped** | never ran: it switched itself off (a config not vendored), setup failed, or the run was cancelled |
| Off by config | not requested by the caller |

It used to report a gate as "Ran" whenever the caller requested it, including a
gate that was skipped behind an earlier failure.

## The checks

**Conflict markers.** Always on, cannot be turned off. Looks for `<<<<<<< ` and `>>>>>>> ` at the start of a line in any markdown file. A merge that left these behind should never have been merged.

**Relative links resolve.** Every relative markdown link that is not `http` or `mailto` must point at a file that exists. Anchors are ignored — this checks the file, not the heading. Fenced blocks and inline code are stripped before scanning, so a page that documents link syntax does not fail on its own examples.

**Placeholder rot.** `TODO` and `TBD` in finished prose mean the document is lying about being finished. Point this at the paths that are meant to be complete, not at working notes.

Fenced blocks and inline code are skipped — documenting the word is not the same as leaving one. HTML comments are **not** skipped, because a note to self in a comment is exactly what this check is for. A path that does not exist is an error, not a silent pass.

**Retired vocabulary.** When a word is replaced, the old one has to stop appearing or both live on forever.

Unlike the placeholder check, this one reads code as well as prose. That is deliberate: a retired identifier in a YAML example is a real occurrence, not an illustration. The consequence is that a page explaining the denylist will match its own examples — put that page in `vocabulary-allow-files`, or scan a narrower path.

`vocabulary-allow-files` is for the places where the old word is legitimately needed: history notes, terminology bridges, rejected proposals.

**Proposal status matches what shipped.** Only runs on pull requests, and only when both `rfc-dir` and `spec-dir` are set.

A proposal and the spec change it causes land on the same pull request. The proposal's status flips on that pull request, never afterwards. So if a pull request changes something under `spec-dir` and also touches a proposal under `rfc-dir`, that proposal must not still say `Status: Draft` — otherwise the repo ships a rule while calling it a proposal.

A pull request that only adds a Draft proposal passes. A pull request that only edits the spec passes. It is the combination that has to be consistent.

The check reads the first line matching `- **Status:**` in each changed proposal. `TEMPLATE.md` is skipped.

## Example: datum-standards

```yaml
jobs:
  ci:
    uses: datumlabsio/actions/.github/workflows/docs-ci.yml@v0.1.0
    with:
      placeholder-paths: "standards/ vision/"
      vocabulary-denylist: "catalog block|BlockManifest|decision product|Datum Services Standard"
      vocabulary-allow-files: "architecture.md|service-manifest.md|services/README.md"
      rfc-dir: "rfcs/"
      spec-dir: "standards/"
```

This replaces the checks that repo currently runs by hand out of its `CLAUDE.md`.

## Permissions

`contents: read`. The workflow reads the repository and nothing else. It does not comment, label, or write.
