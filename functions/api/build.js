// POST /api/build - ask GitHub Actions to compile one selection.
// Runs on Cloudflare Pages Functions (free plan, no card). The token is a
// repository-scoped fine-grained PAT stored as a Pages secret, never shipped to
// the browser.
import { validate, tagFor, dispatchBody } from "../_lib.js";

const REPO = "darthinvader/Ender3S1Firmware";
const API = "https://api.github.com";

function json(body, status = 200) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

export async function onRequestPost({ request, env }) {
  let payload;
  try { payload = await request.json(); } catch (error) { return json({ error: "send JSON" }, 400); }

  const selection = validate(payload);
  if (selection.error) return json(selection, 400);

  const tag = await tagFor(selection);

  // already published? nothing to compile.
  const release = await fetch(API + "/repos/" + REPO + "/releases/tags/" + tag, {
    headers: { accept: "application/vnd.github+json", "user-agent": "firmware-factory" },
  });
  if (release.ok) {
    return json({ status: "done", tag: tag,
      url: "https://github.com/" + REPO + "/releases/download/" + tag + "/firmware.bin" });
  }

  if (!env.GH_TOKEN) return json({ error: "the builder has no token configured" }, 500);

  const dispatched = await fetch(API + "/repos/" + REPO + "/actions/workflows/configurator.yml/dispatches", {
    method: "POST",
    headers: {
      authorization: "Bearer " + env.GH_TOKEN,
      accept: "application/vnd.github+json",
      "user-agent": "firmware-factory",
      "content-type": "application/json",
    },
    body: JSON.stringify(dispatchBody(selection)),
  });
  if (!dispatched.ok) {
    const text = await dispatched.text();
    return json({ error: "GitHub refused the dispatch: " + dispatched.status + " " + text.slice(0, 160) }, 502);
  }
  return json({ status: "building", tag: tag }, 202);
}

