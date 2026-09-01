#!/usr/bin/env python3
"""Exercise the placeholder-key filter that security-baseline.yml ships.

The script under test is EXTRACTED FROM THE WORKFLOW rather than kept beside
it. A copy would pass its tests while the workflow shipped something else --
which is the failure this repository has already been bitten by once.

No key material is committed. Real keys are generated here, at run time.
"""
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/security-baseline.yml"
MARKER = "DATUM_PLACEHOLDER_FILTER"

PLACEHOLDER_BODY = (
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW"
)


def extract_filter(dest: Path) -> Path:
    src = WORKFLOW.read_text()
    m = re.search(rf"<<'{MARKER}'\n(.*?)\n\s*{MARKER}", src, re.S)
    if not m:
        sys.exit(f"FAIL: no {MARKER} heredoc in {WORKFLOW.name} — did the step get renamed?")
    body = "\n".join(
        ln[10:] if ln.startswith(" " * 10) else ln for ln in m.group(1).split("\n")
    )
    out = dest / "placeholder_keys.py"
    out.write_text(body)
    return out


def real_key(path: Path, kind: str) -> None:
    """Generate a genuine private key. Never committed; lives in a temp dir."""
    if kind == "openssh-ed25519":
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)],
                       check=True)
        Path(str(path) + ".pub").unlink(missing_ok=True)
    elif kind == "pkcs8-ed25519":
        subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(path)],
                       check=True, capture_output=True)
    elif kind == "rsa":
        subprocess.run(["openssl", "genrsa", "-out", str(path), "2048"],
                       check=True, capture_output=True)
    elif kind == "ec":
        subprocess.run(["openssl", "ecparam", "-name", "prime256v1", "-genkey",
                        "-noout", "-out", str(path)], check=True, capture_output=True)


def pem_block(text: str) -> str:
    return "-----BEGIN OPENSSH PRIVATE KEY-----\n" + text + "\n-----END OPENSSH PRIVATE KEY-----\n"


def build_cases(d: Path):
    """(name, path, must_be_suppressed)."""
    cases = []

    # --- placeholders: must be suppressed ---
    p = d / "setup_truncated.md"
    p.write_text("Paste it:\n\n```\n" + pem_block(PLACEHOLDER_BODY + "\n... (full private key) ..."))
    cases.append(("openssh header truncated for docs", p, True))

    p = d / "no_body.md"
    p.write_text(pem_block("... your key ..."))
    cases.append(("no base64 body at all", p, True))

    # --- real keys: must all survive ---
    for kind, name in [
        ("openssh-ed25519", "complete OpenSSH ed25519"),
        ("pkcs8-ed25519", "complete PKCS#8 ed25519 (48 bytes -- SMALLER than the placeholder)"),
        ("rsa", "complete RSA 2048"),
        ("ec", "complete EC prime256v1"),
    ]:
        p = d / f"{kind}.pem"
        real_key(p, kind)
        cases.append((name, p, False))

    # The boundary: a real blob truncated EXACTLY where the private section
    # begins. Everything present is the public key, which is public by
    # definition, so this suppresses. Without this case a filter that never
    # reaches its own boundary check still passes.
    ossh = (d / "openssh-ed25519.pem").read_text().strip().split("\n")
    raw = base64.b64decode("".join(ossh[1:-1]))
    off = len(b"openssh-key-v1\x00")
    for _ in range(3):
        n = int.from_bytes(raw[off:off + 4], "big"); off += 4 + n
    off += 4                                    # nkeys
    n = int.from_bytes(raw[off:off + 4], "big"); off += 4 + n   # public key
    clipped = base64.b64encode(raw[:off]).decode()
    p = d / "public_half_only.md"
    p.write_text("```\n" + pem_block("\n".join(
        clipped[i:i + 70] for i in range(0, len(clipped), 70))) + "```\n")
    cases.append(("truncated exactly at the private boundary", p, True))

    # --- the adversarial one: a real key with its middle removed still leaks
    # private bytes, and partial-key recovery is a real attack. Must be kept.
    rsa = (d / "rsa.pem").read_text().strip().split("\n")
    body = rsa[1:-1]
    p = d / "elided_real.md"
    p.write_text("```\n" + "\n".join(
        [rsa[0]] + body[:3] + ["... (trimmed) ..."] + body[-3:] + [rsa[-1]]) + "\n```\n")
    cases.append(("real RSA with its middle elided", p, False))

    return cases


def main() -> int:
    if not shutil.which("openssl") or not shutil.which("ssh-keygen"):
        print("SKIP: openssl/ssh-keygen unavailable")
        return 0

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        script = extract_filter(d)
        sys.path.insert(0, str(d))
        import importlib.util
        spec = importlib.util.spec_from_file_location("pk", script)
        pk = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pk)

        cases = build_cases(d)
        failures = []
        for name, path, want_suppressed in cases:
            text = path.read_text().split("\n")
            line = next((i + 1 for i, ln in enumerate(text) if pk.BEGIN.search(ln)), 1)
            got, why = pk.classify(str(path), line)
            ok = got == want_suppressed
            verb = "suppressed" if got else "kept"
            print(f"    [{'ok' if ok else 'FAIL'}] {name}: {verb} — {why}")
            if not ok:
                failures.append(name)

        if failures:
            print(f"\nFAIL: {len(failures)} case(s): {', '.join(failures)}")
            return 1
        print(f"\nOK: {len(cases)} cases, none of them a length comparison")
        return 0


if __name__ == "__main__":
    sys.exit(main())
