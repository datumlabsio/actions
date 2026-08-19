# `web-ci.yml` and `web-app.yml`

CI for JavaScript / TypeScript. `web-app.yml` is the surface a repo calls; `web-ci.yml` is where the gates live.

Toolchain per DES §5 (RFC-0011): **pnpm** for packages, **turbo** for workspaces, **Biome** for lint and format, **TypeScript** strict, **Vitest** for tests and coverage.

## Calling it

```yaml
jobs:
  ci:
    uses: datumlabsio/actions/.github/workflows/web-app.yml@v0.5.0
    with:
      phase: draft
```

## Inputs

| Input | Default | What it does |
|---|---|---|
| `working-directory` | `.` | Where the project is, for a monorepo component |
| `config-dir` | `.` | Where the vendored configs are, relative to `working-directory` |
| `lint` / `typecheck` / `test` / `build` | `true` | Individual gates |
| `phase` | `draft` | `draft` or `production` — see coverage below |
| `coverage-threshold` | `80` | Percent required once a repo serves production |
| `upload-artifacts` | `true` | Upload `dist`/`.next` and the coverage report |
| `commit-lint` | `true` | Validate the pull request title (§3) |

## Coverage is reported always, gated by phase

DES §11 as amended by RFC-0011: a `draft` repo **MUST report** coverage but **MAY** fall below 80%; a repo serving **production MUST meet it**.

Reporting is unconditional on purpose. A repo with no tests reports 0% rather than nothing, so "we'll add tests later" is visible in every run instead of being invisible until someone flips the repo to production and CI suddenly blocks.

The number goes to the job summary as well as the log.

## What the repo must carry

Vendored by the scaffold, read by CI, bumped never hand-edited:

| File | Why CI needs it |
|---|---|
| `web-tool-versions.txt` | The pinned `node` and `pnpm`. **Missing this fails the run** rather than falling back to whatever the runner ships — a silent fallback means local and CI diverge, which is the whole thing vendoring exists to prevent. |
| `biome.json` | The org's lint and format rules. Missing fails the lint gate. |
| `tsconfig.base.json` | Strict compiler options for the repo's `tsconfig.json` to extend. |
| `pnpm-lock.yaml` | CI installs with `--frozen-lockfile`, so a lockfile that does not match `package.json` fails instead of quietly resolving something else. |

## Two pnpm behaviours that will bite you

Both are supply-chain controls worth keeping, and both need a declaration rather than a workaround.

**Install scripts are blocked by default.** pnpm will not run a dependency's `postinstall` unless it is allowlisted, and it hard-errors rather than skipping. An arbitrary `postinstall` is how a compromised package gets code execution, so the default is right (§6). Declare only what genuinely needs it, in `pnpm-workspace.yaml`:

```yaml
onlyBuiltDependencies:
  - esbuild        # places a platform binary; vite cannot build without it
```

**Packages published very recently are refused.** pnpm enforces a `minimumReleaseAge`, which is what catches a freshly-compromised release before anyone notices. The catch is transitive: a range like `vitest@^4.1.0` resolves to the newest match, so a patch published hours ago gets pulled in and rejected even when your direct pin is older. Hold the family at the aged version:

```yaml
overrides:
  vitest: 4.1.10
  "@vitest/spy": 4.1.10
  # ...the rest of the @vitest/* packages
```

If you hit `ERR_PNPM_OUTDATED_LOCKFILE` or a policy rejection after adding overrides, the lockfile predates them. Delete it and re-resolve once; commit the result.

## Why the pinned versions are not the newest

`web-tool-versions.txt` pins **Node 24** (Active LTS, not the newest release) and **TypeScript 5.9** rather than 7.x. TypeScript 7 is the native rewrite and had a single patch release when this was pinned; 5.9 has two dozen and is what the org's front ends already run.

A standard pins proven. Renovate opens the major bump when the ecosystem has caught up, and that arrives as a reviewable pull request in each repo rather than as a surprise.

The same logic sets the floor for everything else: pins are chosen with at least ten days of release age, so pnpm's own policy accepts them.

## Not here yet

`scan → publish`. DES §8 says `web-app` deploys as a container, and the container registry is not chosen. This covers everything up to the artifact and stops. Adding those stages later is additive — no caller changes.
