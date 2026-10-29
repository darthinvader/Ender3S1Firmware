/* Ender 3 S1 firmware configurator - browser side.
   One file, no build step: the page is served by Cloudflare Pages (docs/cloud)
   and mirrored on GitHub Pages. Sections are separated by banner comments. */

/* ------------------------------------------------------------------------
   constants and state
   ------------------------------------------------------------------------ */
const REPO = "darthinvader/Ender3S1Firmware";
const RAW = "https://raw.githubusercontent.com/" + REPO + "/main/";
const CATALOG_URL = RAW + "tools/configurator/features.json";
const FENCE = String.fromCharCode(96).repeat(3);
const app = { catalog: null, on: new Set(), off: new Set(), mesh: 7, filter: "", collapsed: {},
              poll: 0, tag: null, job: null, gen: 0, backend: null, mode: null, writing: false };

const $ = (id) => document.getElementById(id);
const usable = (f) => f.buildable !== false;
const priced = (f) => f.cost_source === "measured" && typeof f.flash === "number" && f.flash !== 0;
const fmt = (n) => Number(n || 0).toLocaleString("en-US");
const mb = (bytes) => (Number(bytes || 0) / (1024 * 1024)).toFixed(2) + " MiB";
function fileUrl(params) {
  const url = new URL("../api/file", location.href);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return url.toString();
}

function setBuildButton(text, state) {
  const btn = $("build");
  btn.textContent = text;
  btn.className = "primary" + (state ? " " + state : "");
}

function logLine(text) {
  const box = $("log");
  box.hidden = false;
  const stamp = new Date().toLocaleTimeString("en-GB", { hour12: false });
  box.textContent += stamp + "  " + text + String.fromCharCode(10);
  box.scrollTop = box.scrollHeight;
}

const human = (bytes) => {
  const n = Number(bytes || 0);
  return Math.abs(n) >= 1048576 ? fmt(n) + " B · " + mb(n) : fmt(n) + " B";
};

function isOn(f) {
  if (app.on.has(f.id)) return true;
  if (app.off.has(f.id)) return false;
  return !!f.on_by_default;
}
function setFeature(id, value) {
  const f = app.catalog.features.find((x) => x.id === id);
  if (!f) return;
  if (value === !!f.on_by_default) { app.on.delete(id); app.off.delete(id); }
  else if (value) { app.on.add(id); app.off.delete(id); }
  else { app.off.add(id); app.on.delete(id); }
}
function withDependencies(id, value) {
  const byId = (x) => app.catalog.features.find((f) => f.id === x);
  if (value) {
    const queue = [id];
    while (queue.length) {
      const cur = byId(queue.pop());
      if (!cur) continue;
      for (const req of cur.requires || []) {
        const target = byId(req);
        if (target && usable(target) && !isOn(target)) { setFeature(req, true); queue.push(req); }
      }
      for (const other of cur.conflicts || []) {
        const target = byId(other);
        if (target && isOn(target)) setFeature(other, false);
      }
    }
  } else {
    let again = true;
    while (again) {
      again = false;
      for (const f of app.catalog.features) {
        if (isOn(f) && (f.requires || []).includes(id)) { setFeature(f.id, false); again = true; }
      }
    }
  }
}
function predicted() {
  const base = app.catalog.baseline || { flash: 0, ram: 0 };
  let flash = base.flash, ram = base.ram;
  for (const f of app.catalog.features) {
    if (!usable(f)) continue;
    const was = !!f.on_by_default, now = isOn(f);
    if (was === now) continue;
    if (priced(f)) flash += now ? f.flash : -f.flash;
    if (typeof f.ram === "number" && f.ram) ram += now ? f.ram : -f.ram;
  }
  return { flash, ram, base };
}
function region() {
  const m = app.catalog.machines.find((x) => x.id === $("machine").value) || {};
  return m.flash_region || 233472;
}
function selection() {
  const on = [], off = [];
  for (const f of app.catalog.features) {
    if (!usable(f)) continue;
    const now = isOn(f), was = !!f.on_by_default;
    if (now && !was) on.push(f.id);
    if (!now && was) off.push(f.id);
  }
  return { machine: $("machine").value, on: on.sort(), off: off.sort(), mesh: app.mesh };
}
async function sha256Hex(text) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(d)).map((b) => b.toString(16).padStart(2, "0")).join("");
}
function tagLine(sel) {
  let line = "machine=" + sel.machine + ";off=" + sel.off.join(",") + ";mesh=" + sel.mesh;
  if (sel.on.length) line += ";on=" + sel.on.join(",");
  return line;
}
async function currentTag() {
  const sel = selection();
  return { sel: sel, tag: "build-" + (await sha256Hex(tagLine(sel))).slice(0, 12) };
}

async function loadCatalog() {
  try {
    const cached = localStorage.getItem("e3s1-catalog");
    const at = localStorage.getItem("e3s1-catalog-at");
    if (cached && at && Date.now() - Number(at) < 3600 * 1000) app.catalog = JSON.parse(cached);
    else {
      const res = await fetch(CATALOG_URL, { cache: "no-cache" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      app.catalog = await res.json();
      localStorage.setItem("e3s1-catalog", JSON.stringify(app.catalog));
      localStorage.setItem("e3s1-catalog-at", String(Date.now()));
    }
    app.mesh = (app.catalog.mesh && app.catalog.mesh.default) || 7;
    fillMachines();
    fillScreen();
    renderMesh();
    $("version-note").textContent = "";
    render();
    renderBudget();
    await update();
  } catch (error) {
    $("groups").innerHTML = '<p class="bad">Could not load the catalogue: ' + error.message +
      '.</p><p class="hint"><a href="" onclick="location.reload();return false">try again</a></p>';
  }
}

function fillMachines() {
  const host = $("machine");
  host.innerHTML = "";
  (app.catalog.machines || []).forEach((m) => {
    const option = document.createElement("option");
    option.value = m.id;
    option.textContent = m.label + (m.supported ? "" : " - not supported here");
    option.disabled = !m.supported;
    if (m.supported) option.selected = true;
    host.appendChild(option);
  });
  host.onchange = async () => { render(); renderBudget(); await update(); };
}

function fillScreen() {
  const screen = app.catalog.screen || { os: [], assets: [] };
  const fill = (id, entries) => {
    const host = $(id);
    host.innerHTML = "";
    entries.forEach((entry) => {
      const option = document.createElement("option");
      option.value = entry.id;
      option.textContent = entry.label + " (" + human(entry.bytes || 0) + ")";
      host.appendChild(option);
    });
    return entries;
  };
  const os = fill("screen-os", screen.os || []);
  const assets = fill("screen-assets", screen.assets || []);
  const sync = () => {
    const osEntry = os.find((x) => x.id === $("screen-os").value);
    const assetEntry = assets.find((x) => x.id === $("screen-assets").value);
    const osLink = $("screen-download"), assetLink = $("screen-assets-download");
    if (osEntry) { osLink.href = RAW + osEntry.path; osLink.hidden = false; }
    else osLink.hidden = true;
    if (assetEntry && (assetEntry.path || assetEntry.files)) {
      assetLink.href = assetEntry.path ? RAW + assetEntry.path : "https://github.com/" + REPO + "/tree/main/screen/" + assetEntry.id;
      assetLink.hidden = false;
    } else assetLink.hidden = true;
    $("screen-note").textContent = screen.note || "";
  };
  $("screen-os").onchange = sync;
  $("screen-assets").onchange = sync;
  sync();
}

function renderMesh() {
  const spec = app.catalog.mesh || { presets: [3, 5, 7, 9], default: 7 };
  const host = $("mesh-options");
  host.innerHTML = "";
  (spec.presets || [7]).forEach((n) => {
    const label = document.createElement("label");
    label.className = "radio" + (n === app.mesh ? " on" : "");
    const input = document.createElement("input");
    input.type = "radio"; input.name = "mesh"; input.value = String(n); input.checked = n === app.mesh;
    input.onchange = async () => { app.mesh = n; renderMesh(); renderBudget(); await update(); };
    const text = document.createElement("span");
    text.textContent = n + " x " + n + " (" + n * n + " pts)";
    label.appendChild(input); label.appendChild(text); host.appendChild(label);
  });
  $("mesh-note").textContent = "Default for a fresh EEPROM; the printer can still change it between 3 and 9.";
}

function render() {
  const host = $("groups");
  const scroll = window.scrollY;
  host.innerHTML = "";
  const needle = app.filter.trim().toLowerCase();
  let shown = 0;
  (app.catalog.groups || []).forEach((group) => {
    const all = app.catalog.features.filter((f) => f.group === group && usable(f));
    const feats = all.filter((f) => !needle ||
      (f.label + " " + f.id + " " + (f.summary || "")).toLowerCase().includes(needle));
    if (!feats.length) return;
    shown += feats.length;
    const box = document.createElement("div");
    box.className = "group" + (app.collapsed[group] ? " collapsed" : "");
    const head = document.createElement("h2");
    const left = document.createElement("span");
    left.textContent = group + "  (" + feats.filter(isOn).length + "/" + feats.length + ")";
    const right = document.createElement("span");
    right.textContent = app.collapsed[group] ? "show" : "hide";
    head.appendChild(left); head.appendChild(right);
    head.onclick = () => { app.collapsed[group] = !app.collapsed[group]; render(); };
    box.appendChild(head);
    feats.forEach((f) => {
      const row = document.createElement("label");
      row.className = "row" + (isOn(f) !== !!f.on_by_default ? " changed" : "");
      const cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = isOn(f);
      cb.onchange = async () => {
        setFeature(f.id, cb.checked);
        withDependencies(f.id, cb.checked);
        render(); renderBudget(); await update();
      };
      const text = document.createElement("div");
      const name = document.createElement("div");
      name.className = "name"; name.textContent = f.label;
      const sub = document.createElement("div");
      sub.className = "sub"; sub.textContent = f.summary;
      text.appendChild(name); text.appendChild(sub);
      const cost = document.createElement("span");
      cost.className = "cost";
      cost.textContent = priced(f) ? (f.flash > 0 ? "+" : "") + fmt(f.flash) + " B" : "~0 B";
      row.appendChild(cb); row.appendChild(text); row.appendChild(cost);
      box.appendChild(row);
    });
    host.appendChild(box);
  });
  if (!shown) host.innerHTML = '<p class="hint">No feature matches that filter.</p>';
  $("filter-count").textContent = shown + " shown";
  window.scrollTo(0, scroll);
}

function renderBudget() {
  const p = predicted();
  const reg = region();
  const over = Math.max(0, p.flash - reg);
  $("predicted").textContent = human(p.flash);
  $("bar").classList.toggle("over", over > 0);
  $("bar-used").style.transform = "scaleX(" + Math.min(1, p.flash / reg).toFixed(4) + ")";
  $("free").textContent = over ? "over by " + fmt(over) + " B" : fmt(reg - p.flash) + " B free";
  $("region").textContent = "region " + fmt(reg) + " B";
  const diff = p.flash - (app.catalog.baseline ? app.catalog.baseline.flash : p.flash);
  const delta = $("delta");
  if (diff === 0) { delta.textContent = "same size as the shipped image"; delta.className = "delta"; }
  else if (diff < 0) { delta.textContent = human(-diff) + " smaller than the shipped image"; delta.className = "delta good"; }
  else { delta.textContent = human(diff) + " larger than the shipped image"; delta.className = "delta bad"; }
  $("ramline").textContent = "RAM " + human(p.ram);
  const changed = app.catalog.features.filter((f) => usable(f) && isOn(f) !== !!f.on_by_default).length;
  const onCount = app.catalog.features.filter((f) => usable(f) && isOn(f)).length;
  $("countline").textContent = onCount + " features on, " + changed + " changed from the shipped build";
  const btn = $("build");
  const fits = p.flash <= reg;
  btn.disabled = !fits;
  $("build-note").textContent = fits ? "" : "This selection is " + human(p.flash - reg) +
    " over the region - switch something off before building.";
}

async function update() {
  const gen = ++app.gen;
  const { sel, tag } = await currentTag();
  if (gen !== app.gen) return;
  app.tag = tag;
  const meta = await fetchRelease(tag);
  if (gen !== app.gen) return;
  if (meta) {
    showResult(meta, tag);
    $("build-note").textContent = "This exact selection is already published - download below.";
  } else {
    $("result").hidden = true;
    $("build-note").textContent = $("build").disabled ? $("build-note").textContent : "";
  }
}

async function fetchRelease(tag) {
  try {
    const res = await fetch("https://api.github.com/repos/" + REPO + "/releases/tags/" + tag,
      { headers: { accept: "application/vnd.github+json" } });
    if (!res.ok) return null;
    const data = await res.json();
    const assets = {};
    for (const asset of data.assets || []) assets[asset.name] = asset;
    return { tag: tag, published: (data.published_at || "").slice(0, 10), assets: assets };
  } catch (error) { return null; }
}

function showCardSizes(meta) {
  const assets = (meta && meta.assets) || {};
  const bytes = (entry) => (entry && typeof entry === "object" ? entry.size : null);
  const label = (n) => (typeof n === "number" ? " (" + n.toLocaleString("en-US") + " B)" : "");
  if ($("size-board")) $("size-board").textContent = label(bytes(assets["firmware.bin"]));
  if ($("size-manifest")) $("size-manifest").textContent = label(bytes(assets["meta.json"]));
}

function showResult(meta, tag) {
  if (tag && tag !== app.tag) return;
  const bin = meta.assets["firmware.bin"];
  const manifest = meta.assets["meta.json"];
  const log = meta.assets["build.log"];
  const bundle = meta.assets["firmware-bundle.zip"];
  $("result").hidden = false;
  $("r-size").textContent = bin ? human(bin.size) : "-";
  const p = predicted();
  $("r-pred").textContent = human(p.flash);
  $("r-free").textContent = human(Math.max(0, region() - p.flash));
  $("r-ram").textContent = human(p.ram);
  $("r-mesh").textContent = app.mesh + " x " + app.mesh;
  const sel = selection();
  $("r-sel").textContent = (sel.off.length ? "off: " + sel.off.join(", ") : "") +
    (sel.on.length ? (sel.off.length ? " · " : "") + "on: " + sel.on.join(", ") : "") ||
    "nothing changed from what you run";
  $("r-sha").textContent = meta.assets["checksums.txt"] ? "in checksums.txt" : (bin ? "in the build log" : "-");
  const link = (el, asset, fallbackName) => {
    if (asset) { el.href = asset.browser_download_url; el.hidden = false; }
    else if (fallbackName) { el.href = "https://github.com/" + REPO + "/releases/download/" + meta.tag + "/" + fallbackName; el.hidden = false; }
    else el.hidden = true;
  };
  app.last = { tag: meta.tag, published: meta.published, files: {} };
  for (const name of ["firmware.bin", "meta.json", "firmware-bundle.zip", "checksums.txt"]) {
    if (meta.assets[name]) app.last.files[name] = meta.assets[name].browser_download_url;
  }
  link($("download"), bin, "firmware.bin");
  link($("manifest"), manifest, "meta.json");
  link($("loglink"), log, "build.log");
  link($("bundle"), bundle, null);
  if ($("card-bundle")) link($("card-bundle"), bundle, null);
  showCardSizes(meta);
  const sums = $("checksums");
  if (sums) { link(sums, meta.assets["checksums.txt"], "checksums.txt"); }
}


async function startBuild() {
  if (!app.backend) return;
  if ($("build").disabled) return;
  const sel = selection();
  if (app.mode === "pages") return startPagesBuild(sel);
  $("status").hidden = false;
  $("result").hidden = true;
  $("log").hidden = false;
  $("log").textContent = "";
  setBuildButton("Queued...", "busy");
  logLine("build queued on this machine");
  $("phase").textContent = "queued";
  $("phase").className = "mono warn";
  $("jobid").textContent = "";
  $("log").hidden = true;
  $("build").disabled = true;
  try {
    const res = await fetch(app.backend + "/api/build", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ machine: sel.machine, on: sel.on, off: sel.off, mesh: sel.mesh }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
    $("jobid").textContent = data.id;
    pollJob(data.id);
  } catch (error) {
    $("phase").textContent = "refused";
    $("phase").className = "mono bad";
    $("build-note").textContent = "The builder refused the job: " + error.message;
    $("build").disabled = false;
  }
}

async function startPagesBuild(sel) {
  $("result").hidden = true;
  $("log").hidden = false;
  $("log").textContent = "";
  $("build").disabled = true;
  setBuildButton("Asking the builder...", "busy");
  logLine("selection sent: " + sel.on.length + " on, " + sel.off.length + " off, mesh " + sel.mesh);
  try {
    const res = await fetch("../api/build", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ machine: sel.machine, on: sel.on, off: sel.off, mesh: sel.mesh }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
    $("jobid").textContent = data.tag || "";
    if (data.status === "done") {
      $("build").disabled = false;
      setBuildButton("Already published - download below", "ok");
      logLine("this exact image already exists (" + data.tag + ")");
      await showRelease(data.tag);
      return;
    }
    setBuildButton("Queued...", "busy");
    logLine("queued on GitHub Actions as " + data.tag);
    if (data.run) logLine("run " + data.run);
    pollPages(data.tag, data.run);
  } catch (error) {
    setBuildButton("Build firmware", "");
    $("build-note").textContent = "The builder refused the job: " + error.message;
    logLine("refused: " + error.message);
    $("build").disabled = false;
  }
}


/* ------------------------------------------------------------------------
   build: dispatch, poll, result
   ------------------------------------------------------------------------ */
function pollPages(tag, runId) {
  const suffix = runId ? "?run=" + encodeURIComponent(runId) : "";
  const announced = new Set();
  clearInterval(app.poll);
  const started = Date.now();
  let lastStep = "";
  app.poll = setInterval(async () => {
    try {
      const res = await fetch("../api/build/" + tag + suffix);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
      const seconds = data.elapsed || Math.round((Date.now() - started) / 1000);

      if (data.status === "queued") {
        setBuildButton("In the queue (" + seconds + " s)", "busy");
      } else if (data.status === "running") {
        const step = (data.detail || []).find((s) => s.status === "running");
        const name = step ? step.name : "working";
        setBuildButton("Compiling: " + name + " (" + seconds + " s)", "busy");
        if (step && step.name !== lastStep) {
          lastStep = step.name;
          if (!announced.has("start:" + step.name)) {
            announced.add("start:" + step.name);
            logLine("started: " + step.name);
          }
        }
        for (const s of data.detail || []) {
          if (s.status !== "success") continue;
          if (announced.has("done:" + s.name)) continue;
          announced.add("done:" + s.name);
          logLine("done: " + s.name);
        }
      } else if (data.status === "done") {
        clearInterval(app.poll);
        $("build").disabled = false;
        setBuildButton("Published - download below", "ok");
        logLine("published " + tag);
        await showRelease(tag);
      } else if (data.status === "failed") {
        clearInterval(app.poll);
        $("build").disabled = false;
        setBuildButton("Build failed - see the log", "bad");
        logLine("failed: " + (data.error || "the workflow ended early"));
        $("build-note").textContent = data.run ? "The run is at " + data.run : "The run failed.";
      }
      if (data.run && $("run-link")) { $("run-link").href = data.run; $("run-link").hidden = false; }
    } catch (error) {
      clearInterval(app.poll);
      $("build").disabled = false;
      setBuildButton("Status lost - try again", "bad");
      $("build-note").textContent = "Could not read the build status: " + error.message;
    }
  }, 4000);
}

async function showRelease(tag) {
  const meta = await fetchRelease(tag);
  if (!meta) {
    $("build-note").textContent = "Published as " + tag + " but the release could not be read yet; try again in a moment.";
    return;
  }
  $("build-note").textContent = "Published " + meta.published + " - download below.";
  showResult(meta, tag);
}

function pollJob(id) {
  clearInterval(app.poll);
  app.poll = setInterval(async () => {
    try {
      const res = await fetch(app.backend + "/api/build/" + id);
      const job = await res.json();
      if (!res.ok) throw new Error(job.error || ("HTTP " + res.status));
      $("phase").textContent = job.phase || job.status;
      $("phase").className = "mono " + (job.status === "failed" ? "bad" : job.status === "succeeded" ? "ok" : "warn");
      if (job.log && job.log.length) {
        $("log").hidden = false;
        $("log").textContent = job.log.join("");
        $("log").scrollTop = $("log").scrollHeight;
      }
      if (job.status === "succeeded") {
        clearInterval(app.poll);
        $("build").disabled = false;
        setBuildButton("Built - download below", "ok");
        showJobResult(id, job);
      } else if (job.status === "failed") {
        clearInterval(app.poll);
        $("build").disabled = false;
        $("build-note").textContent = "Build failed: " + (job.error || "see the log above");
      }
    } catch (error) {
      clearInterval(app.poll);
      $("build").disabled = false;
      $("phase").textContent = "lost contact";
      $("phase").className = "mono bad";
    }
  }, 1200);
}

function showJobResult(id, job) {
  const base = app.backend + "/api/build/" + id;
  const result = job.result || {};
  const predicted = job.predicted || {};
  $("result").hidden = false;
  $("r-size").textContent = result.file_size ? human(result.file_size) : "-";
  $("r-pred").textContent = predicted.flash ? human(predicted.flash) : "-";
  $("r-free").textContent = predicted.flash_free != null ? human(predicted.flash_free) : "-";
  $("r-ram").textContent = result.ram_used ? human(result.ram_used) : (predicted.ram ? human(predicted.ram) : "-");
  const size = job.mesh || app.mesh;
  $("r-mesh").textContent = size + " x " + size;
  const off = job.off || [], on = job.on || [];
  $("r-sel").textContent = (off.length ? "off: " + off.join(", ") : "") +
    (on.length ? (off.length ? " · " : "") + "on: " + on.join(", ") : "") || "nothing changed from the shipped build";
  $("r-sha").textContent = result.sha256 ? result.sha256.slice(0, 16) + "..." : "-";
  $("download").href = base + "/firmware.bin"; $("download").hidden = false;
  $("manifest").href = base + "/manifest.json"; $("manifest").hidden = false;
  $("bundle").href = base + "/bundle.zip"; $("bundle").hidden = false;
  $("loglink").href = "data:text/plain;charset=utf-8," + encodeURIComponent((job.log || []).join(""));
  $("loglink").hidden = false;
  $("checksums").hidden = true;
  $("build-note").textContent = "Built in this browser session from the pinned sources.";
}

function applyPreset(name) {
  document.querySelectorAll(".preset").forEach((b) => b.classList.toggle("active", b.dataset.preset === name));
  app.on.clear(); app.off.clear();
  if (name === "min") {
    app.catalog.features.forEach((f) => { if (usable(f)) setFeature(f.id, false); });
  } else if (name === "fit") {
    const candidates = app.catalog.features.filter((f) => usable(f) && !isOn(f) && priced(f))
      .sort((a, b) => a.flash - b.flash);
    for (const f of candidates) {
      if ((f.conflicts || []).some((other) => {
        const t = app.catalog.features.find((x) => x.id === other);
        return t && isOn(t);
      })) continue;
      setFeature(f.id, true);
      if (predicted().flash > region()) setFeature(f.id, false);
    }
  }
  render(); renderBudget();
  update();
}

document.querySelectorAll(".preset").forEach((b) => { b.onclick = () => applyPreset(b.dataset.preset); });
$("filter").oninput = (event) => { app.filter = event.target.value; render(); };
$("build").onclick = startBuild;
async function findBackend() {
  // (a) the same-origin Pages Function: GET /api/build/<a tag that cannot exist>
  try {
    const probe = await fetch("../api/build/build-000000000000", { signal: AbortSignal.timeout(6000) });
    if (probe.ok) { app.mode = "pages"; return ".."; }
  } catch (error) { /* not deployed */ }
  // (b) a self-hosted configurator named in backend.json
  try {
    const res = await fetch("backend.json?t=" + Date.now(), { cache: "no-store" });
    if (!res.ok) return null;
    const config = await res.json();
    if (!config.url) return null;
    const probe = await fetch(config.url + "/api/catalog", { signal: AbortSignal.timeout(6000) });
    if (probe.ok) { app.mode = "server"; return config.url; }
  } catch (error) { /* offline */ }
  return null;
}


/* ------------------------------------------------------------------------
   boot and selection
   ------------------------------------------------------------------------ */
async function boot() {
  app.backend = await findBackend();
  const state = $("builder-state");
  if (app.backend) {
    state.className = "hint ok";
    state.textContent = app.mode === "pages"
      ? "Builder online: GitHub Actions compiles the selection and publishes it here. A new image takes a few minutes; anything already built downloads at once."
      : "Builder online: this server compiles the selection and hands back the files in seconds.";
  } else {
    state.className = "hint warn";
    let mirror = "";
    try {
      const config = await (await fetch("backend.json?t=" + Date.now(), { cache: "no-store" })).json();
      if (config && config.pages && location.hostname.endsWith("github.io")) {
        mirror = " The live build page is at " + config.pages + " - this copy is a mirror.";
      }
    } catch (error) { /* no pointer */ }
    state.textContent = "Public builder offline right now. Downloads of already published images still work; " +
      "a new build needs the machine that serves it, or a GitHub request from the maintenance page." + mirror;
    $("build").disabled = true;
    $("build-note").textContent = "The builder is offline; pick a published image below or come back later.";
  }
  await loadCatalog();
}

let cardHandle = null;
// capability detection, with ?nofolder=1 to exercise the fallback on purpose
const canWriteFolder = typeof window.showDirectoryPicker === "function" &&
  !location.search.includes("nofolder");

function initCardWriter() {
  if (canWriteFolder) return;
  $("pick-card").disabled = true;
  $("pick-card").textContent = "This browser cannot write into a folder";
  $("write-card").hidden = true;
  $("card-bundle").hidden = false;
  $("card-note").textContent = "Firefox and Safari do not let a page write into a folder " +
    "(Chrome and Edge do). Download the bundle and unzip it onto the card instead - " +
    "the printer only needs firmware.bin at the card's root.";
}

initCardWriter();

/* ------------------------------------------------------------------------
   write to card
   ------------------------------------------------------------------------ */
async function pickCard() {
  if (!canWriteFolder) {
    $("card-note").textContent = "This browser cannot write into a folder; use the bundle download below.";
    return;
  }
  try {
    const picked = await window.showDirectoryPicker({ mode: "readwrite", id: "sd-card" });
    if (cardHandle && picked && picked.name === cardHandle.name) {
      $("card-note").textContent = "Already using " + cardHandle.name + " - press the copy button when ready.";
      refreshCard();
      return;
    }
    cardHandle = picked;
    $("card-note").textContent = "Folder chosen: " + cardHandle.name +
      ". Nothing copied yet - tick the files, then press the copy button.";
    refreshCard();
  } catch (error) {
    $("card-note").textContent = "No folder chosen.";
  }
}

function refreshCard() {
  const boxes = ["w-board", "w-manifest", "w-screen"];
  const chosen = boxes.filter((id) => $(id) && $(id).checked);
  const button = $("write-card");
  let label;
  if (app.writing) label = "Copying...";
  else if (!cardHandle) label = "Choose a card first";
  else if (!chosen.length) label = "Tick what to copy";
  else label = "Copy " + chosen.length + " file" + (chosen.length === 1 ? "" : "s") + " to " + cardHandle.name;
  button.textContent = label;
  button.disabled = !cardHandle || !chosen.length || !!app.writing;
  if ($("card-picked")) $("card-picked").textContent = cardHandle
    ? "Using " + cardHandle.name + "."
    : "No folder chosen yet - nothing is copied until you press the copy button.";
}

function freshName(extension) {
  const bytes = new Uint8Array(3);
  crypto.getRandomValues(bytes);
  const code = Array.from(bytes).map((b) => b.toString(16).padStart(2, "0")).join("");
  return "firmware-" + code + "." + extension;
}

async function writeCard() {
  if (!cardHandle) return;
  if (app.writing) return;
  app.writing = true;
  const tasks = [];
  const binaryName = $("w-fresh").checked ? freshName("bin") : "firmware.bin";
  if ($("w-board").checked && app.last) tasks.push([binaryName, fileUrl({ tag: app.last.tag, name: "firmware.bin" })]);
  if ($("w-manifest").checked && app.last) tasks.push(["meta.json", fileUrl({ tag: app.last.tag, name: "meta.json" })]);
  if ($("w-screen").checked) {
    const osId = $("screen-os").value, assetId = $("screen-assets").value;
    const screen = (app.catalog && app.catalog.screen) || { os: [], assets: [] };
    const osEntry = (screen.os || []).find((x) => x.id === osId);
    const assetEntry = (screen.assets || []).find((x) => x.id === assetId);
    if (osEntry) tasks.push([osEntry.path.split("/").pop(), fileUrl({ raw: osEntry.path })]);
    if (assetEntry && assetEntry.path) tasks.push([assetEntry.path.split("/").pop(), fileUrl({ raw: assetEntry.path })]);
  }
  if (!tasks.length) {
    $("card-note").textContent = "Nothing to copy - build an image first.";
    app.writing = false;
    refreshCard();
    return;
  }
  app.writing = true;
  refreshCard();
  for (const [name, url] of tasks) {
    if (!url) continue;
    $("card-note").textContent = "writing " + name + " ...";
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error("HTTP " + response.status);
      const blob = await response.blob();
      const handle = await cardHandle.getFileHandle(name, { create: true });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      logLine("wrote " + name + " (" + human(blob.size) + ")");
    } catch (error) {
      $("card-note").textContent = "could not write " + name + " (" + error.message +
        "). The download link below always works as a fallback.";
      app.writing = false;
      refreshCard();
      return;
    }
  }
  $("card-note").textContent = "Copied. Flash " + binaryName + ", then eject the card before pulling it out.";
  app.writing = false;
  refreshCard();
}

$("pick-card").onclick = pickCard;
for (const id of ["w-board", "w-manifest", "w-screen", "w-fresh"]) {
  if ($(id)) $(id).onchange = refreshCard;
}
refreshCard();
$("write-card").onclick = writeCard;

boot();
