// Cloudflare Worker: the only thing in front of the builder.
//
// It holds a fine-grained GitHub token, validates what it is asked to build,
// rate limits per IP, deduplicates identical selections, and dispatches the
// repository workflow. It cannot compile anything itself, so it cannot be made
// expensive: Workers' free plan stops at its daily request limit instead of
// billing, and GitHub Actions is free for public repositories.
//
// Bindings (wrangler.toml): KV namespace RL, secret GH_TOKEN.
// Vars: REPO, ALLOWED_ORIGIN, MAX_PER_IP_HOUR, MAX_PER_DAY.

import { canonicalSelection, validateSelection, tagFor, hashSelection } from "./selection.js";

const GH = "https://api.github.com";

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...extra,
    },
  });
}

function cors(env) {
  return {
    "access-control-allow-origin": env.ALLOWED_ORIGIN || "*",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type",
    "access-control-max-age": "86400",
  };
}

async function gh(env, path, init = {}) {
  const res = await fetch(GH + path, {
    ...init,
    headers: {
      authorization: "Bearer " + env.GH_TOKEN,
      accept: "application/vnd.github+json",
      "user-agent": "ender3s1-configurator-worker",
      "x-github-api-version": "2022-11-28",
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error("GitHub " + res.status + ": " + text.slice(0, 200));
  }
  return res;
}

async function bump(env, key, ttl) {
  const current = Number((await env.RL.get(key)) || "0");
  await env.RL.put(key, String(current + 1), { expirationTtl: ttl });
  return current + 1;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const base = cors(env);

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: base });

    try {
      if (url.pathname === "/api/build" && request.method === "POST") {
        const body = await request.json().catch(() => null);
        const selection = validateSelection(body);
        if (selection.error) return json(selection, 400, base);

        const ip = request.headers.get("cf-connecting-ip") || "unknown";
        const hour = new Date().toISOString().slice(0, 13);
        const day = new Date().toISOString().slice(0, 10);

        const perIp = await bump(env, "ip:" + ip + ":" + hour, 3600);
        if (perIp > Number(env.MAX_PER_IP_HOUR || 3)) {
          return json({ error: "rate limited: " + (env.MAX_PER_IP_HOUR || 3) + " builds per hour from one address" }, 429, base);
        }
        const perDay = await bump(env, "day:" + day, 90000);
        if (perDay > Number(env.MAX_PER_DAY || 20)) {
          return json({ error: "the daily build budget is used up; try again tomorrow" }, 429, base);
        }

        const canonical = canonicalSelection(selection);
        const hash = await hashSelection(canonical);
        const tag = await tagFor(selection);
        const existing = await env.RL.get("sel:" + hash, "json");
        if (existing) return json({ status: existing.status, id: hash, url: existing.url, run: existing.run, cached: true }, 200, base);

        const dispatched = await gh(env, "/repos/" + env.REPO + "/actions/workflows/configurator.yml/dispatches", {
          method: "POST",
          body: JSON.stringify({
            ref: "main",
            inputs: {
              machine: selection.machine,
              disable: selection.off.join(","),
              mesh: selection.mesh ? String(selection.mesh) : "",
            },
          }),
        });
        const runUrl = dispatched.headers.get("location") || null;

        await env.RL.put("sel:" + hash, JSON.stringify({
          status: "building",
          tag: tag,
          machine: selection.machine,
          off: selection.off,
          mesh: selection.mesh || null,
          run: runUrl,
          requested: new Date().toISOString(),
        }), { expirationTtl: 60 * 60 * 24 * 30 });

        return json({ status: "building", id: hash, run: runUrl }, 202, base);
      }

      if (url.pathname.startsWith("/api/build/") && request.method === "GET") {
        const hash = url.pathname.split("/").pop();
        if (!/^[a-f0-9]{12}$/.test(hash)) return json({ error: "not found" }, 404, base);
        const entry = await env.RL.get("sel:" + hash, "json");
        if (!entry) return json({ error: "unknown build" }, 404, base);
        if (!entry.tag) entry.tag = await tagFor(entry);

        // the published release tag is deterministic, so completion needs no state
        const download = "https://github.com/" + env.REPO + "/releases/download/" + entry.tag + "/firmware.bin";
        if (entry.status === "done") return json({ status: "done", id: hash, url: download }, 200, base);

        const head = await fetch(download, { method: "HEAD", redirect: "follow" });
        if (head.ok) {
          entry.status = "done";
          await env.RL.put("sel:" + hash, JSON.stringify(entry), { expirationTtl: 60 * 60 * 24 * 90 });
          return json({ status: "done", id: hash, url: download }, 200, base);
        }
        return json({ status: "building", id: hash, run: entry.run || null }, 200, base);
      }

      if (url.pathname === "/api/catalog") {
        const res = await fetch("https://raw.githubusercontent.com/" + env.REPO + "/main/tools/configurator/features.json", {
          cf: { cacheTtl: 300 },
        });
        return new Response(res.body, {
          status: res.status,
          headers: { "content-type": "application/json; charset=utf-8", "cache-control": "public, max-age=300", ...base },
        });
      }

      return json({ error: "not found", routes: ["GET /api/catalog", "POST /api/build", "GET /api/build/<id>"] }, 404, base);
    } catch (error) {
      return json({ error: String(error && error.message ? error.message : error) }, 500, base);
    }
  },
};

