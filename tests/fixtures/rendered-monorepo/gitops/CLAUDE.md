# gitops — this install's desired state

Local context for this folder only. Conventions and guardrails for the whole
repo are in the root `CLAUDE.md`; nothing here restates them.

## Commands

```bash
kustomize build .                       # renders offline, no cluster needed
kubeconform -strict -summary <(kustomize build .)
helm lint charts/*
yamllint -c .yamllint .
```

Exactly what CI runs, from the versions pinned in `gitops-tool-versions.txt`.

## Guardrails

- **NEVER apply to a cluster from a laptop** to fix drift. Change desired state
  and let the reconciler converge, or the cluster and this folder disagree
  silently and the next reconcile undoes your fix.
- **NEVER hand-edit a file Flux manages.** It is overwritten on the next
  reconcile. Change the source.
- **NEVER put a hostname, an IP or a client name** in `platform/`,
  `applications/`, `charts/` or `policies/`. Those stay reusable so
  `copier update` can improve them. It goes in `values/`, and CI fails the build
  if it does not.
- **NEVER use `:latest` or an untagged image.** The cluster's actual state would
  stop being derivable from this folder.
- Layer order is dependency order: `policies` → `platform` → `applications`.
