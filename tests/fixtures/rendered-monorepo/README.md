# rendered-monorepo

A real scaffold render, used as a fixture

Archetype `monorepo` (DES §8). Born from `datumlabsio/scaffolds`; the
version it came from is recorded in `.copier-answers.yml`.

## Running the checks

CI runs every gate on your pull request, so nothing below is required.

Optionally, wire the same pre-commit hooks into your own clone so they run on
`git commit` instead of after a push:

```bash
pre-commit install
```

It is a one-off per clone. Git hooks live in `.git/`, which is not version
controlled, so committing the config cannot do this for you.

CI runs the `monorepo` archetype workflow from `datumlabsio/actions`,
pinned to `v0.27.1`. To reproduce it locally, see `CLAUDE.md`.

## Changing it

Branch, pull request, review by a code owner. No direct pushes to `main`.

This repo is in **draft** phase: pull requests are required, and approvals are
set to 0 until it serves production (DES §3).

## Upgrading from the scaffold

The template improves over time. To take those improvements:

```bash
copier update --trust
```

Review the diff like any pull request. Files the template owns are **bumped,
never hand-edited** — that includes the vendored configs and the CI caller.
