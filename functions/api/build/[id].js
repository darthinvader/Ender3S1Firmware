// GET /api/build/<tag> - is that image published yet?
// No state is needed: the tag is deterministic, so the answer is a release lookup.
const REPO = "darthinvader/Ender3S1Firmware";
const API = "https://api.github.com";

function json(body, status = 200) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

export async function onRequestGet({ params }) {
  const tag = String(params.id || "");
  if (!/^build-[a-f0-9]{12}$/.test(tag)) return json({ error: "not found" }, 404);
  const release = await fetch(API + "/repos/" + REPO + "/releases/tags/" + tag, {
    headers: { accept: "application/vnd.github+json", "user-agent": "firmware-factory" },
  });
  if (release.ok) {
    const data = await release.json();
    const assets = {};
    for (const asset of data.assets || []) assets[asset.name] = asset.size;
    return json({ status: "done", tag: tag, published: (data.published_at || "").slice(0, 10), assets: assets,
      url: "https://github.com/" + REPO + "/releases/download/" + tag + "/firmware.bin" });
  }
  if (release.status === 404) return json({ status: "building", tag: tag });
  return json({ error: "GitHub answered " + release.status }, 502);
}

