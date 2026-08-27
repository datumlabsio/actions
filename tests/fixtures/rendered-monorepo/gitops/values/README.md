# This install's values

Everything specific to **this install** lives here, and nowhere else: hostnames,
domains, replica counts, resource limits, anything that differs between one
client's cluster and another's.

Why it is separated: `policies/`, `platform/`, `applications/` and `charts/` stay
reusable, so `copier update` can improve them without touching anything you have
tuned. CI fails the build if a hostname, an IP or a client name appears in those
paths.

The install this tree deploys to is whatever cluster pulls from this repo — the
tree does not name it, so nothing here has to be renamed if it moves.
