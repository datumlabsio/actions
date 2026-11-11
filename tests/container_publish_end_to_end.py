#!/usr/bin/env python3
"""publish pushes what build-scan scanned -- end to end, against a real registry.

    python3 tests/container_publish_end_to_end.py

Needs docker, a buildx docker-container builder and skopeo, which is to say a
GitHub runner: self-test runs it in its own job.

self-test never publishes anywhere real, so publish's push path had no test at
all -- the job that decides what every release ships was first exercised by
each release. This runs container-ci's OWN step scripts, cut out of the
workflow file -- Build from build-scan, then Join and Push from publish --
against a registry that lives only in this job, and then asks the registry
what it holds:

  * a two-platform image whose platform manifests are byte for byte the ones
    build-scan built and scanned, under the SHA, version and `latest` tags on
    the primary registry, and SHA and version -- never `latest` -- on the
    second;
  * a single-platform image pushed as a plain manifest, as it always was;
  * refused, with nothing pushed: one changed byte in a scanned layer, and a
    platform whose archive never arrived.

The fixture is FROM scratch, so its arm64 half builds on an amd64 runner with
no emulation: what is under test is the archive handling, not the compiler.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WF = yaml.safe_load((ROOT / ".github" / "workflows" / "container-ci.yml").read_text())
REGISTRY_IMAGE = ("registry:2.8.3@sha256:"
                  "a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373")
SHA = "0123456789abcdef0123456789abcdef01234567"
FAILURES = []


def step(job, name):
    for s in WF["jobs"][job]["steps"]:
        if s.get("name") == name:
            return s["run"]
    sys.exit(f"FAIL: container-ci.yml has no step {name!r} in {job}")


BUILD = step("build-scan", "Build")
JOIN = step("publish", "Join the scanned platforms, checking every byte")
PUSH = step("publish", "Push what was scanned")


def check(name, ok, detail=""):
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' -- {detail}'}")
    if not ok:
        FAILURES.append(name)


def bash(script, env, cwd=None):
    # The shell GitHub runs a `run:` block with.
    return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
                          env={**os.environ, **env}, cwd=cwd, capture_output=True, text=True)


def raw(ref, conf):
    p = subprocess.run(["skopeo", "inspect", "--raw", f"docker://{ref}"],
                       env={**os.environ, "CONTAINERS_REGISTRIES_CONF": conf},
                       capture_output=True)
    return p.stdout if p.returncode == 0 else None


def scanned_digest(tar_path):
    """The image manifest digest inside one build-scan archive."""
    with tarfile.open(tar_path) as t:
        index = json.load(t.extractfile("index.json"))
        d = index["manifests"][0]
        if d["mediaType"].endswith("index.v1+json"):
            inner = json.load(t.extractfile("blobs/sha256/" + d["digest"].split(":")[1]))
            d = inner["manifests"][0]
    return d["digest"]


def build_leg(fixture, work, platform):
    env = {"RUNNER_TEMP": str(work), "LIST": platform, "DOCKERFILE": "Dockerfile",
           "BUILD_ARGS": "", "GITHUB_OUTPUT": str(work / "out")}
    work.mkdir(parents=True, exist_ok=True)
    p = bash(BUILD, env, cwd=fixture)
    if p.returncode != 0:
        sys.exit(f"FAIL: Build for {platform} did not build:\n{p.stdout}\n{p.stderr}")
    return work / "scanned" / (platform.replace("/", "-") + ".tar")


def hand_on(pub, archives):
    """Lay the archives out the way download-artifact does: one dir per artifact."""
    for arch, tar_path in archives.items():
        d = pub / "scanned" / f"scanned-selftest-0000000000000000-{arch}"
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy(tar_path, d / tar_path.name)


def tamper(src, dst):
    """The same archive with one byte changed in its largest blob."""
    with tempfile.TemporaryDirectory() as t:
        with tarfile.open(src) as tf:
            tf.extractall(t)
        blobs = sorted((Path(t) / "blobs" / "sha256").iterdir(), key=lambda p: p.stat().st_size)
        b = bytearray(blobs[-1].read_bytes())
        b[len(b) // 2] ^= 0xFF
        blobs[-1].write_bytes(bytes(b))
        with tarfile.open(dst, "w") as tf:
            for p in sorted(Path(t).rglob("*")):
                tf.add(p, arcname=str(p.relative_to(t)), recursive=False)


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    conf = tmp / "registries.conf"
    conf.write_text('[[registry]]\nlocation = "localhost:5000"\ninsecure = true\n')
    subprocess.run(["docker", "rm", "-f", "e2e-registry"], capture_output=True)
    subprocess.run(["docker", "run", "-d", "--rm", "-p", "5000:5000", "--name", "e2e-registry",
                    REGISTRY_IMAGE], check=True, capture_output=True)
    try:
        for _ in range(60):
            if subprocess.run(["curl", "-sf", "http://localhost:5000/v2/"],
                              capture_output=True).returncode == 0:
                break
            time.sleep(1)
        else:
            sys.exit("FAIL: the test registry never came up")

        fixture = tmp / "fixture"
        fixture.mkdir()
        (fixture / "Dockerfile").write_text("FROM scratch\nCOPY hello.txt /hello.txt\n")
        (fixture / "hello.txt").write_text("scanned, then pushed\n")

        amd = build_leg(fixture, tmp / "leg-amd64", "linux/amd64")
        arm = build_leg(fixture, tmp / "leg-arm64", "linux/arm64")
        scanned = {scanned_digest(amd): "linux/amd64", scanned_digest(arm): "linux/arm64"}
        check("each leg wrote its archive and unpacked the copy it scans",
              amd.exists() and arm.exists()
              and (tmp / "leg-amd64" / "layouts" / "linux-amd64" / "index.json").exists())

        # --- two platforms, two registries ------------------------------------
        pub = tmp / "pub"
        hand_on(pub, {"amd64": amd, "arm64": arm})
        base = {"RUNNER_TEMP": str(pub), "CONTAINERS_REGISTRIES_CONF": str(conf),
                "GITHUB_STEP_SUMMARY": str(tmp / "summary.md"), "GITHUB_SHA": SHA,
                "GITHUB_REPOSITORY_OWNER": "datumlabsio", "IMAGE": "selftest"}
        j = bash(JOIN, {**base, "PLATFORMS": "linux/amd64,linux/arm64"})
        check("Join accepts both scanned platforms", j.returncode == 0, j.stdout + j.stderr)
        p = bash(PUSH, {**base, "REGISTRY": "localhost:5000/primary",
                        "ALSO_REGISTRY": "localhost:5000/also",
                        "VERSION": "v0.0.0-selftest", "LATEST": "true"})
        check("Push publishes to both registries", p.returncode == 0, p.stdout + p.stderr)

        for ref in ("localhost:5000/primary/selftest:" + SHA,
                    "localhost:5000/primary/selftest:v0.0.0-selftest",
                    "localhost:5000/primary/selftest:latest",
                    "localhost:5000/also/selftest:" + SHA,
                    "localhost:5000/also/selftest:v0.0.0-selftest"):
            body = raw(ref, str(conf))
            if body is None:
                check(f"{ref} exists", False, "the registry does not hold it")
                continue
            idx = json.loads(body)
            held = {m["digest"]: f"{m['platform']['os']}/{m['platform']['architecture']}"
                    for m in idx.get("manifests", [])}
            check(f"{ref} is exactly the two scanned manifests", held == scanned,
                  f"registry holds {held}, build-scan scanned {scanned}")
        check("the second registry never gets `latest`",
              raw("localhost:5000/also/selftest:latest", str(conf)) is None)
        for digest in scanned:
            body = raw(f"localhost:5000/primary/selftest@{digest}", str(conf))
            check(f"the registry's {scanned[digest]} manifest hashes to the scanned digest",
                  body is not None and "sha256:" + hashlib.sha256(body).hexdigest() == digest)

        # --- one platform: a plain manifest, as before ------------------------
        single = tmp / "pub-single"
        hand_on(single, {"amd64": amd})
        s_env = {**base, "RUNNER_TEMP": str(single), "PLATFORMS": ""}
        j = bash(JOIN, s_env)
        p = bash(PUSH, {**s_env, "REGISTRY": "localhost:5000/single", "ALSO_REGISTRY": "",
                        "VERSION": "", "LATEST": "false"})
        body = raw(f"localhost:5000/single/selftest:{SHA}", str(conf))
        man = json.loads(body) if body else {}
        check("one platform is pushed as the scanned manifest itself, not an index",
              j.returncode == 0 and p.returncode == 0 and "layers" in man
              and "sha256:" + hashlib.sha256(body).hexdigest() == scanned_digest(amd),
              p.stdout + p.stderr)
        check("...with only the SHA tag when there is no version and no latest",
              raw("localhost:5000/single/selftest:latest", str(conf)) is None)

        # --- refused: a changed byte, and a missing platform ------------------
        bad = tmp / "arm-tampered" / "linux-arm64.tar"
        bad.parent.mkdir()
        tamper(arm, bad)
        tam = tmp / "pub-tampered"
        hand_on(tam, {"amd64": amd, "arm64": bad})
        j = bash(JOIN, {**base, "RUNNER_TEMP": str(tam), "PLATFORMS": "linux/amd64,linux/arm64"})
        check("one changed byte in a scanned layer stops publish before it pushes",
              j.returncode != 0 and "::error::" in j.stdout, j.stdout + j.stderr)

        miss = tmp / "pub-missing"
        hand_on(miss, {"amd64": amd})
        j = bash(JOIN, {**base, "RUNNER_TEMP": str(miss), "PLATFORMS": "linux/amd64,linux/arm64"})
        check("a platform whose archive never arrived stops publish",
              j.returncode != 0 and "Asked for" in j.stdout, j.stdout + j.stderr)
    finally:
        subprocess.run(["docker", "rm", "-f", "e2e-registry"], capture_output=True)

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)}: {', '.join(FAILURES)}")
    sys.exit(1)
print("\nOK: publish pushes the scanned bytes to every registry, and refuses anything else")
