# Self-hosted runners

We run some CI on our own hardware. This is how, and — more importantly — what must never change about it.

**Why:** not cost. At six active repositories the overage is a couple of dollars a month. It is that the bill scales with the thing we are building — every repository adopted adds jobs, and `dl-assessment-platform` alone runs 15 billed minutes per pull request. Free runners also remove the quiet disincentive to add a gate.

## The three rules

**Never a public repository.** Several of ours are, this one included. Anyone with a GitHub account can open a pull request on a public repository, and on a self-hosted runner that pull request's code executes on our network. Public minutes are also **already free**, so the security constraint and the economics agree — there is no reason to want this.

**Ephemeral, always.** One job per runner registration, then exit and re-register. A reused runner is a machine where the next job can read the previous job's checkout, tokens and `/tmp`. Persistent runners are faster because caches survive; that is the same reason they are unsafe.

**No `pull_request_target`.** Enforced by `workflows-ci` — see the check there. On a self-hosted runner it means a stranger's code with a writable token, on our network.

## What runs here, and what does not

| | |
|---|---|
| **Yes** | lint, typecheck, unit tests, dbt, scheduled internal jobs |
| **No** | container builds — image layers and Trivy's database fill a 100 GB disk in days |
| **Never** | anything triggered by a public repository |

Container jobs stay on GitHub-hosted until there is a runner with disk sized for them. That is a capacity decision, not a security one.

## Standing one up

The VM: 16 vCPU, 32 GB, 100 GB. Ten concurrent lint/test jobs peaked at load 9
of 16 and **6.5 GB of 32** — so this is generous on both, deliberately, because
the first guess (8 vCPU, 17 GB) hit load 16.1 with the same workload and every
job slowed three- to four-fold.

**Do not size this against CPU.** Bandwidth is the binding constraint and the
numbers are at the bottom of this file. More cores past this point buy nothing.

**1. A runner group scoped to private repositories.** In organisation settings → Actions → Runner groups. Create `datum-private`, set repository access to **selected repositories**, and add only private ones. This is the control that enforces rule one — not a convention, a setting.

**2. Install the runner.**

A clean Ubuntu 24.04 image has almost none of what these workflows assume. They
were written against GitHub's runner image, which preinstalls a very large
amount, and **every absence fails somewhere other than the install**:

| missing | how it actually presents |
|---|---|
| `curl` | the service fails on its first run, everything else looking correct |
| `git` | `actions/checkout` silently falls back to a tarball download and goes **green** — then `gitleaks` finds no history, scans the whole working tree, and fails three steps later naming none of this |
| `pipx` | `pipx: command not found`, exit 127, in whichever gate installs a tool |
| `libpq-dev`, `python3-dev` | `Failed to build psycopg2-…` inside a dependency resolve |

`git` is the one worth reading twice. A missing binary produced a passing
checkout and a failure elsewhere — the same shape as the `curl` problem that
cost three weeks, and the reason step 6 below exists.

```bash
sudo apt-get update && sudo apt-get install -y \
  curl git pipx python3-pip python3-venv build-essential \
  libpq-dev python3-dev pkg-config
sudo useradd -m -d /opt/actions-runner runner
cd /opt/actions-runner
curl -sSL -o runner.tar.gz \
  https://github.com/actions/runner/releases/download/v2.337.0/actions-runner-linux-x64-2.337.0.tar.gz
tar xzf runner.tar.gz && rm runner.tar.gz
sudo ./bin/installdependencies.sh
```

**3. Credentials**, in `/etc/actions-runner.env`, mode `0600`, owned by root:

```
RUNNER_ORG=datumlabsio
RUNNER_GROUP=datum-private
RUNNER_LABELS=self-hosted,linux,x64,datum
RUNNER_DIR=/opt/actions-runner
APP_ID=<the datum-runner App's id>
APP_PRIVATE_KEY_PATH=/etc/datum-runner.pem
```

The key itself goes at `/etc/datum-runner.pem`, **`0640`, owned `root:runner`**:

```bash
sudo chown root:runner /etc/datum-runner.pem && sudo chmod 640 /etc/datum-runner.pem
```

Not `0600 root:root`, which is the obvious choice and is wrong here. `actions-runner.service` runs as `User=runner` and `app-token.py` opens that path itself, so a root-only key means the service cannot read its own credential. Root owns it, the service group reads it, nobody else can.

Prove it **as the service user**. Run as root and it passes on a key the runner cannot open:

```bash
sudo -u runner env APP_ID=<id> APP_PRIVATE_KEY_PATH=/etc/datum-runner.pem \
  RUNNER_ORG=datumlabsio python3 /opt/actions-runner/app-token.py >/dev/null && echo ok
```

**Use the App, not a personal access token.** A PAT on disk *is* the credential — read the file and use it — and it belongs to a **person**, so runners stop registering the day that person rotates or leaves. The App's key needs a signed JWT exchange first, the token it yields lasts an hour, and the App holds `organization_self_hosted_runners: write` and nothing else: it cannot read a repository, push, or see a secret.

If this machine is compromised, the worst that credential does is register and remove runners. That is a nuisance, not an incident.

`GH_TOKEN` still works as a fallback while the App is being created, and warns every run. Temporary credentials are the ones that stay.

**4. Copy in the scripts and units** from `runners/` in this repository, then:

```bash
sudo systemctl enable --now reclaim-disk.timer
```

**5. Ten runners, not one.** One runner is a queue of one: fourteen jobs that
want five minutes of wall clock took **twenty-eight**, almost all of it
waiting. Each instance needs its **own directory** — `config.sh` writes a
single registration and `_work` into it, so they cannot share one.

```bash
sudo bash -s <<'SETUP'
set -euo pipefail
N=10; SRC=/opt/actions-runner
for i in $(seq 1 $N); do
  D=/opt/actions-runner-$i
  [ -d "$D" ] || { mkdir -p "$D"
    tar -C "$SRC" --exclude=_work --exclude=_diag --exclude=.runner \
        --exclude=.credentials --exclude=.credentials_rsaparams -cf - . | tar -C "$D" -xf -
    mkdir -p "$D/_work"; }
  chown -R runner:runner "$D"
done
mkdir -p /opt/hostedtoolcache && chown runner:runner /opt/hostedtoolcache
systemctl daemon-reload
systemctl enable --now $(seq -f 'actions-runner@%g' 1 $N)
SETUP
```

The template unit is `runners/actions-runner@.service`. Four things in its
`ExecStart` are not optional, and each was found the hard way:

```
ExecStart=/usr/bin/env HOME=/opt/actions-runner-%i RUNNER_DIR=/opt/actions-runner-%i \
  RUNNER_TOOL_CACHE=/opt/hostedtoolcache PIP_BREAK_SYSTEM_PACKAGES=1 \
  PATH=/opt/actions-runner-%i/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  /opt/actions-runner-%i/run-ephemeral.sh
```

- **`/usr/bin/env`, not `Environment=`.** `EnvironmentFile=` wins over
  `Environment=` regardless of the order they appear in the unit. Setting
  `RUNNER_DIR` the systemd way silently loses to `/etc/actions-runner.env`,
  every instance then configures in the *original* directory, which
  `ReadWritePaths` correctly makes read-only, and all ten crash-loop every five
  seconds.
- **`HOME` per instance.** The `runner` user's home is `/opt/actions-runner`.
  Leave it and ten instances share one `~/.cache/uv` and one `~/.local`: you get
  `error: Could not acquire lock` on every Python job and
  `Read-only file system: .../.local/state/pipx` on every pipx one.
- **`PATH` including `$HOME/.local/bin`.** pipx installs there. Without it,
  `pipx install semgrep` succeeds and then `semgrep: command not found`.
- **`PIP_BREAK_SYSTEM_PACKAGES=1`.** Ubuntu 24.04 is PEP 668 managed, so a bare
  `python3 -m pip install` — which `gitops-ci` does for PyYAML — fails with
  `externally-managed-environment`. GitHub's image permits it; this restores
  parity.

Also set `StartLimitIntervalSec=300` / `StartLimitBurst=20` in `[Unit]`, so a
persistent failure stops instead of hammering GitHub's registration endpoint
every five seconds. Ours did that unnoticed for ninety seconds, twice.

**Two traps in the ephemeral loop itself**, both invisible until a runner is
killed mid-job:

- A runner that does not exit cleanly leaves `.runner` behind, and `config.sh`
  then refuses with *"Cannot configure the runner because it is already
  configured"* — **forever**. `--replace` handles the server side; nothing
  handles the local side. `run-ephemeral.sh` deletes `.runner` and
  `.credentials*` before configuring.
- Because it deletes `.credentials`, the runner can no longer deregister
  itself, so a **PID-based name orphans a registration every job**. Ours reached
  39 dead entries in an afternoon. Name each instance stably —
  `$(hostname)-${RUNNER_DIR##*-}` — and `--replace` reuses the same slot.

**6. Prove the toolchain is there before trusting a green run.**

```bash
for b in git curl pipx python3 pip3 gcc make; do
  command -v $b >/dev/null || echo "MISSING: $b"
done
```

**7. Point one workflow at it.** Start with `polaris` lint and test only:

```yaml
jobs:
  ci:
    uses: datumlabsio/actions/.github/workflows/python-ci.yml@v1.10.0
    with:
      runner-label: datum
```

Watch it for a week before widening. A runner that works for one repository is evidence; a migration is not.

## Disk

`reclaim-disk.sh` runs hourly and escalates: prune containers and build cache always, unused images past 75%, everything past 85%.

Past 85% after a full prune it exits non-zero — **and that is quieter than it sounds.** The script emits `::error::`, which is a GitHub Actions workflow command and means nothing to systemd; here it is a literal string in the journal. The unit enters `failed`, and `systemctl --failed` is not somewhere anyone looks.

So the honest description today: it records the problem where a person could find it, if they already knew to look. **Nothing notifies.** Until that is wired to the Slack path, this is the first thing to check when jobs start failing for unrelated-looking reasons.

This is the most common way a self-hosted runner dies. It is a timer from day one, not a thing to add after the first outage.

## Network egress — the control that decides the blast radius

**This is not in any script, and everything above assumes it exists.**

CI runs `pnpm install` and `pip install`, and those execute `postinstall` scripts and `setup.py` by design. That is arbitrary code execution on every job, inherent to CI, and no runner configuration removes it. On GitHub-hosted runners it happens on a disposable machine on somebody else's network. Here it happens on our hardware, inside our perimeter.

**So the firewall is what decides whether a compromised dependency is an annoyance or an incident.** The runner's VLAN should permit outbound 443 to:

```
github.com, api.github.com, codeload.github.com, *.actions.githubusercontent.com
ghcr.io, registry.npmjs.org, pypi.org, files.pythonhosted.org
the OS package mirrors
```

and reach **nothing else** — specifically no route to the applications host, no Tailscale, no internal DNS, no other VM on the hypervisor. No inbound ports at all: runners poll outward, so nothing needs to reach them.

An allowlist, not a denylist. A denylist protects against the destinations somebody thought of.

## Getting a repo onto it, and off it again

Two controls, and they are deliberately not the same control.

**Per repo: the `runner-label` input.** A caller opts in by passing it:

```yaml
jobs:
  ci:
    uses: datumlabsio/actions/.github/workflows/python-ci.yml@v0.6.0
    with:
      runner-label: datum
```

It defaults to `ubuntu-latest`, and the default is the whole point. A label
that no runner answers does not fail a job — GitHub queues it, silently, for
twenty-four hours before cancelling it. So opting in has to be an act, taken
in a repo the runner group actually grants, not something a version bump does
to thirty repos at once.

`dbt-ci` and `container-ci` do not take the input at all. Both hand a job a
warehouse or registry credential, and a stage-1 VM on the office LAN is not
where those go. Neither does the `violation` job in `security-baseline`, for
the same reason — it holds the App key that files the issue.

**Org-wide: the `DATUM_RUNNER_OFFLINE` variable.** While it is `"true"`, every
opted-in job goes back to `ubuntu-latest`, whatever the input says:

```yaml
runs-on: ${{ vars.DATUM_RUNNER_OFFLINE == 'true' && 'ubuntu-latest' || inputs.runner-label }}
```

An organisation variable, not a secret: a workflow reads it with no
credential, no extra job, and no token minted anywhere. Absent means the
runner is up, so a repo outside the org — an external adopter, who has no such
variable — is unaffected.

`.github/workflows/runner-watch.yml` in `datumlabsio/.github` is what sets it,
on a schedule, and puts a message in Slack when it flips. Recovery needs no
action: the next run after the variable clears reads the new value. Two limits
worth knowing before you rely on it:

- **Detection lags.** Scheduled workflows on GitHub run late under load —
  ten to thirty minutes is normal. During the gap, jobs queue.
- **Queued jobs stay queued.** The variable is read when a run starts. A job
  already waiting on a dead runner is not rescued by the flip; cancel and
  re-run it.

To flip it by hand, without waiting for the watcher:

```bash
gh variable set DATUM_RUNNER_OFFLINE --org datumlabsio --body true --visibility all
```

## What is deliberately not here

**Autoscaling.** One VM, ten runners. Autoscaling is a second system to operate and nothing needs it yet — and with bandwidth as the constraint, more runners would make things worse, not better.

**Caching between jobs.** Ephemeral runners start cold every time. That is the cost of rule two and it is not negotiable for a speed gain.

The shared tool cache at `/opt/hostedtoolcache` is not an exception to that, as
long as it is **root-owned and read-only to jobs**. A writable shared cache
would let one job plant a binary the next job executes, which is precisely what
rule two exists to prevent. Populate it under a commit you control, then lock
it.

**Container builds.** See above.

## Why it takes sixteen minutes, and what would fix it

Measured on `polaris`, fourteen jobs, ten runners, 16 vCPU / 32 GB:

| | |
|---|---|
| wall clock | **16 minutes** |
| queue time per job | 2–32 s — parallelism is not the problem |
| peak load | 9.15 of 16 — **CPU is not the problem** |
| peak memory | 6.5 GB of 32 — memory is not the problem |

The same jobs run alone on this box take 98–311 s. Run ten at a time they take
478–948 s, while the CPU sits half idle. What they are waiting on is the office
uplink:

```
1 stream    2.27 MB/s
6 streams   3.59 MB/s aggregate
```

**About 29 Mbit/s total, and parallelism buys almost nothing** — six streams got
1.6× one stream. Ten jobs each resolving dependencies share that, so a project
pulling 300 MB of wheels takes a quarter of an hour. GitHub-hosted runners sit
in the same datacentre as PyPI and npm with gigabit to both. That is a 30× gap
and no amount of VM tuning closes it.

So: **do not buy more cores, and do not add more runners.** The only thing that
moves this number is not fetching the same public bytes over the WAN ten times
— a read-through package cache on the LAN (devpi for PyPI, Verdaccio for npm),
or a faster uplink. A package proxy caches public immutable artefacts, not job
state, so it does not cost rule two.

Worth stating plainly, because it changes the decision: moving `polaris`
off GitHub-hosted saves about **$8 a month**. At sixteen minutes versus six,
the case for self-hosting is the Actions budget cap and where the code runs —
not speed, and not really cost either.

## If it is on fire

```bash
sudo systemctl stop actions-runner.service                                    # on the VM
gh variable set DATUM_RUNNER_OFFLINE --org datumlabsio --body true --visibility all
```

Stopping the service alone leaves jobs queueing until the watcher notices.
The second command is the one that keeps merges moving, and it is the only one
you can run from a phone.
