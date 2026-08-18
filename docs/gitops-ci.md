# gitops-ci

CI for the `gitops` archetype: one install's desired state, pulled by that install's Flux.

Every gate runs **without a cluster**. `kustomize build` renders offline and `kubeconform` validates the result, so a pull request is checked in seconds rather than against a live reconciler. Nothing here needs cluster credentials, and nothing here is granted any — Flux pulls from the repo (DES §4).

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
    uses: datumlabsio/actions/.github/workflows/gitops-ci.yml@v0.2.0
```

## Inputs

| Input | Type | Default | What it does |
|---|---|---|---|
| `root` | string | `"."` | Directory holding the desired state. |
| `config-dir` | string | `"."` | Where the vendored configs live, relative to `root`. |
| `kubernetes-version` | string | `"1.31.0"` | API version kubeconform validates against. |
| `generic-paths` | string | `"platform applications charts"` | Paths that must stay reusable across installs. Empty skips. |
| `chart-paths` | string | `"charts"` | Where charts we author live. Empty skips helm lint. |
| `yamllint` | boolean | `true` | yamllint against the shared config. |
| `build` | boolean | `true` | `kustomize build` every overlay, then validate the output. |
| `ignore-missing-schemas` | boolean | `false` | Let kubeconform pass a CR it has no schema for. |
| `image-pinning` | boolean | `true` | Fail on `:latest` or an untagged image. |
| `plaintext-secrets` | boolean | `true` | Fail on a Secret with inline data. |

## The gates

**Vendored configs present and stamped.** `.yamllint` and `gitops-tool-versions.txt` must exist and carry a `# datum-config:` stamp. The tool versions come from that file, so a local run and CI install the same ones.

**Build every overlay, validate the output.** Every directory containing a `kustomization.yaml` is built, and the rendered manifests are checked against real API schemas — including Flux's own CRDs, from the community catalog. `ignore-missing-schemas` is **off** by default: a CRD with no schema is unvalidated, and silently unvalidated is how a broken manifest reaches a cluster. A repo with no `kustomization.yaml` anywhere is an error.

**Images are pinned.** An image on `:latest`, or with no tag, means the cluster's actual state depends on when it last pulled — and rollback (DES §10) cannot work against that. A digest is better than a tag.

**No plaintext secrets.** A `Secret` carrying inline `data` or `stringData` belongs in the secret manager, referenced by SealedSecret or ExternalSecret. DES §6 has no exceptions.

**Reusable paths name no install.** A hostname or IP under `platform/`, `applications/` or `charts/` means that component has quietly stopped being reusable, and it can no longer be updated from the scaffold. Move it to this install's values.

Two things this gate deliberately does not flag:

- **A four-part image tag.** `clickhouse-server:24.8.4.13` looks exactly like an IPv4 address. An IP must be a standalone token, so a version tag preceded by `:` is not one.
- **`image:` lines at all.** A registry hostname and a version tag are the image-pinning gate's business, not this one.

Both were false positives found by running the gate against a clean fixture — the control case earning its keep.

## Running the same checks locally

```bash
yamllint -c .yamllint .
for d in $(find . -name kustomization.yaml -exec dirname {} \;); do
  kustomize build "$d" | kubeconform -strict -summary \
    -kubernetes-version 1.31.0 -schema-location default \
    -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'
done
```

Same pinned versions, same result.

## The fixture

`tests/fixtures/gitops-ok/` is a real Flux tree — a `HelmRelease` referencing a third-party chart by exact version, a Deployment on a digest-pinned non-root image, a library chart we author, and a `values/` directory for this install's specifics. `self-test` runs this workflow against it on every pull request.

It also shows the split the reusable-paths gate depends on: nothing under `platform/` or `applications/` names a client; anything that does lives in `values/`.
