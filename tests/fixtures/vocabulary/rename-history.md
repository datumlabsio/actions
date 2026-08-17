# Fixture: an allowlisted history note

Used by `self-test.yml` to exercise `vocabulary-allow-files`. This file contains
a retired term on purpose, and the check must still pass because the file is
allowlisted.

Naming history: the API kind was `ServiceManifest`, then `BlockManifest`, and is
now `ApplicationManifest`.

That is what the allowlist is for — history notes, terminology bridges, and
rejected proposals need the old word to do their job. If the allowlist ever
stops working, this file makes the check fail.
