# `application` — the caller surface for an installed application

```yaml
jobs:
  ci:
    uses: datumlabsio/actions/.github/workflows/application.yml@v0.13.0
```

DES §8: an application is *"an installed application or platform component"*, it is containerised, and it deploys via the install's GitOps.

## What it runs

`commit-lint` and `python-ci` — with **coverage on**, because §11 scopes the 80% requirement to `application`, `web-app` and `dagster-user-code`. `dlt-pipeline` is exempt, which is why `python-ci` has coverage off by default and this wrapper turns it on.

## What it deliberately does not run

**The container half.** The generated `ci.yml` calls `container-ci` directly as its own job rather than through this wrapper.

`container-ci`'s publish job needs `packages: write`, and a called workflow cannot request more permission than its caller holds. Threading that grant through a wrapper adds a level for it to traverse — and when it is missed the run dies at **startup, with no jobs and no log**. That has cost an hour twice already, in B-41 and again in B-14.

One less level is one less place to get it wrong.

## The §11 phase-in

Coverage is **reported in every phase** so the number is visible and the trend is real. The threshold is enforced only once `phase: production`.

Reporting unconditionally is what stops *"we'll add tests later"* from being invisible. Flip a repo with `copier update -d phase=production`.

`self-test` drives both branches directly, because a passing fixture cannot exercise the below-threshold path — and getting it backwards either blocks every draft repo or silently exempts production.

## No `if:` on the `title` job

Guarding a `uses:` job makes it skippable, and a skipped job holding a relative reference inside a cross-repository called workflow kills the run at startup on a push. That is B-52, and it broke every scaffolded repo's default branch for nine releases.

The toggle lives inside `commit-lint.yml` as an input instead.
