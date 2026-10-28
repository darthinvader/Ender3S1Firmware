# The build broker (Cloudflare Worker, free plan)

The public site cannot compile C. This Worker does the only thing that is safe to
expose: it validates a selection, rate limits, deduplicates, and asks GitHub
Actions to build it. The image then appears as a **release asset**, which anyone
can download without an account.

## Why this cannot bill you

| Limit | Behaviour when reached |
|---|---|
| Workers free plan: 100k requests/day | requests fail; no card on file, nothing to charge |
| This Worker: 3 builds per IP per hour, 20 builds per day | returns 429 with the reason |
| Identical selection | returns the already-published release; **no new build** |
| GitHub Actions, public repository | free; a spike queues jobs instead of billing |

The worst a stranger can do is queue builds, and the daily counter stops that
after 20. Nothing here is metered against a payment method.

## One-time setup (your account, ~5 minutes)

1. Create a **fine-grained personal access token** for this repository only:
   *Actions: read and write*, *Contents: read*. Nothing else.
2. Create the KV namespace and copy its id into `wrangler.toml`:
   ```bash
   cd deploy/cloudflare
   npx wrangler kv namespace create RL
   ```
3. Store the token as a secret and deploy:
   ```bash
   npx wrangler secret put GH_TOKEN
   npx wrangler deploy
   ```
4. Point the site at it: set `ALLOWED_ORIGIN` in `wrangler.toml` to your Pages origin.

## Try it

```bash
curl -s -X POST https://ender3s1-build-broker.YOUR.workers.dev/api/build \
  -H 'content-type: application/json' \
  -d '{"machine":"ender3s1-f103","off":["arc_support"],"mesh":7}'
# -> {"status":"building","id":"e93da78f5654","run":"..."}

curl -s https://ender3s1-build-broker.YOUR.workers.dev/api/build/e93da78f5654
# -> once done: {"status":"done","url":"https://github.com/.../releases/download/build-e93da78f5654/firmware.bin"}
```

## What is verified here, without a Worker account

The Worker logic is pure where it matters, and tested:

```bash
node deploy/cloudflare/selection.test.mjs   # 11 checks
```

The part that actually builds was proven end to end: a dispatch with
`off=arc_support, mesh=7` produced release **build-e93da78f5654**, and the image
downloaded anonymously (no cookies, no token) at 229,956 bytes, matching the
manifest's prediction of 229,352 B flash and 4,120 B free.

The tag rule in `selection.js` and in the workflow were cross-checked on three
selections; they agree byte for byte.

