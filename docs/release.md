# release

Cuts a SemVer release from Conventional Commits, and refuses to move a tag that already exists. [DES §3](https://github.com/datumlabsio/datum-standards/blob/main/standards/engineering/README.md) requires SemVer cut by CI; §10 requires that a published version is never changed.

## Calling it

```yaml
name: release
on:
  push:
    branches: [main]

permissions:
  contents: write

jobs:
  release:
    uses: datumlabsio/actions/.github/workflows/release.yml@v0.1.0
```

Pair it with `commit-lint.yml` on pull requests, so a merge cannot produce a commit this workflow has no version for.

## Inputs

| Input | Type | Default | What it does |
|---|---|---|---|
| `tag-prefix` | string | `"v"` | Prefix on the tag. Empty for a bare SemVer. |
| `dry-run` | boolean | `false` | Work out the version, print it, stop. Nothing tagged or published. |
| `create-github-release` | boolean | `true` | Publish a GitHub Release with generated notes. |

## Outputs

| Output | What it is |
|---|---|
| `version` | The version cut, or empty when there was nothing to release |
| `released` | `'true'` when a tag was created |

## How the version is worked out

Commits since the last tag, by Conventional Commit type:

| In the commits | Bump |
|---|---|
| `!` after the type, or a `BREAKING CHANGE:` footer | major — but see below |
| `feat:` | minor |
| `fix:` or `perf:` | patch |
| anything else only — `chore`, `docs`, `ci`, `refactor`, `test`, `style`, `build` | **no release** |

The highest applicable bump wins, so one `feat:` among ten `fix:` commits gives a minor.

**Below 1.0.0 a breaking change is a minor bump**, which is what SemVer says and what stops a pre-1.0 repo racing to v9 while it is still finding its shape.

**No releasable commits is a success, not a failure.** A pull request that only touches documentation should not cut a version, and should not go red for it either.

**`BREAKING CHANGE:` is looked for in the subject as well as the footer.** Conventional Commits puts it in a footer after a blank line, but git folds an unseparated footer into the subject — and quietly turning a breaking change into a minor bump is the expensive mistake, so layout is treated leniently.

**Tags are read in version order, not by date.** A tag pushed late must not look like the latest release, or the next version is derived from the wrong base.

## Tags are never moved

Before tagging, the workflow checks the tag does not exist locally *and* does not exist on the remote, and fails if either does. `git push` is never given `--force`.

This is checked rather than trusted because the failure is silent: a moved tag means every caller pinned to it receives different code, with nothing in their own repo having changed. That is also why callers pin an exact version rather than a moving major.

## Permissions

**The caller grants `contents: write`**; this workflow declares no `permissions:` block of its own.

That is a constraint, not a choice. A called workflow cannot request more than its caller has, and asking for more fails the run at startup — before any job, with nothing in the log to explain it. So the requirement lives with the caller:

```yaml
permissions:
  contents: write
```

A caller that grants only `contents: read` can still call this with `dry-run: true`, which is exactly what `self-test` does.

## The pull-request half

`commit-lint.yml` validates the pull request *title*, because a squash merge uses the title as the commit message on `main`. An unconventional title becomes a commit this workflow cannot derive a version from, so the check belongs on the pull request rather than after the merge.

```yaml
jobs:
  title:
    uses: datumlabsio/actions/.github/workflows/commit-lint.yml@v0.1.0
```

Its `allow-types` input takes a pipe-separated list, if a repo needs a type the default set does not have.
