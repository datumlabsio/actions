#!/usr/bin/env python3
"""Mint a short-lived installation token for the runner App.

    APP_ID=... APP_PRIVATE_KEY_PATH=... ORG=... python3 app-token.py

Prints an installation access token and nothing else.

WHY AN APP AND NOT A PAT. A PAT on disk IS the credential -- read the file, use
it immediately, and it lives for months. It also belongs to a PERSON: when they
leave or rotate it, runners stop registering.

An App's private key needs a signed JWT exchange before it is worth anything,
the resulting token expires in an hour, and it belongs to the organisation. The
key on disk is still a long-lived secret -- this narrows the blast radius, it
does not remove it.

The App holds `organization_self_hosted_runners: write` and NOTHING else. It
cannot read a repository, cannot push, cannot see a secret. If this VM is
compromised the attacker can register and remove runners, which is a nuisance
rather than an incident.

No dependencies beyond the standard library and `openssl`, because this runs on
a machine we deliberately keep thin.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request


def b64(data: bytes) -> str:
    """JWT wants base64url with no padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_jwt(app_id: str, key_path: str) -> str:
    now = int(time.time())
    # 60 seconds in the past absorbs clock skew between this VM and GitHub --
    # a fast clock here makes every token "issued in the future" and rejected.
    payload = {"iat": now - 60, "exp": now + 540, "iss": app_id}
    signing_input = f"{b64(json.dumps({'alg': 'RS256', 'typ': 'JWT'}).encode())}." \
                    f"{b64(json.dumps(payload).encode())}"
    sig = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", key_path],
        input=signing_input.encode(), capture_output=True, check=True).stdout
    return f"{signing_input}.{b64(sig)}"


def api(url: str, token: str, method: str = "GET") -> dict:
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        # Never print the JWT or the key path in an error: this runs in a
        # service log that is easier to read than /etc.
        sys.exit(f"GitHub said {e.code} for {method} {url}\n{body}")


def main() -> int:
    app_id = os.environ.get("APP_ID")
    key_path = os.environ.get("APP_PRIVATE_KEY_PATH")
    org = os.environ.get("RUNNER_ORG")
    if not (app_id and key_path and org):
        sys.exit("set APP_ID, APP_PRIVATE_KEY_PATH and RUNNER_ORG")
    if not os.path.isfile(key_path):
        sys.exit(f"no private key at {key_path}")

    jwt = make_jwt(app_id, key_path)
    inst = api(f"https://api.github.com/orgs/{org}/installation", jwt)
    tok = api(inst["access_tokens_url"], jwt, method="POST")
    print(tok["token"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
