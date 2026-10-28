# `chart-publish` — lint, package, push Helm charts

```yaml
jobs:
  charts:
    uses: datumlabsio/actions/.github/workflows/chart-publish.yml@vX.Y.Z
    permissions:
      contents: read
      id-token: write          # packages: write instead, for ghcr.io
    with:
      registry: ${{ vars.CHART_REGISTRY }}
      version: ${{ needs.release.outputs.version }}
      workload-identity-provider: ${{ vars.GCP_WIF_PROVIDER }}
      service-account: ${{ vars.GCP_PUBLISHER_SA }}
      publish: true
```

Charts land at `oci://<registry>/charts/<name>:<version without v>`. Dependencies must be vendored in each chart's `charts/`; nothing is fetched.

| Input | Default | |
|---|---|---|
| `registry` | *(required)* | no `oci://`; `ghcr.io/…` logs in with `GITHUB_TOKEN`, anything else with Workload Identity |
| `version` | *(required)* | release tag `v1.4.2`; chart version `1.4.2`, app version `v1.4.2` |
| `charts-dir` | `charts` | every subdirectory with a `Chart.yaml` |
| `config-dir` | `.` | where `gitops-tool-versions.txt` is vendored (helm version) |
| `workload-identity-provider` | *(empty)* | required unless `ghcr.io`; pass a variable, never a literal |
| `service-account` | *(empty)* | required unless `ghcr.io` |
| `publish` | `false` | only ever true on a release |
