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

The VM: 8 GB RAM, 4–8 vCPU, 100 GB. That fits two or three concurrent lint/test jobs at parity with GitHub's runner (2 vCPU / 7 GB each).

**1. A runner group scoped to private repositories.** In organisation settings → Actions → Runner groups. Create `datum-private`, set repository access to **selected repositories**, and add only private ones. This is the control that enforces rule one — not a convention, a setting.

**2. Install the runner.**

`curl` is a prerequisite, and a clean Ubuntu 24.04 image does not have it — `run-ephemeral.sh` needs it to exchange the App token for a registration token. Install it first, or the service fails at its first run with everything else looking correct.

```bash
sudo apt-get update && sudo apt-get install -y curl
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
sudo systemctl enable --now actions-runner.service
sudo systemctl enable --now reclaim-disk.timer
```

**5. Point one workflow at it.** Start with `polaris` lint and test only:

```yaml
runs-on: [self-hosted, linux, datum]
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

## What is deliberately not here

**Autoscaling.** One VM, a fixed number of runners. When jobs queue, they queue — that is visible and fine. Autoscaling is a second system to operate and nothing needs it yet.

**Caching between jobs.** Ephemeral runners start cold every time. That is the cost of rule two and it is not negotiable for a speed gain.

**Container builds.** See above.

## If it is on fire

```bash
sudo systemctl stop actions-runner.service     # jobs queue on GitHub, nothing is lost
```

Removing the runner group's repository access has the same effect and is faster from a phone.
