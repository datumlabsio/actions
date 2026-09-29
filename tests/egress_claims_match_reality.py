#!/usr/bin/env python3
"""The runbook must not promise a control that is not deployed.

For months this document described the runner's egress as an allowlist at the
switch — "reach nothing else" — when what existed was a denylist on the guest.
Anyone reading it would have concluded the blast radius was bounded by the
network. It is bounded by a ruleset that root on the guest can flush.

(The first version of this file said nothing was filtering at all. That was
not verified and was probably wrong — B-82 records host rules applied and
matching the day before. Asserting an absence without looking is the same
mistake this file exists to catch, so it is corrected rather than quietly
reworded.)

What is deployed is weaker and worth being exact about: an nftables output
chain on the guest that blocks private networks and permits the internet. It
stops a malicious `postinstall` reaching the applications host. It does not
stop exfiltration, and root on the guest defeats it.

A security document that overstates its controls is worse than one that says
nothing, because it stops people asking. So the overstatement is asserted
against here.

Run: python3 tests/egress_claims_match_reality.py
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = (ROOT / "docs" / "self-hosted-runners.md").read_text()
# The ruleset lives in runners/ rather than in the document, because a public
# repository must not carry this site's addressing -- the no_literal_env_values
# gate caught exactly that here, in prose, which is the half it exists for.
_NFT_RAW = (ROOT / "runners" / "datum-egress.nft").read_text()

# Strip the comments before asserting. That file explains every lockout rule in
# a comment directly above it, so deleting the RULE leaves the WORDS, and a
# substring check passes on the explanation. runner_setup.py has carried a
# code_only() for this since --ephemeral escaped the same way; two mutations
# escaped here before this line existed.
NFT = "\n".join(l for l in _NFT_RAW.splitlines()
                 if not l.lstrip().startswith("#"))

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


egress = DOC.split("## Network egress")[1].split("\n## ")[0]

# Assert on the RULESET FILE, not on the paragraph that explains it. Deleting a
# rule leaves its explanation behind, and a substring check then passes on the
# prose -- the same trap runner_setup.py's code_only() exists for. Four of
# these escaped a first pass for exactly that reason.
blocks = re.findall(r"```(?:bash)?\n(.*?)```", egress, re.S)
ruleset = NFT
evidence = next((b for b in blocks if "timeout" in b and "200" in b), "")
not_this = egress.split("### What this is not")[-1].split("### Stage 2")[0]

# --- the deployed thing is described as what it is -------------------------
check("It is a denylist" in not_this,
      "the runbook no longer admits the deployed filter is a denylist — that "
      "admission is the difference between a reader checking stage 2 and "
      "assuming it is done")
check(re.search(r"stage 2.*outstanding", egress, re.I) is not None,
      "stage 2 is no longer marked outstanding, so it reads as delivered")
check(re.search(r"root on\s+the\s+(box|guest)", not_this) is not None,
      "the stage-1 section no longer says host-level filtering is defeated by "
      "root — the stage-2 paragraph saying it is not the same claim")

# --- the three rules that are a lockout if dropped -------------------------
check("chain output" in ruleset,
      "runners/datum-egress.nft no longer defines an output chain")
check("@private drop" in ruleset,
      "the ruleset no longer drops anything -- it accepts and logs, which "
      "reads as a control and is not one")
check(DOC.count("datum-egress.nft") >= 2,
      "the runbook no longer points at the ruleset, so the two will drift")
for rule, why in [
    ("established,related",
     "without it, dropping LAN egress kills the SSH session applying the rule"),
    ("67, 68", "without DHCP the VM loses its address and nobody can reach it"),
    ("169.254.0.0/16", "the cloud metadata endpoint stays reachable"),
]:
    check(rule in ruleset, f"the ruleset lost {rule!r}: {why}")

# --- and the failure mode that is silent -----------------------------------
check("silent" in egress.lower(),
      "the runbook does not warn that a bad /etc/nftables.conf fails at boot "
      "without a word, quietly reopening egress")

# --- the numbers are from the box, not from hope ---------------------------
# Aspiration reads exactly like evidence once it is in a code block, which is
# how this section came to promise an allowlist nobody had built. So: no
# hedging words, and more than one destination actually observed blocked.
blocked = len(re.findall(r"timeout|blocked|refused", evidence))
check(blocked >= 2 and "200" in evidence,
      f"only {blocked} destination(s) shown blocked — the evidence must show "
      f"the LAN dead AND the internet alive, or it proves nothing")
check(not re.search(r"\bshould\b|\bexpect\b|\bmust\b", evidence),
      "the verification block hedges — 'should block' is not 'does block', "
      "and this section has made exactly that substitution before")

if failures:
    print("\n".join(f"FAIL  {f}" for f in failures))
    sys.exit(1)
print("PASS  the egress section describes what is deployed, not what is wanted")
