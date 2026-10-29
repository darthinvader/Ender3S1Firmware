// GET /api/file?tag=<release>&name=<asset>   or   ?raw=<repo path>
// The browser cannot fetch github.com release assets directly (no CORS), which is
// why writing to the card failed with "Failed to fetch". This streams the bytes
// from the same origin instead.
const REPO = "darthinvader/Ender3S1Firmware";
const ASSETS = new Set(["firmware.bin", "meta.json", "checksums.txt", "build.log", "firmware-bundle.zip"]);

function bad(message, status) {
  return new Response(JSON.stringify({ error: message }), {
    status: status || 400,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const raw = url.searchParams.get("raw") || "";
  const tag = url.searchParams.get("tag") || "";
  const name = url.searchParams.get("name") || "";

  let upstream;
  let filename;
  if (raw) {
    if (!/^screen\/[A-Za-z0-9._\/-]+$/.test(raw) || raw.includes("..")) return bad("bad path");
    filename = raw.split("/").pop();
    upstream = await fetch("https://raw.githubusercontent.com/" + REPO + "/main/" + raw);
  } else {
    if (!/^build-[a-f0-9]{12}$/.test(tag)) return bad("bad tag");
    if (!ASSETS.has(name)) return bad("unknown asset");
    filename = name;
    const headers = { "user-agent": "firmware-factory" };
    if (env && env.GH_TOKEN) headers.authorization = "Bearer " + env.GH_TOKEN;
    upstream = await fetch("https://github.com/" + REPO + "/releases/download/" + tag + "/" + name,
      { headers: headers, redirect: "follow" });
  }

  if (!upstream.ok) return bad("upstream answered " + upstream.status, 502);

  return new Response(upstream.body, {
    headers: {
      "content-type": "application/octet-stream",
      "content-disposition": 'attachment; filename="' + filename + '"',
      "content-length": upstream.headers.get("content-length") || "",
      "cache-control": "public, max-age=3600",
      "access-control-allow-origin": "*",
    },
  });
}

