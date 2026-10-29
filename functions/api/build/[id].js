// GET /api/build/<tag>[?run=<id>] - published, queued, running (which step), or failed.
// The run id comes from the dispatch response; without it the newest recent run
// is used, never an old one.
const REPO = "darthinvader/Ender3S1Firmware";
const API = "https://api.github.com";
const WORKFLOW = "configurator.yml";

const FRIENDLY = [
  ["Bootstrap", "preparing the sources"],
  ["Apply", "applying the selection"],
  ["Compile", "compiling"],
  ["Verify", "verifying the image"],
  ["Upload", "uploading"],
  ["Publish", "publishing"],
];

function json(body, status = 200) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function headers(env) {
  const base = { accept: "application/vnd.github+json", "user-agent": "firmware-factory" };
  if (env && env.GH_TOKEN) base.authorization = "Bearer " + env.GH_TOKEN;
  return base;
}

export async function onRequestGet({ params, request, env }) {
  const tag = String(params.id || "");
  if (!/^build-[a-f0-9]{12}$/.test(tag)) return json({ error: "not found" }, 404);
  const auth = headers(env);

  const release = await fetch(API + "/repos/" + REPO + "/releases/tags/" + tag, { headers: auth });
  if (release.ok) {
    const data = await release.json();
    const assets = {};
    for (const asset of data.assets || []) assets[asset.name] = asset.size;
    return json({
      status: "done", tag: tag, published: (data.published_at || "").slice(0, 10), assets: assets,
      url: "https://github.com/" + REPO + "/releases/download/" + tag + "/firmware.bin",
    });
  }
  if (release.status !== 404) return json({ error: "GitHub answered " + release.status }, 502);

  const wanted = new URL(request.url).searchParams.get("run");
  let run = null;
  if (wanted && /^[0-9]+$/.test(wanted)) {
    const one = await fetch(API + "/repos/" + REPO + "/actions/runs/" + wanted, { headers: auth });
    if (one.ok) run = await one.json();
  }
  if (!run) {
    const runs = await fetch(API + "/repos/" + REPO + "/actions/workflows/" + WORKFLOW + "/runs?per_page=6",
      { headers: auth });
    if (runs.ok) {
      const list = (await runs.json()).workflow_runs || [];
      const fresh = list.filter((r) => Date.now() - Date.parse(r.created_at) < 15 * 60 * 1000);
      run = fresh.find((r) => r.status === "queued" || r.status === "in_progress") || fresh[0] || null;
    }
  }
  if (!run) return json({ status: "building", tag: tag });

  const elapsed = Math.max(0, Math.round((Date.now() - Date.parse(run.created_at)) / 1000));
  const base = { tag: tag, run: run.html_url, elapsed: elapsed };

  if (run.status === "queued") return json({ status: "queued", ...base });
  if (run.status !== "in_progress") {
    return json({ status: "failed", ...base, error: "the workflow ended as " + run.conclusion });
  }

  const steps = [];
  const jobs = await fetch(API + "/repos/" + REPO + "/actions/runs/" + run.id + "/jobs", { headers: auth });
  if (jobs.ok) {
    for (const job of (await jobs.json()).jobs || []) {
      for (const step of job.steps || []) {
        if (step.status === "queued") continue;
        const friendly = FRIENDLY.find((pair) => step.name.startsWith(pair[0]));
        steps.push({
          name: friendly ? friendly[1] : step.name,
          status: step.status === "in_progress" ? "running" : step.conclusion || step.status,
        });
      }
    }
  }
  return json({ status: "running", ...base, detail: steps });
}

