# Hosting it for free, for a long time

The frontend is easy - it is a static page. The backend is the hard part: it
**compiles C code**, so it needs a real machine with a disk, not a serverless
function.

## Recommended: no server, no bill

Do not run the compiler on a host you pay for. Let **GitHub Actions** do the
compiling and let the result live as a **release asset** - public repos get
Actions minutes for free, and a release asset is downloadable by anyone without
an account.

- The site (Pages, free) posts a selection to a small **Cloudflare Worker**
  (free plan, hard request cap, no card on file).
- The Worker validates the selection, allows **3 builds per IP per hour** and
  **20 per day**, hashes it, and **returns the existing file if that exact
  selection was built before** - repeat requests cost nothing.
- A new selection dispatches @BT@configurator.yml@BT@, which compiles, verifies the ARM
  vector table, and publishes @BT@build-<hash>@BT@ as a release with the image, the
  manifest and the build log.
- The Worker answers @BT@GET /api/build/<hash>@BT@ by checking that deterministic tag.

What a spammer can achieve: a queued job, until the daily counter stops them.
What they cannot achieve: a bill, because neither Workers nor public Actions
minutes are metered against a payment method.

**Proven end to end, not sketched:** a dispatch with @BT@off=arc_support, mesh=7@BT@
produced release @BT@build-e93da78f5654@BT@; the image downloads anonymously at
229,956 bytes (HTTP 200, no cookies, no token), and its manifest predicts 229,352 B
flash with 4,120 B free. The Worker's tag rule was cross-checked against the
workflow on three selections and matches byte for byte; its pure logic passes 11
tests. Setup and code: [deploy/cloudflare/README.md](../deploy/cloudflare/README.md).

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
