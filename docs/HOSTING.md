# Hosting it for free, for a long time

The frontend is easy - it is a static page. The backend is the hard part: it
**compiles C code**, so it needs a real machine with a disk, not a serverless
function.

## The one that needs no card at all: GitHub Actions + Cloudflare Pages Functions

Oracle refused the signup cards, and every other VM free tier asks for one. The
stack that needs **no card and no machine** is already half in this repository:

1. **GitHub Actions** does the compiling. Free for public repositories, no card,
   no quota that bills. [configurator.yml](../.github/workflows/configurator.yml)
   builds a selection, verifies the vector table and publishes it as a release
   under a deterministic tag, skipping the compile when that tag already exists.
2. **A Pages Function** is the trigger. It lives next to this site in
   [docs/functions/api/build.js](../docs/functions/api/build.js), holds a
   repository-scoped token as a Pages secret, and answers
   `POST /api/build` by dispatching the workflow. The same origin means no CORS,
   no tunnel and nothing of yours reachable.
3. **The page** prefers that function: it probes `/api/build/<tag>` on load and,
   when it answers, Build posts the selection and polls until the release exists.
   Anything already published downloads immediately.

### Five minutes, no card

1. Cloudflare dashboard -> *Workers & Pages* -> *Create* -> *Pages* -> connect the
   GitHub repository, publish directory `docs`.
2. Repository settings -> *Secrets and variables* -> *Actions* is not needed;
   instead, in the Pages project: *Settings -> Variables and secrets -> Add*,
   name `GH_TOKEN`, a fine-grained token with **Actions: read and write** and
   **Contents: read** on this repository only.
3. Deploy. The function is served with the site; the page switches to it by itself.

A new selection takes the length of one compile (about 3 minutes); a selection
that was built before downloads at once, because the function checks the release
tag before dispatching anything.

### When a real server is wanted anyway

The same server also runs anywhere with Docker: [deploy/](../deploy) has the
image, the compose file and a cloud-init script. Hosts that ask for a card -
Oracle Always Free (2 OCPU / 12 GB / 200 GB, verified in their docs), Google
Cloud `e2-micro`, AWS, Azure - all fit the footprint if the card goes through.
Hugging Face Docker Spaces no longer fit the price (their docs: Docker Spaces
require a paid plan).

## Where the backend can live: checked, not guessed

The backend compiles with PlatformIO, so it needs a container-sized host: about
**5 GB of disk and 1 GB of RAM**, on x86_64 **or arm64** (PlatformIO ships
both). Serverless platforms cannot run it at all.

| Host | Fits? | Cost | Verified detail |
|---|---|---|---|
| **Oracle Cloud Always Free**, `VM.Standard.A1.Flex` (Arm) | **yes** | free forever | Oracle's docs: Always Free tenancies get the equivalent of **2 OCPUs and 12 GB RAM**, plus **200 GB** of block storage; minimum boot volume 47 GB |
| Google Cloud free `e2-micro` | marginal | free | 1 GB RAM against a 462 MB build peak; one build at a time |
| Hugging Face Spaces (Docker) | no longer | - | Spaces docs: "creating a Space that runs on compute (Gradio or Docker) **requires a paid plan**"; Static Spaces are the free ones |
| Cloudflare Workers | not for the compiler | free plan | Workers cannot run PlatformIO; only useful as a small dispatcher for GitHub Actions |
| Render / Railway / Koyeb / Fly.io free tiers | no | - | 512 MB RAM, ephemeral disk, or trial credit |

### Oracle recipe (one paste)

[deploy/oracle/cloud-init.yaml](../deploy/oracle/cloud-init.yaml) is a cloud-init
script: on Ubuntu 24.04 it installs Docker, clones this repository and runs
[deploy/docker-compose.yml](../deploy/docker-compose.yml), which starts the
service in **public mode** on port 8080.

1. Create an **Always Free** `VM.Standard.A1.Flex` instance: 2 OCPUs, 12 GB, Ubuntu 24.04,
   47 GB boot volume, and paste the cloud-init script under
   *Show advanced options → Management*.
2. Open port 8080 in the subnet's security list (and `ufw`, which the script already does).
3. Wait for the image build (a few minutes), then browse to
   `http://<instance-ip>:8080` - that is the configurator, same API as locally.
4. Point the Pages build page at it: put the address into
   [docs/cloud/backend.json](../docs/cloud/backend.json) as `{"url": "http://<instance-ip>:8080"}`.

### Public mode

`--public` (or `CONFIGURATOR_PUBLIC=1`) is required on any reachable host:

- `/api/write`, `/api/devices` and `/api/versions/fetch` answer **403** - a visitor can build,
  not format a disk;
- builds are limited per address (`CONFIGURATOR_BUILDS_PER_HOUR`, default 6) and answer 429 beyond that;
- one build runs at a time in the existing queue.

Verified locally: catalog 200, devices 403, write 403, versions/fetch 403,
third build from one address 429.

### Do not publish a tunnel from a home machine

A quick tunnel (`trycloudflare.com`) does not reveal the home IP - the connection is
outbound - but it does publish a compiler and, without public mode, the card
writer to anyone with the URL. Use a host you can afford to expose instead.

## What the backend actually needs (measured on this machine)

| Resource | Measured |
|---|---|
| Warm build tree (`build/Ender3V2S1`) | **2.1 GB** |
| PlatformIO toolchains and frameworks (`~/.platformio`) | **1.4 GB** |
| One extra firmware checkpoint clone (tag or branch) | 53 MB (2022) to **635 MB** (2026 branch) |
| Peak RAM during a build | **462 MB** |
| Build time | ~5 s warm, ~25 s from a cold checkout |
| Services it must reach | github.com (git clone), registry.platformio.org (toolchains) |

So the floor is roughly **5 GB of disk and 1 GB of RAM** for one build at a time,
on a Linux x86_64 **or arm64** host - PlatformIO ships both `linux_x86_64` and
`linux_aarch64` toolchains (checked in the registry).

## The honest table

| Where | Free forever? | Fits this backend? | Catch |
|---|---|---|---|
| **Your own machine + Cloudflare Tunnel** | yes, you own it | yes | the machine must stay on; you are the sysadmin |
| **Oracle Cloud Always Free** (Ampere ARM: 4 OCPU / 24 GB / 200 GB) | yes, "always free" tier | yes | card for signup; idle instances can be reclaimed; region capacity is flaky |
| **Oracle Cloud Always Free** (AMD micro: 1 GB RAM) | yes | tight - 462 MB per build, 1 GB total | slow, one build at a time |
| **GitHub Actions as the builder** - *recommended* | yes for public repos | yes, but not as a server | no live log, 20-60 s queue; publish as a release so downloads need no account; a free Worker broker is included here |
| Google Cloud free `e2-micro` | yes | marginal (1 GB RAM, 30 GB disk) | card required; slow |
| Vercel / Netlify / Cloudflare Workers | yes | **no** | cannot run a compiler at all |
| Render / Railway / Koyeb / Fly.io free | no | no | sleep on idle, ephemeral disk, or trial credits |
| Hugging Face Spaces (CPU) | yes-ish | no | sleeps, ephemeral disk, terms not aimed at this |

"Free forever" means *until the provider changes its terms*. The only option
that cannot be taken away is hardware you already own.

## Three architectures that work

### A. Your box, one command (recommended)

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

Builds the image (python 3.12 slim + PlatformIO 6.1.19), bootstraps the pinned
tree into a named volume on first start, serves on `127.0.0.1:8787`, and
restarts itself.

Publish it without opening a port:

```bash
cloudflared tunnel create ender3s1
cloudflared tunnel route dns ender3s1 firmware.example.com
cloudflared tunnel --config deploy/cloudflared.yml run
```

Cloudflare Tunnel is free, terminates TLS, and the service stays bound to
loopback. Without Docker, `deploy/configurator.service` is the same thing as a
systemd user unit.

### B. Oracle Cloud Always Free (a VM you do not keep at home)

1. Create an **Always Free** Ampere A1 instance (4 OCPU, 24 GB, Ubuntu 24.04,
   200 GB block storage). ARM is fine - the ARM toolchain exists.
2. `apt install docker.io docker-compose-v2 git`, add your user to the docker group.
3. Clone this repository, then `docker compose -f deploy/docker-compose.yml up -d --build`.
4. Open only 443/80 in the security list and put Caddy or nginx in front - or run
   `cloudflared` there too and open nothing.
5. Keep the instance busy enough not to look idle (the weekly rebuild cron is a
   good candidate).

Budget: 4 GB image + 2-3 GB tree + a few hundred MB per checkpoint, well inside
200 GB.

### C. No server at all (Actions builds, Pages serves)

Half of this already exists: `configurator.yml` takes a machine id and a list of
features to disable, bootstraps, compiles, verifies and uploads the image as a
workflow artifact. To make that public you need a small broker holding a
fine-grained token (a free Cloudflare Worker, or a Netlify function) that calls
`workflow_dispatch` and links the run.

What you give up: live compiler log, instant feedback, artifacts after 90 days,
and the write-the-card step (which needs local hardware anyway).

## Do not expose it naked

The service runs a compiler and has no authentication. If it is public:

- keep it behind the tunnel or a reverse proxy with **Cloudflare Access** (free
  for small teams), or a single shared password in front;
- keep the built-in one-job queue (depth 4) so two visitors cannot compile at
  once;
- set a disk quota - each checkpoint adds up to 635 MB;
- never mount `/dev` into it or run it privileged: the SD-card writer is for
  the operator's own machine, not a public host.

## What this repository now contains

| File | Purpose |
|---|---|
| [deploy/Dockerfile](../deploy/Dockerfile) | multi-arch image: python 3.12 + PlatformIO 6.1.19 + the service |
| [deploy/entrypoint.sh](../deploy/entrypoint.sh) | bootstraps the pinned tree once, then serves |
| [deploy/docker-compose.yml](../deploy/docker-compose.yml) | one command, named volume for the tree, restart on failure |
| [deploy/configurator.service](../deploy/configurator.service) | systemd user unit for a bare-metal install |
| [deploy/cloudflared.yml](../deploy/cloudflared.yml) | free public hostname without opening a port |

Verified here: `docker build` succeeds (370 MB image), and the container serves
the UI and the 71-feature catalogue on `127.0.0.1:8787`; the tree bootstraps
into the volume on first start (`SKIP_BOOTSTRAP=1` serves the UI alone, which is
how the smoke test was run).
