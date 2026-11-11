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

**The pushed image is the scanned image** — the same bytes, not a rebuild. `build-scan` builds each platform once, to an OCI archive; the SBOM and the scan read that archive; `publish` pushes it with `skopeo` and builds nothing. On the way it checks every blob's sha256 and size, refuses if the platforms it holds are not exactly the ones asked for, and after each push asks the registry for what it now holds and compares digests. `publish` used to rebuild the image and push the rebuild: a second build nothing had scanned, and half of every release's minutes.

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
| `build-args` | *(empty)* | `KEY=VALUE` per line, into **both** builds |
| `publish` | `false` | only ever true on the default branch |
| `registry` | `ghcr.io` | anything else: image goes to `<registry>/<image-name>` via Workload Identity; caller grants `id-token: write` |
| `workload-identity-provider` | *(empty)* | required unless `ghcr.io`; pass a variable, never a literal |
| `service-account` | *(empty)* | required unless `ghcr.io` |
| `platforms` | *(empty)* | e.g. `linux/amd64,linux/arm64`. Each architecture builds **natively**, arm64 on GitHub's `ubuntu-24.04-arm`; `build-scan` SBOMs and scans every platform, and `gate-on` applies to each, before `publish` pushes them; see [`platforms`](#platforms) |
| `latest` | `true` | also move `latest` to this build, pushed after the SHA and version tags. Set `false` for a registry with tag immutability (Artifact Registry), which refuses to move it |
| `also-registry` | *(empty)* | a second registry, reached by Workload Identity, that gets **the same scanned image** under the SHA and version, never `latest`. One build for both; see [`also-registry`](#also-registry) |

`publish` defaults to false deliberately. A pull request from a fork must not be able to push an image.

### `build-args`

One `KEY=VALUE` per line. Blank lines are ignored, and a value may contain spaces.

```yaml
with:
  image-name: polaris-introspector-heavy
  build-args: |
    PROFILE=heavy
```

It exists for an image with **more than one shape from one Dockerfile** — a lean build and a heavy one carrying extra SDKs, say. Without it the only way to publish the second shape is a duplicated Dockerfile, which drifts from the first in a way nobody notices until the two disagree.

The args go to the scanned build **and** the published build, because those must be the same image. Passing a profile to one and not the other would publish a variant nothing had scanned while the run still went green.

**Never pass a secret.** A build argument is recorded in the image's own metadata, and `docker history` prints it back out of any pulled copy — a token passed here ships to everyone who can pull the image. Use it for build-time *shape*: a profile, a variant, a feature flag. Nothing that would matter if it were published, because it is.

### `platforms`

```yaml
with:
  platforms: linux/amd64,linux/arm64
```

`build-scan` runs **one leg per architecture, each on a runner of that architecture**: `build-scan` on `ubuntu-latest` for amd64 (and, under QEMU, anything GitHub has no runner for), `build-scan (arm64)` on `ubuntu-24.04-arm` for arm64. Each leg builds its platforms to OCI archives, writes an SBOM per platform (`sbom-linux-arm64.spdx.json`; the arm64 leg's go in `sbom-<sha>-arm64`), and runs Trivy on each. With `gate-on`, one platform over the line fails its leg, and publish never starts. `publish` joins the legs' archives into one multi-arch image and pushes it.

Before #113 was fixed, only the runner's native amd64 build was scanned, and an arm64 half reached the registry having passed no scan. The arm64 half used to be built under QEMU on an amd64 runner — about 15 minutes an image against 3 natively — and then built a second time in `publish`. On a polaris release of ten images that was most of the Actions bill. GitHub has offered arm64 runners to private repositories since January 2026; they count against the same included minutes.

Without `platforms`: one native linux/amd64 build, one `sbom.spdx.json`, one scan, pushed as a plain single-platform manifest, as before — now an OCI manifest rather than Docker's own format, which every registry and runtime we pull from reads.

### `also-registry`

```yaml
permissions:
  contents: read
  packages: write   # GHCR
  id-token: write   # Workload Identity, for also-registry
with:
  platforms: linux/amd64,linux/arm64
  also-registry: ${{ vars.CHART_REGISTRY }}
  workload-identity-provider: ${{ vars.GCP_WIF_PROVIDER }}
  service-account: ${{ vars.GCP_PUBLISHER_SA }}
```

For an image that has to be in two registries — GHCR for Proxmox and Artifact Registry for installs, in polaris's case. It used to take two calls, so two complete builds and scans of the same sources; now one build is scanned once and pushed to both. The second registry gets the SHA and version tags and never `latest`, because it is there for a registry with tag immutability. Empty pushes to `registry` only.

One job pushes to both, so a failure on the second registry can leave the tags already pushed to the first. They are the scanned image either way; re-run the failed job and it completes the second.

## The hadolint config

The lint stage reads `<config-dir>/hadolint.yaml` if the repo has vendored one, exactly as it reads `container-tool-versions.txt`. **Absent means unchanged** — hadolint's built-in defaults, which is what every caller got before the file existed.

Vendor it the usual way: copy `configs/hadolint.yaml` from this repo, keep the `# datum-config:` stamp, and bump rather than edit. A local `hadolint` run then reads the same rules CI does.

It currently waives one rule, **DL3008** (pin versions in `apt-get install`), and the file carries the written reason DES §5 requires. The short version: an exact apt pin stops resolving the moment Debian issues a point release, so the build fails on a commit nobody touched, and nothing bumps apt pins for us. Digest-pinned bases (DL3006), the SBOM and the Trivy scan cover the same ground without that failure mode.

## One thing that will bite on a bump

**hadolint renamed its release assets.** v2.12.0 shipped `hadolint-Linux-x86_64`; v2.15.1 ships `hadolint-linux-x86_64` — lowercase. A version bump alone changes the download URL, and the failure is a 404 during install rather than anything that looks like a version problem.

I wrote the capitalised form from memory and it would have 404'd on the first run.

## Verified

`self-test` runs the workflow against `tests/fixtures/container-ok` — which builds for real, from a base pinned by a **resolvable** digest, because a fixture that cannot build proves nothing about a workflow whose job is building. It runs it a second time with `platforms: linux/amd64,linux/arm64`, so the multi-platform path (a native arm64 leg, a build, SBOM and scan per platform) is exercised on every pull request too.

`publish` never pushes anywhere real from `self-test` — a pull request from a fork must never be able to — so `container-publish-end-to-end` runs its own `Build`, `Join` and `Push` steps, cut out of the workflow file, against a registry that lives only inside that job. It asserts the registry holds exactly the scanned manifests under the right tags, that the second registry never gets `latest`, that one platform is pushed as a plain manifest, and that one changed byte in a scanned layer, or a platform whose archive never arrived, stops publish before it pushes. `tests/merge_oci_unit.py` runs 26 further cases against the shipped copy of the merge.

And directly against `tests/fixtures/container-bad`, which must be refused: `:latest`, unpinned apt packages, no cache cleanup, `ADD` from a URL, and a shell-form `CMD`.
