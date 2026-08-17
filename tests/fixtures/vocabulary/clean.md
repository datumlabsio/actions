# Fixture: clean vocabulary

Used by `self-test.yml` to exercise the retired-vocabulary check. This file uses
current vocabulary only, so the check must pass on it.

An **application** is an installed tool with a tile in my-apps. It joins the
platform through one `ApplicationManifest`. Delivery items are named concretely:
pipeline, model, dashboard, metric, alert, agent. A tool **implements** a
**protocol**.

If someone adds a retired term to this file, the check should fail. That is the
point of the fixture.
