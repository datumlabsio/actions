# applications

One directory per installed application. Each is a tile in my-apps and joins the
platform through one `ApplicationManifest` (DPS P1).

Add one by creating its directory, referencing the upstream chart at an **exact
version**, and adding it to `kustomization.yaml`.

**Nothing here names this install.** Hostnames, sizes and switches go in
`../values/`. That is what keeps a component updatable from the scaffold, and CI
fails a hostname found in this directory.
