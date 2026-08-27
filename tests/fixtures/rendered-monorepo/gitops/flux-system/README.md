# flux-system

Flux's own manifests: the `GitRepository` pointing at this repo, and the root
`Kustomization` that reconciles `../`.

Written here by `flux bootstrap` on first install, then owned by Flux and
committed like anything else. **Do not hand-edit a file Flux manages** — it is
overwritten on the next reconcile. Change the source and let it converge.

This directory is deliberately empty in the scaffold: bootstrap output depends
on the cluster and the credentials used, so generating a placeholder here would
mean committing something wrong.
