# `container-ci` — lint, build, SBOM, scan, publish

```yaml
jobs:
  container:
    uses: datumlabsio/actions/.github/workflows/container-ci.yml@v0.12.0
    permissions:
      contents: read
      packages: write
```

## The order is the control

`lint → build → SBOM → scan → publish`, and **publish is a separate job that `needs` the scan**.

Not a step after the scan — a *job*. A step can be reached by a workflow edit that moves it above the scan; a job dependency cannot be satisfied by a scan that failed. Scanning after publishing tells you what you have already shipped.

The scanned image is the built image, not a rebuild. Scanning something you rebuilt proves nothing about what ships.

## Why GHCR

**Publishing needs no credentials.** `GITHUB_TOKEN` is already scoped to the registry. ECR would put long-lived AWS keys in CI.

§4 says CI publishes an artifact and the install pulls it. The fewer secrets in the publishing half, the more that holds.

## Reporting before gating

`gate-on` is **empty by default** — Trivy reports and does not fail.

A base image carries findings nobody has triaged. Gating on day one blocks the first author to touch a Dockerfile for something they did not cause and cannot fix, and that is how a gate gets routed around rather than respected.

Set `gate-on: CRITICAL` once the real number is known. Same phase-in as §11 coverage.

## Inputs

| Input | Default | |
|---|---|---|
| `dockerfile` | `Dockerfile` | |
| `image-name` | the repo name | right for one image, wrong for a monorepo — pass it there |
| `hadolint` | `true` | a finding fails |
| `sbom` | `true` | syft, SPDX, kept 30 days |
| `scan-severity` | `HIGH,CRITICAL` | what Trivy **reports** |
| `gate-on` | *(empty)* | what **fails** the build |
| `publish` | `false` | only ever true on the default branch |

`publish` defaults to false deliberately. A pull request from a fork must not be able to push an image.

## One thing that will bite on a bump

**hadolint renamed its release assets.** v2.12.0 shipped `hadolint-Linux-x86_64`; v2.15.1 ships `hadolint-linux-x86_64` — lowercase. A version bump alone changes the download URL, and the failure is a 404 during install rather than anything that looks like a version problem.

I wrote the capitalised form from memory and it would have 404'd on the first run.

## Verified

`self-test` runs the workflow against `tests/fixtures/container-ok` — which builds for real, from a base pinned by a **resolvable** digest, because a fixture that cannot build proves nothing about a workflow whose job is building.

And directly against `tests/fixtures/container-bad`, which must be refused: `:latest`, unpinned apt packages, no cache cleanup, `ADD` from a URL, and a shell-form `CMD`.
