#!/usr/bin/env python3
"""publish pushes exactly what build-scan scanned -- the merge that joins the
per-platform builds into one image must not change a single byte of them.

    python3 tests/merge_oci_unit.py

The script under test is the copy that SHIPS: the heredoc inside
container-ci.yml's publish job, cut out of the workflow file on every run. A
called workflow cannot read files from this repository, so the script lives in
the YAML -- and a test of a copy kept anywhere else would test something that
never runs. MERGE_OCI_SCRIPT overrides it, for working on a draft.

Every case builds SYNTHETIC OCI archives -- fake layer bytes, a real config,
manifest and index, tarred the way `buildx --output type=oci` writes them --
and runs the real script on them. Manifests are written with indent=2, so a
merge that parsed and re-serialised one would produce different bytes, and a
different digest, which the cases below would catch.

The script path comes from MERGE_OCI_SCRIPT, so the same cases can be pointed
at the copy that actually ships inside a workflow file.
"""

import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKFLOW = HERE.parent / ".github" / "workflows" / "container-ci.yml"


def shipped_script():
    """Cut the merge script out of publish's heredoc, exactly as bash will."""
    lines = WORKFLOW.read_text().split("\n")
    start = next(i for i, l in enumerate(lines) if "<<'PY'" in l and "merged.txt" in l)
    indent = len(lines[start]) - len(lines[start].lstrip())
    body = []
    for l in lines[start + 1:]:
        if l.strip() == "PY" and len(l) - len(l.lstrip()) == indent:
            break
        body.append(l[indent:] if l.strip() else "")
    else:
        sys.exit(f"FAIL: no PY terminator after line {start + 1} of {WORKFLOW}")
    out = Path(tempfile.mkdtemp()) / "merge_oci.py"
    out.write_text("\n".join(body) + "\n")
    return str(out)


SCRIPT = os.environ.get("MERGE_OCI_SCRIPT") or shipped_script()
FAILURES = []

MANIFEST = "application/vnd.oci.image.manifest.v1+json"
INDEX = "application/vnd.oci.image.index.v1+json"
CONFIG = "application/vnd.oci.image.config.v1+json"
LAYER = "application/vnd.oci.image.layer.v1.tar+gzip"
REF_NAME = "org.opencontainers.image.ref.name"


def check(name, ok, detail=""):
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' -- {detail}'}")
    if not ok:
        FAILURES.append(name)


def digest(b):
    return "sha256:" + hashlib.sha256(b).hexdigest()


def image(os_, arch, variant=None, layer=None, layer_size_delta=0, platform_in_desc=None):
    """Blobs and the manifest descriptor for one synthetic single-platform image."""
    layer = layer if layer is not None else f"layer-bytes-{os_}-{arch}-{variant}".encode() * 50
    config = {"architecture": arch, "os": os_, "rootfs": {"type": "layers", "diff_ids": [digest(layer)]}}
    if variant:
        config["variant"] = variant
    cfg = json.dumps(config, indent=2).encode()
    manifest = {
        "schemaVersion": 2, "mediaType": MANIFEST,
        "config": {"mediaType": CONFIG, "digest": digest(cfg), "size": len(cfg)},
        "layers": [{"mediaType": LAYER, "digest": digest(layer), "size": len(layer) + layer_size_delta}],
    }
    mb = json.dumps(manifest, indent=2).encode()
    desc = {"mediaType": MANIFEST, "digest": digest(mb), "size": len(mb),
            "annotations": {"org.opencontainers.image.created": "2026-11-11T00:00:00Z"}}
    if platform_in_desc is not None:
        desc["platform"] = platform_in_desc
    blobs = {digest(b): b for b in (layer, cfg, mb)}
    return {"desc": desc, "blobs": blobs, "manifest_bytes": mb, "layer": layer, "config_bytes": cfg}


def archive(path, descs, blobs, extra=None, drop=(), replace=None, wrap_in_index=False):
    """Tar an OCI layout. `replace` swaps a blob's bytes but keeps its file name."""
    blobs = dict(blobs)
    top = list(descs)
    if wrap_in_index:
        body = json.dumps({"schemaVersion": 2, "mediaType": INDEX, "manifests": top}).encode()
        blobs[digest(body)] = body
        top = [{"mediaType": INDEX, "digest": digest(body), "size": len(body)}]
    index = json.dumps({"schemaVersion": 2, "manifests": top}).encode()
    with tarfile.open(path, "w") as tar:
        def add(name, data):
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))
        add("oci-layout", b'{"imageLayoutVersion":"1.0.0"}')
        add("index.json", index)
        for d, b in blobs.items():
            if d in drop:
                continue
            if replace and d in replace:
                b = replace[d]
            add("blobs/sha256/" + d.split(":")[1], b)
        for kind, name, target in (extra or []):
            ti = tarfile.TarInfo(name)
            if kind == "file":
                ti.size = len(target)
                tar.addfile(ti, io.BytesIO(target))
            elif kind == "sym":
                ti.type, ti.linkname = tarfile.SYMTYPE, target
                tar.addfile(ti)
            elif kind == "hard":
                ti.type, ti.linkname = tarfile.LNKTYPE, target
                tar.addfile(ti)
    return path


def run(tmp, *archives):
    out = Path(tmp) / "out"
    p = subprocess.run([sys.executable, SCRIPT, str(out), *map(str, archives)],
                       capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr, out


def blob_ok(out, desc):
    """The blob exists in the output and hashes to its descriptor."""
    p = Path(out) / "blobs" / "sha256" / desc["digest"].split(":")[1]
    if not p.is_file():
        return False
    b = p.read_bytes()
    return digest(b) == desc["digest"] and len(b) == desc["size"]


def reachable_ok(out):
    """Walk the output from index.json; every blob present and hash-correct."""
    top = json.loads((Path(out) / "index.json").read_text())["manifests"]
    stack, n = list(top), 0
    while stack:
        d = stack.pop()
        if not blob_ok(out, d):
            return False, d["digest"]
        n += 1
        if d["mediaType"] not in (INDEX, MANIFEST):
            continue  # a config or a layer: verified above, nothing to walk into
        body = json.loads((Path(out) / "blobs" / "sha256" / d["digest"].split(":")[1]).read_bytes())
        if d["mediaType"] == INDEX:
            stack += body["manifests"]
        else:
            stack += [body["config"]] + body["layers"]
    return True, n


def fails(name, code, out, *words):
    check(name, code == 1 and "::error::" in out and all(w in out for w in words),
          f"exit {code}, wanted 1 with ::error:: and {words}: {out[-300:]!r}")


with tempfile.TemporaryDirectory() as T:
    T = Path(T)

    # --- two platforms: an index listing both, original digests, every blob --
    amd, arm = image("linux", "amd64"), image("linux", "arm64")
    a1 = archive(T / "amd.tar", [amd["desc"]], amd["blobs"])
    a2 = archive(T / "arm.tar", [arm["desc"]], arm["blobs"])
    with tempfile.TemporaryDirectory() as t:
        code, out, o = run(t, a2, a1)          # arm64 given first, on purpose
        check("two platforms: merges", code == 0, out)
        top = json.loads((o / "index.json").read_text())["manifests"]
        check("two platforms: index.json names one index, ref.name=push",
              len(top) == 1 and top[0]["mediaType"] == INDEX
              and top[0]["annotations"].get(REF_NAME) == "push", top)
        idx = json.loads((o / "blobs" / "sha256" / top[0]["digest"].split(":")[1]).read_bytes())
        got = [(m["platform"]["architecture"], m["digest"]) for m in idx["manifests"]]
        check("two platforms: the ORIGINAL manifest digests, sorted amd64 then arm64",
              got == [("amd64", amd["desc"]["digest"]), ("arm64", arm["desc"]["digest"])], got)
        check("two platforms: manifests carry their platform os",
              all(m["platform"]["os"] == "linux" for m in idx["manifests"]), idx["manifests"])
        ok, n = reachable_ok(o)
        check("two platforms: every reachable blob present and hash-correct (7 = index + 2x3)",
              ok and n == 7, f"{ok} {n}")
        man_bytes = (o / "blobs" / "sha256" / amd["desc"]["digest"].split(":")[1]).read_bytes()
        check("two platforms: manifest bytes are byte-for-byte the originals",
              man_bytes == amd["manifest_bytes"], "re-serialised")
        lines = out.strip().splitlines()
        check("two platforms: stdout names each platform, then the index",
              lines == [f"linux/amd64 {amd['desc']['digest']}", f"linux/arm64 {arm['desc']['digest']}",
                        f"index {top[0]['digest']}"], lines)
        check("two platforms: oci-layout written",
              json.loads((o / "oci-layout").read_text()) == {"imageLayoutVersion": "1.0.0"})

    # --- one platform: the manifest itself, no index ---------------------------
    with tempfile.TemporaryDirectory() as t:
        code, out, o = run(t, a1)
        top = json.loads((o / "index.json").read_text())["manifests"] if code == 0 else []
        check("one platform: a plain manifest at ref.name=push",
              code == 0 and len(top) == 1 and top[0]["mediaType"] == MANIFEST
              and top[0]["digest"] == amd["desc"]["digest"]
              and top[0]["annotations"].get(REF_NAME) == "push"
              and top[0]["platform"] == {"os": "linux", "architecture": "amd64"}, f"{code} {top} {out}")
        nblobs = len(list((o / "blobs" / "sha256").iterdir())) if code == 0 else -1
        check("one platform: no index blob written (manifest, config, layer only)", nblobs == 3, nblobs)
        check("one platform: original annotations kept", code == 0 and
              top[0]["annotations"].get("org.opencontainers.image.created") == "2026-11-11T00:00:00Z", top)
        check("one platform: stdout ends with the manifest",
              out.strip().splitlines()[-1:] == [f"manifest {amd['desc']['digest']}"], out)

    # --- buildx's shape: one platform wrapped in an index ----------------------
    with tempfile.TemporaryDirectory() as t:
        w = archive(T / "wrapped.tar", [amd["desc"]], amd["blobs"], wrap_in_index=True)
        code, out, o = run(t, w)
        top = json.loads((o / "index.json").read_text())["manifests"] if code == 0 else []
        check("wrapped in an index: unwrapped to the plain manifest",
              code == 0 and len(top) == 1 and top[0]["digest"] == amd["desc"]["digest"], f"{code} {out}")

    # --- arm64 written with and without /v8 is one platform, not a conflict -----
    with tempfile.TemporaryDirectory() as t:
        v8 = image("linux", "arm64", variant="v8", platform_in_desc={"os": "linux", "architecture": "arm64"})
        code, out, o = run(t, archive(T / "v8.tar", [v8["desc"]], v8["blobs"]))
        check("arm64 vs arm64/v8 in descriptor and config: accepted", code == 0, out)

    # --- failures ---------------------------------------------------------------
    def fail_case(name, words, *archives):
        with tempfile.TemporaryDirectory() as t:
            code, out, o = run(t, *archives)
            fails(name, code, out, *words)
            return o

    fail_case("the same platform twice: refused", ("twice",), a1, archive(T / "amd2.tar", [amd["desc"]], amd["blobs"]))

    bad = bytearray(amd["layer"])
    bad[10] ^= 0xFF
    fail_case("a layer whose bytes changed (same length, digest kept): refused", ("does not hash",),
              archive(T / "corrupt.tar", [amd["desc"]], amd["blobs"], replace={digest(amd["layer"]): bytes(bad)}))

    big = image("linux", "amd64", layer_size_delta=1)
    fail_case("a layer whose size disagrees with its descriptor: refused", ("bytes; its descriptor says",),
              archive(T / "size.tar", [big["desc"]], big["blobs"]))

    fail_case("a blob missing from the archive: refused", ("missing",),
              archive(T / "missing.tar", [amd["desc"]], amd["blobs"], drop={digest(amd["layer"])}))

    sentinel = T / "escaped-by-dotdot"
    fail_case("a member with '..': refused", ("'..'",),
              archive(T / "dotdot.tar", [amd["desc"]], amd["blobs"],
                      extra=[("file", "blobs/../../../escaped-by-dotdot", b"x")]))
    check("...and nothing was written outside", not sentinel.exists(), str(sentinel))

    fail_case("an absolute member path: refused", ("absolute",),
              archive(T / "abs.tar", [amd["desc"]], amd["blobs"], extra=[("file", "/tmp/oci-abs-escape", b"x")]))

    fail_case("a symlink member: refused", ("link",),
              archive(T / "sym.tar", [amd["desc"]], amd["blobs"], extra=[("sym", "blobs/sha256/evil", "/etc/passwd")]))

    fail_case("a hardlink member: refused", ("link",),
              archive(T / "hard.tar", [amd["desc"]], amd["blobs"], extra=[("hard", "blobs/sha256/evil", "index.json")]))

    att_body = json.dumps({"schemaVersion": 2, "mediaType": MANIFEST,
                           "config": {"mediaType": CONFIG, "digest": digest(amd["config_bytes"]),
                                      "size": len(amd["config_bytes"])},
                           "layers": []}, indent=2).encode()
    att_desc = {"mediaType": MANIFEST, "digest": digest(att_body), "size": len(att_body),
                "platform": {"os": "unknown", "architecture": "unknown"},
                "annotations": {"vnd.docker.reference.type": "attestation-manifest",
                                "vnd.docker.reference.digest": amd["desc"]["digest"]}}
    fail_case("an attestation manifest: refused, and says to build without one", ("--provenance=false",),
              archive(T / "att.tar", [amd["desc"], att_desc], dict(amd["blobs"], **{digest(att_body): att_body}),
                      wrap_in_index=True))

    liar = image("linux", "amd64", platform_in_desc={"os": "linux", "architecture": "arm64"})
    fail_case("a descriptor whose platform contradicts its config: refused", ("its config says",),
              archive(T / "liar.tar", [liar["desc"]], liar["blobs"]))

    with tempfile.TemporaryDirectory() as t:
        (Path(t) / "out").mkdir()
        (Path(t) / "out" / "stale").write_text("x")
        p = subprocess.run([sys.executable, SCRIPT, str(Path(t) / "out"), str(a1)], capture_output=True, text=True)
        fails("a non-empty OUT_DIR: refused", p.returncode, p.stdout + p.stderr, "not empty")

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)}: {', '.join(FAILURES)}")
    sys.exit(1)
print("\nOK: the merge pushes the scanned bytes, every platform once, and refuses anything else")
