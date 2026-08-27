# rendered-monorepo — A real scaffold render, used as a fixture

## Context

Archetype `monorepo` (DES §8). Born from `datumlabsio/scaffolds`;
`.copier-answers.yml` records which version, and the org conformance workflow
reads it.

CI is a thin caller to `datumlabsio/actions`, pinned to `v0.20.0`.
Org defaults — pull request template, issue forms, security policy — come from
`datumlabsio/.github` and are not files in this repo.

This is a **monorepo**: several components, each in its own folder, one set of
root files. Folders: `gitops`, `web-app`, `dbt-project`, `dlt-pipeline`.

Each folder has its own `CLAUDE.md` with the commands and guardrails for that
component. This file holds what is true for the whole repo — conventions and
guardrails live here and are not restated per folder (DES §7).

Each folder was rendered from its own archetype and keeps its own
`.copier-answers.*.yml`, so each is upgraded on its own with
`copier update -a .copier-answers.<name>.yml` from inside that folder. A
template fix for one component does not touch the others.

CI runs only the components whose folders changed.



## Commands

```bash
copier update --trust    # take improvements, or change an answer
```

It re-asks with your current answers filled in, so changing one is a keystroke on
that question and enter through the rest.

**Adding a component** is the same command: the folder list arrives with your
current folders already ticked — space the new one and `ci.yml` picks up its jobs
on its own. If you script it with `-d folders=[...]` instead, name EVERY folder
you want to keep; a list answer replaces rather than appends, and the interactive
form is the one that cannot drop a folder by accident.

```bash
```

## Conventions

- **Vocabulary is load-bearing** (RFC-0008). `install` = one client deployment.
  `application` = an installed tool with a my-apps tile. The two structural
  words are **protocol** and **implements**. `service`, `role` and `binding` are
  retired as categories.
- **Never write bespoke CI.** A gate is fixed in `datumlabsio/actions` and the
  pin here is bumped. If a check is wrong, it is wrong for everyone.
- **The template owns some files.** `.copier-answers.yml`, the CI caller,
  `renovate.json` and any vendored config are bumped by `copier update`, never
  hand-edited — an edit is lost on the next update and breaks the fleet-upgrade
  path.
- **Renovate opens the bumps.** It inherits every rule from
  `datumlabsio/.github`, so this repo configures nothing. A bump to
  `datumlabsio/actions` arrives as its own pull request; tool pins arrive grouped
  on a Monday. Merging those is how this repo stays current.
- Conventional Commits. Branches `feat/…` `fix/…` `chore/…`, short-lived.

## Guardrails

- **NEVER commit a secret**, or a plaintext value that resolves to one. Only
  references to the secret manager. Push protection has no exceptions (DES §6).
- **NEVER push directly to `main`.** Branch, pull request, review.
- **NEVER hand-edit a file the template owns.** Bump instead.
- **NEVER weaken a linter or a gate to make a check pass.** That is a spec
  change, and it goes through the RFC process.
- **NEVER let CI hold production credentials.** CI publishes an artifact; the
  install pulls it (DES §4).
- **EVERY install's cluster can read this entire repo.** `gitops/` lives here, and
  in GitOps the cluster pulls — so each install's Flux has read access to the
  whole monorepo, not just its own folder. That is repo-level access and no
  folder layout changes it. Treat everything committed here as visible to every
  install: no client-specific secret, no credential, and nothing one client must
  not see about another.
- **NEVER add a root-level CI file, CODEOWNERS or CLAUDE.md inside a component
  folder.** GitHub reads workflows only from the repo root, so a copy in a folder
  does nothing at all — silently.
- **NEVER hand-edit a component's `.copier-answers.*.yml`.** It records which
  template version that folder came from; `copier update` reads it.

## Docs

- What the archetype's CI does: `datumlabsio/actions/docs/`
- The rules all of this enforces: [datumlabsio/datum-standards](https://github.com/datumlabsio/datum-standards)
