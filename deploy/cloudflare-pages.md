# Deploy the builder on Cloudflare Pages (no card)

Everything in this file happens in a browser, in one sitting, on the free plan.

## 1. Connect the repository

1. Cloudflare dashboard -> **Workers & Pages** -> **Create** -> **Pages** ->
   **Connect to Git**.
2. Pick **darthinvader/Ender3S1Firmware**.
3. Framework preset: **None**. Build command: **empty**. Build output directory:
   **docs**.
4. **Save and Deploy**. The first deployment takes a minute or two.

The site lands on `https://<project>.pages.dev`. The build page is
`/cloud/`; the functions are served from `/api/build` on the same origin, which is
why no CORS or tunnel is involved.

## 2. Give it a token

The function needs permission to start a workflow run, nothing else.

1. GitHub -> **Settings -> Developer settings -> Personal access tokens ->
   Fine-grained tokens -> Generate new token**.
2. **Repository access**: only `Ender3S1Firmware`.
3. **Permissions**: *Actions* -> **Read and write**; *Contents* -> **Read-only**.
   Nothing else.
4. Copy the token.
5. Cloudflare -> the Pages project -> **Settings -> Variables and secrets ->
   Add**: name `GH_TOKEN`, value the token, type **Secret**. Save.

## 3. Check it

- Open `https://<project>.pages.dev/cloud/`. The line under **Build** should read
  *Builder online: GitHub Actions compiles the selection and publishes it here.*
- Press **Build firmware**. A brand-new selection shows *compiling (n s)* for about
  three minutes, then the Result card fills with the file, manifest, bundle, log
  and checksums.
- Press it again for the same selection: the function finds the release tag and
  answers immediately, with no compile.

## What runs where

| Step | Where | Cost |
|---|---|---|
| Page + trigger | Cloudflare Pages (free plan, no card) | 500 builds/month, 100k function requests/day |
| Compile | GitHub Actions, public repository | free, no card |
| Storage of results | GitHub release assets on this repository | free |
| Dedupe / status | release tag lookup, no KV or database | free |

## Local check before deploying

`node functions/selftest.mjs` runs 16 checks against a stubbed GitHub.

To exercise the real runtime: `npx wrangler pages dev docs` serves the site and the
functions together on `http://localhost:8787`. A `POST /api/build` with a selection
that is already published answers `{"status":"done"}` without a token.

