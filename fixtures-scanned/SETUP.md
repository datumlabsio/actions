# Fixture: a private-key match that carries no private key

> **This lives outside `tests/` on purpose.** Semgrep's default ignore list
> excludes `tests/`, so a fixture kept there is never scanned -- the job that
> uses it passes while checking nothing. It was written under `tests/fixtures/`
> first and reported "Ran 1077 rules on 0 files". Do not move it back.

This is the shape real setup documentation takes, and it is the most common
false positive the security baseline meets on a repository it did not scaffold.

Semgrep's `detected-private-key` fires on it. It is not a finding: the block
stops after 52 bytes, which is the fixed OpenSSH format header. There is no
private material here, and those bytes are the same in every unencrypted key.

Nothing in this file is a secret. That is the whole point of the fixture.

```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
... (full private key) ...
-----END OPENSSH PRIVATE KEY-----
```
