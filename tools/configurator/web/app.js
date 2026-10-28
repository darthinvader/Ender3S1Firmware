// Ender 3 S1 firmware configurator - UI.
// One state object, explicit render steps, and a build is only "fresh" while the
// selection still matches the signature it was built from.

const app = {
  catalog: null,
  state: {},
  filter: '',
  collapsed: {},
  showUnavailable: false,
  devices: [],
  versions: null,
  sourceId: "pinned",
  sourceInspect: null,
  build: null,
  busy: false,
  pollTimer: null,
};

const $ = (id) => document.getElementById(id);
const fmt = (n) => Number(n).toLocaleString('en-US');
const signed = (n) => (n > 0 ? '+' : (n < 0 ? '-' : '+-')) + fmt(Math.abs(n));
const runningFlash = () => app.catalog.baseline.running_flash || app.catalog.baseline.flash;
const machineById = (id) => app.catalog.machines.find((m) => m.id === id);
const machine = () => $('machine').value;
const featureById = (id) => app.catalog.features.find((f) => f.id === id);
const usable = (f) => f.buildable !== false;
const priced = (f) => typeof f.flash === 'number' && f.flash > 0;

function toast(message, kind) {
  const el = $('toast');
  el.textContent = message;
  el.className = 'toast';
  if (kind === 'info') { el.style.background = '#132033'; el.style.borderColor = 'var(--accent)'; el.style.color = '#d6e4ff'; }
  else { el.style.background = '#2a1414'; el.style.borderColor = 'var(--bad)'; el.style.color = '#ffd9d6'; }
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add('hidden'), 5000);
}

// ------------------------------------------------------------- firmware source
const isPinned = () => app.sourceId === "pinned";
function currentVersion() {
  return (app.versions || []).find((v) => v.id === app.sourceId) || null;
}

async function loadVersions(refresh) {
  try {
    const res = await fetch("/api/versions" + (refresh ? "?refresh=1" : ""));
    app.versions = (await res.json()).versions || [];
  } catch (e) {
    app.versions = [];
    toast("Could not read the version list: " + e.message);
  }
  renderSources();
}

function renderSources() {
  const sel = $("source");
  const keep = app.sourceId;
  sel.innerHTML = "";
  for (const v of app.versions) {
    const o = document.createElement("option");
    const bits = [v.label];
    if (v.sha) bits.push(v.sha);
    if (v.date) bits.push(v.date);
    if (v.kind !== "pinned" && !v.fetched) bits.push("not downloaded");
    o.value = v.id;
    o.textContent = bits.join("  -  ");
    sel.appendChild(o);
  }
  if (![...sel.options].some((o) => o.value === keep)) app.sourceId = "pinned";
  sel.value = app.sourceId;
  sel.onchange = () => {
    app.sourceId = sel.value;
    app.sourceInspect = null;
    renderSources();
    renderBudget();
    inspectSource();
  };
  $("source-fetch").disabled = isPinned() || !!(currentVersion() || {}).fetched;
  renderSourceNote();
}

function renderSourceNote() {
  const v = currentVersion();
  const note = $("source-note");
  const extra = $("source-extra");
  extra.classList.add("hidden");
  $("source-fetch").disabled = isPinned() || !!(v || {}).fetched;
  if (!v || isPinned()) {
    note.textContent = "The commit this repository was built from: measured costs, presets and the write panel all apply to it.";
    return;
  }
  const bits = [];
  bits.push(v.kind === "tag" ? "release " + v.ref : "branch " + v.ref);
  if (v.date) bits.push("published " + v.date);
  bits.push("commit " + v.sha);
  bits.push(v.fetched ? "downloaded" : "not downloaded yet - the size is only known after compiling");
  note.textContent = bits.join("  -  ");
  if (v.fetched && app.sourceInspect) renderInspect();
}

function renderInspect() {
  const i = app.sourceInspect;
  if (!i) return;
  $("source-extra").classList.remove("hidden");
  const missing = (i.features_missing || []).length;
  const extra = i.new_define_count;
  $("source-compat").textContent =
    i.features_present + " of " + i.features_total + " catalogue features exist in this version" +
    (missing ? "; " + missing + " will be skipped" : "") +
    (extra ? ".  It has " + extra + (extra === 1 ? " option" : " options") + " the pinned tree does not." : ".");
  const det = $("source-new");
  det.classList.toggle("hidden", !i.new_define_count);
  det.querySelector("summary").textContent = i.new_define_count + " option(s) this version has that your build does not";
  const list = $("source-new-list");
  list.innerHTML = "";
  for (const d of (i.new_defines || []).slice(0, 40)) {
    const li = document.createElement("li");
    const code = document.createElement("code");
    code.textContent = d.macro;
    li.appendChild(code);
    if (d.note) li.appendChild(document.createTextNode("  " + d.note));
    list.appendChild(li);
  }
}

async function inspectSource() {
  if (isPinned()) return;
  try {
    const res = await fetch("/api/versions/inspect?id=" + encodeURIComponent(app.sourceId));
    if (!res.ok) return;
    app.sourceInspect = await res.json();
    renderInspect();
  } catch (e) { /* informational only */ }
}

async function fetchVersion() {
  const v = currentVersion();
  if (!v || isPinned()) return;
  app.busy = true;
  $("source-fetch").disabled = true;
  $("source-note").textContent = "downloading " + v.label + " ...";
  $("status").classList.remove("hidden");
  $("phase").textContent = "downloading";
  $("log").textContent = "";
  try {
    const res = await fetch("/api/versions/fetch", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: v.id })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
    if (data.status === "already") {
      app.busy = false;
      await loadVersions(false);
      renderBudget();
      return;
    }
    $("jobid").textContent = data.id;
    poll(data.id);
  } catch (e) {
    app.busy = false;
    toast("Download failed: " + e.message);
    renderSources();
  }
}

// ---------------------------------------------------------------- selection
function signature() {
  const on = [];
  for (const f of app.catalog.features) if (app.state[f.id]) on.push(f.id);
  // the screen package is copied onto the card, not compiled: it is deliberately not part of this
  return [machine(), app.sourceId, on.join(',')].join('|');
}
function buildFresh() { return !!app.build && app.build.signature === signature(); }

function predicted() {
  const base = app.catalog.baseline;
  let flash = base.flash + (base.stamp_offset || 0);
  let ram = base.ram;
  for (const f of app.catalog.features) {
    if (app.state[f.id] === f.on_by_default) continue;
    const sign = app.state[f.id] ? 1 : -1;
    flash += sign * (f.flash || 0);
    ram += sign * (f.ram || 0);
  }
  const margin = (base.add_margin_per_feature || 0) *
    app.catalog.features.filter((f) => app.state[f.id] && !f.on_by_default).length;
  return { flash: flash + margin, ram: ram, margin: margin };
}

function renderUnmeasured(m) {
  const v = currentVersion() || { label: app.sourceId };
  $('predicted').textContent = 'not measured';
  $('bar').classList.remove('over');
  $('bar-used').style.width = '0%';
  $('bar-over').style.width = '0%';
  $('free').textContent = 'size known after compiling';
  $('region').textContent = fmt(m.flash_region) + ' B region';
  const el = $('delta');
  el.textContent = 'Costs were measured on the pinned tree, so no prediction is claimed for ' + (v.label || 'this version') + '.';
  el.className = 'delta';
  $('ramline').textContent = 'RAM unknown until it links';
  const usableCount = app.catalog.features.filter(usable);
  const onCount = usableCount.filter((f) => app.state[f.id]).length;
  $('countline').textContent = onCount + ' of ' + usableCount.length + ' usable features on - the build reports the real size';
  $('budget-warn').classList.add('hidden');

  const build = $('build');
  build.classList.remove('over');
  build.textContent = 'Build this version';
  build.disabled = app.busy || !app.catalog.build.toolchain_ready;
  $('build-note').textContent = (v.fetched
    ? 'Builds ' + v.label + ' at ' + v.sha + '. Features this version lacks are skipped, and the result is the truth about its size.'
    : 'Download this version first.');
  build.disabled = build.disabled || !v.fetched;
  updateWriteState();
}

function applyRequires(fid, value) {
  const f = featureById(fid);
  if (!f) return;
  if (value) {
    for (const req of (f.requires || [])) {
      if (!app.state[req]) { app.state[req] = true; applyRequires(req, true); }
    }
  } else {
    for (const other of app.catalog.features) {
      if (app.state[other.id] && (other.requires || []).indexOf(fid) !== -1) {
        app.state[other.id] = false;
        applyRequires(other.id, false);
      }
    }
  }
}

function resolveConflicts(fid, value) {
  const f = featureById(fid);
  if (!f || !value) return;
  for (const other of (f.conflicts || [])) if (app.state[other]) app.state[other] = false;
}

// ------------------------------------------------------------------ rendering
function renderMachines() {
  const sel = $('machine');
  const previous = sel.value;
  sel.innerHTML = '';
  for (const m of app.catalog.machines) {
    if (!app.showUnavailable && !m.supported) continue;
    const o = document.createElement('option');
    o.value = m.id;
    o.textContent = m.label + (m.supported ? '' : '  (not supported)');
    o.disabled = !m.supported;
    sel.appendChild(o);
  }
  const supported = app.catalog.machines.filter((m) => m.supported);
  sel.value = (previous && supported.some((m) => m.id === previous)) ? previous : supported[0].id;
}

function renderScreen() {
  const sc = app.catalog.screen;
  const os = $('screen-os');
  const assets = $('screen-assets');
  const keepOs = os.value, keepAssets = assets.value;
  os.innerHTML = '';
  assets.innerHTML = '';
  for (const e of sc.os) {
    if (!app.showUnavailable && !e.bundled) continue;
    const o = document.createElement('option');
    o.value = e.id;
    o.textContent = e.label + '  (' + Math.round(e.bytes / 1024) + ' KiB' +
      (e.verified_on_this_panel ? ', verified here' : ', not verified here') + ')';
    o.disabled = !e.bundled;
    os.appendChild(o);
  }
  for (const e of sc.assets) {
    if (!app.showUnavailable && !(e.bundled && e.pairs_with === 'custom')) continue;
    const o = document.createElement('option');
    o.value = e.id;
    o.textContent = e.label + '  (' + Math.round(e.bytes / 1024) + ' KiB' +
      (e.pairs_with === 'custom' ? ', pairs with this build' : ', ' + e.pairs_with + ' firmware only') + ')';
    o.disabled = !(e.bundled && e.pairs_with === 'custom');
    assets.appendChild(o);
  }
  const firstOk = (list, test) => (list.filter(test)[0] || list[0] || {}).id;
  os.value = [...os.options].some((o) => o.value === keepOs) ? keepOs : firstOk(sc.os, (e) => e.bundled);
  assets.value = [...assets.options].some((o) => o.value === keepAssets) ? keepAssets
    : firstOk(sc.assets, (e) => e.bundled && e.pairs_with === 'custom');
  renderScreenNote();
}

function renderScreenNote() {
  const sc = app.catalog.screen;
  const o = sc.os.find((x) => x.id === $('screen-os').value);
  const a = sc.assets.find((x) => x.id === $('screen-assets').value);
  $('screen-note').textContent = [o ? o.note : '', a ? a.note : ''].filter(Boolean).join(' ');
}

function matches(f) {
  const q = app.filter.trim().toLowerCase();
  if (!q) return true;
  return (f.label + ' ' + f.id + ' ' + (f.summary || '')).toLowerCase().indexOf(q) !== -1;
}

function renderGroups() {
  const host = $('groups');
  const scroll = window.scrollY;
  host.innerHTML = '';
  let hidden = 0;
  let shown = 0;
  for (const group of app.catalog.groups) {
    const all = app.catalog.features.filter((f) => f.group === group);
    const feats = all.filter((f) => (app.showUnavailable || usable(f)) && matches(f));
    hidden += all.filter((f) => !app.showUnavailable && !usable(f)).length;
    if (!feats.length) continue;
    shown += feats.length;

    const box = document.createElement('div');
    box.className = 'group' + (app.collapsed[group] ? ' collapsed' : '');
    const h = document.createElement('h2');
    h.dataset.group = group;
    h.textContent = group + '  (' + feats.filter((f) => app.state[f.id]).length + '/' + feats.length + ')';
    h.onclick = () => {
      app.collapsed[group] = !app.collapsed[group];
      box.classList.toggle('collapsed');
    };
    box.appendChild(h);

    for (const f of feats) {
      const row = document.createElement('label');
      row.className = 'row' + (usable(f) ? '' : ' unusable') +
        (app.state[f.id] !== f.on_by_default ? ' changed' : '');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.dataset.fid = f.id;
      if (!usable(f)) {
        app.state[f.id] = f.on_by_default;
        cb.disabled = true;
        cb.title = f.build_failed || 'cannot be toggled here';
      }
      cb.checked = !!app.state[f.id];
      cb.onchange = () => {
        app.state[f.id] = cb.checked;
        applyRequires(f.id, cb.checked);
        resolveConflicts(f.id, cb.checked);
        syncCheckboxes();
        renderBudget();
      };
      const text = document.createElement('div');
      const name = document.createElement('div');
      name.className = 'name';
      name.textContent = f.label;
      if (f.risk === 'high') {
        const r = document.createElement('span');
        r.className = 'risk';
        r.textContent = 'careful';
        name.appendChild(r);
      }
      const sub = document.createElement('div');
      sub.className = 'sub';
      sub.textContent = usable(f) ? f.summary : (f.summary + '  -  ' + (f.build_failed || 'not usable here'));
      text.appendChild(name);
      text.appendChild(sub);
      const cost = document.createElement('span');
      cost.className = 'cost' + (f.cost_source === 'measured' ? ' measured' : '');
      if (!usable(f)) {
        cost.textContent = f.on_by_default ? 'fixed on' : 'unavailable';
        cost.title = f.build_failed || '';
      } else if (f.cost_source === 'measured') {
        cost.textContent = priced(f) ? signed(f.flash) + ' B' : '~0 B';
        cost.title = priced(f) ? '' : 'no measurable cost: inside the linker alignment';
      } else {
        cost.textContent = 'measuring';
      }
      row.appendChild(cb);
      row.appendChild(text);
      row.appendChild(cost);
      box.appendChild(row);
    }
    host.appendChild(box);
  }
  if (!shown) {
    const p = document.createElement('p');
    p.className = 'hint';
    p.textContent = 'Nothing matches "' + app.filter + '".';
    host.appendChild(p);
  } else if (!app.showUnavailable && hidden > 0) {
    const p = document.createElement('p');
    p.className = 'hint';
    p.textContent = hidden + ' option(s) hidden: they cannot be toggled on this board. Tick the box in the header to see them with the reason for each.';
    host.appendChild(p);
  }
  $('filter-count').textContent = shown + ' shown';
  window.scrollTo(0, scroll);
}

function syncCheckboxes() {
  document.querySelectorAll('.row input').forEach((cb) => {
    cb.checked = !!app.state[cb.dataset.fid];
    const f = featureById(cb.dataset.fid);
    if (f) cb.closest('.row').classList.toggle('changed', app.state[f.id] !== f.on_by_default);
  });
}

function renderBudget() {
  const m = machineById(machine());
  const region = m.flash_region;
  if (!isPinned()) { renderUnmeasured(m); return; }
  const p = predicted();
  const over = Math.max(0, p.flash - region);
  const used = Math.min(p.flash, region);

  $('predicted').textContent = fmt(p.flash) + ' B';
  $('bar').classList.toggle('over', over > 0);
  $('bar-used').style.width = (100 * used / region).toFixed(2) + '%';
  $('bar-over').style.width = (100 * over / region).toFixed(2) + '%';
  $('free').textContent = over ? 'over by ' + fmt(over) : fmt(region - p.flash) + ' B free';
  $('region').textContent = fmt(region) + ' B region';

  const diff = p.flash - runningFlash();
  const el = $('delta');
  const pct = Math.abs(100 * diff / runningFlash()).toFixed(1);
  if (diff === 0) { el.textContent = 'same size as the image you run now'; el.className = 'delta'; }
  else if (diff < 0) { el.textContent = fmt(-diff) + ' B smaller than what you run now (' + pct + '%)'; el.className = 'delta good'; }
  else { el.textContent = fmt(diff) + ' B larger than what you run now (' + pct + '%)'; el.className = 'delta bad'; }

  $('ramline').textContent = 'RAM ' + fmt(p.ram) + ' B of ' + fmt(m.ram_total) + ' B' +
    (p.margin ? '  (+' + fmt(p.margin) + ' B margin)' : '');

  const usableCount = app.catalog.features.filter(usable);
  const onCount = usableCount.filter((f) => app.state[f.id]).length;
  const changed = app.catalog.features.filter((f) => app.state[f.id] !== f.on_by_default).length;
  $('countline').textContent = onCount + ' of ' + usableCount.length + ' usable features on' +
    (changed ? '  -  ' + changed + ' changed from what you run' : '');

  const warn = $('budget-warn');
  warn.classList.toggle('hidden', !over);
  if (over) warn.textContent = 'This image is ' + fmt(over) + ' B larger than the flash region this preset assumes.';

  const build = $('build');
  build.classList.toggle('over', over > 0);
  build.textContent = over > 0 ? 'Build anyway (' + fmt(over) + ' B over)' : 'Build firmware';
  build.disabled = app.busy || !app.catalog.build.toolchain_ready;
  $('build-note').textContent = over > 0
    ? ('Over budget: ' + fmt(p.flash) + ' B against ' + fmt(region) + ' B. The link will fail unless the board has more flash.')
    : '';

  const busy = app.busy;
  $('screen-os').disabled = busy;
  $('screen-assets').disabled = busy;
  updateWriteState();
}

// -------------------------------------------------------------------- device
async function loadDevices() {
  try {
    const res = await fetch('/api/devices');
    const data = await res.json();
    app.devices = data.devices || [];
    const sel = $('device');
    const previous = sel.value;
    sel.innerHTML = '';
    for (const d of app.devices) {
      const o = document.createElement('option');
      o.value = d.path;
      o.textContent = d.path + '   ' + d.size_human + '   ' + d.model + ' (' + d.transport + ')' +
        (d.usable ? '' : '  - ' + d.why_not);
      o.disabled = !d.usable;
      sel.appendChild(o);
    }
    const ok = app.devices.filter((d) => d.usable);
    if (ok.length) sel.value = ok.some((d) => d.path === previous) ? previous : ok[0].path;
    $('device-note').textContent = ok.length
      ? (data.sudo ? '' : 'Passwordless sudo is not available to the service, so writing is disabled.')
      : 'No writable card found. Insert a reader and press re-scan; internal disks are never offered.';
  } catch (e) {
    app.devices = [];
    $('device').innerHTML = '';
    $('device-note').textContent = 'Could not list devices: ' + e.message;
  }
  updateWriteState();
}

function selectedDevice() { return app.devices.find((d) => d.path === $('device').value); }

function payloadBytes() {
  const sc = app.catalog.screen;
  const o = sc.os.find((x) => x.id === $('screen-os').value);
  const a = sc.assets.find((x) => x.id === $('screen-assets').value);
  let n = 0;
  if ($('part-board').checked && app.build) n += app.build.file_size || 0;
  if ($('part-screen').checked) n += (o ? o.bytes : 0) + (a ? a.bytes : 0);
  return n;
}

function updateWriteState() {
  const d = selectedDevice();
  const board = $('part-board').checked;
  const screen = $('part-screen').checked;
  let note = '';
  let ok = !!d && d.usable && (board || screen);

  if (board && !app.build) { ok = false; note = 'Build the firmware first: the mainboard part needs an image.'; }
  else if (board && !buildFresh()) { ok = false; note = 'The selection changed since that build. Rebuild before writing, so the card matches what you see.'; }
  else if (!board && !screen) { ok = false; note = 'Pick at least one thing to write.'; }
  if (ok && d && payloadBytes() > d.size * 0.97) {
    ok = false;
    note = 'The payload (' + fmt(payloadBytes()) + ' B) does not fit on ' + d.size_human + '.';
  }
  $('write').disabled = !ok || app.busy;
  $('write-note').textContent = note;
}

// ------------------------------------------------------------------- presets
function applyPreset(name) {
  for (const b of document.querySelectorAll('.preset')) b.classList.remove('active');
  const btn = document.querySelector('.preset[data-preset="' + name + '"]');
  if (btn) btn.classList.add('active');

  if (name === 'min') {
    for (const f of app.catalog.features) app.state[f.id] = usable(f) ? false : f.on_by_default;
  } else if (name === 'now') {
    for (const f of app.catalog.features) app.state[f.id] = f.on_by_default;
  } else if (name === 'fit') {
    for (const f of app.catalog.features) app.state[f.id] = f.on_by_default;
    const region = machineById(machine()).flash_region;
    const candidates = app.catalog.features
      .filter((f) => !app.state[f.id] && usable(f) && priced(f))
      .sort((a, b) => a.flash - b.flash);
    for (const f of candidates) {
      if ((f.conflicts || []).some((other) => app.state[other])) continue;
      app.state[f.id] = true;
      if (predicted().flash > region) app.state[f.id] = false;
    }
  }
  syncCheckboxes();
  renderBudget();
}

// --------------------------------------------------------------------- build
async function startBuild() {
  const pinned = isPinned();
  const p = predicted();
  const region = machineById(machine()).flash_region;
  let allowOverflow = false;
  if (pinned && p.flash > region) {
    allowOverflow = await modal(
      'This image will not fit on this board',
      '<p>Prediction: <b>' + fmt(p.flash) + ' B</b> against the application region of <b>' + fmt(region) +
      ' B</b> - <b>' + fmt(p.flash - region) + ' B too large</b>.</p>' +
      '<p>On an STM32F103RCT6 with the 28 KiB bootloader the link stops at ' + fmt(region) + ' B. The build is still allowed because:</p>' +
      '<ul><li>your board may have more flash than this preset assumes;</li>' +
      '<li>you may be checking what a configuration would need before trimming.</li></ul>' +
      '<p>The compiler is the authority here, not this estimate.</p>',
      'Build anyway');
    if (!allowOverflow) return;
  }

  const sc = app.catalog.screen;
  const osEntry = sc.os.find((x) => x.id === $('screen-os').value);
  const packEntry = sc.assets.find((x) => x.id === $('screen-assets').value);

  app.busy = true;
  renderBudget();
  $('result').classList.add('hidden');
  $('write-result').classList.add('hidden');
  $('status').classList.remove('hidden');
  $('phase').textContent = 'submitting';
  $('log').textContent = '';
  $('status').scrollIntoView({ block: 'nearest', behavior: 'smooth' });

  const payload = { machine: machine(), on: [], off: [], allow_overflow: allowOverflow,
    source: app.sourceId,
    screen_os: $('screen-os').value, screen_assets: $('screen-assets').value };
  for (const f of app.catalog.features) (app.state[f.id] ? payload.on : payload.off).push(f.id);

  try {
    const res = await fetch('/api/build', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    app.pending = { id: data.id, signature: signature(), screen_os: payload.screen_os, screen_assets: payload.screen_assets };
    $('jobid').textContent = data.id;
    poll(data.id);
  } catch (e) {
    app.busy = false;
    renderBudget();
    $('phase').textContent = 'failed to submit';
    toast('Could not start the build: ' + e.message);
  }
}

function poll(id) {
  clearTimeout(app.pollTimer);
  const finish = () => { app.busy = false; renderBudget(); };
  fetch('/api/build/' + id).then((r) => r.json()).then((j) => {
    $('phase').textContent = j.phase || j.status;
    if (j.log) { $('log').textContent = j.log.join('\n'); $('log').scrollTop = $('log').scrollHeight; }
    if (j.status === 'succeeded') {
      if (j.kind === 'write') { finish(); showWriteResult(j); }
      else if (j.kind === 'fetch') { finish(); showFetchedVersion(j); }
      else { finish(); showResult(j); }
      return;
    }
    if (j.status === 'failed') {
      finish();
      $('phase').textContent = 'failed';
      toast(j.error || 'the build failed');
      return;
    }
    app.pollTimer = setTimeout(() => poll(id), 1200);
  }).catch(() => { app.pollTimer = setTimeout(() => poll(id), 2500); });
}

function updateBundleLink(id) {
  const base = '/api/build/' + (id || (app.build && app.build.id) || '') + '/bundle.zip';
  if (!id && !(app.build && app.build.id)) return;
  $('bundle').href = base + '?os=' + encodeURIComponent($('screen-os').value) +
    '&assets=' + encodeURIComponent($('screen-assets').value);
}

async function showFetchedVersion(j) {
  const r = j.result || {};
  const info = r.source || {};
  toast((info.label || info.ref || 'version') + ' downloaded at ' + (info.sha || '?'), 'info');
  await loadVersions(false);
  if (info.id) app.sourceId = info.id;
  renderSources();
  await inspectSource();
  renderBudget();
}

function showResult(j) {
  const r = j.result;
  app.build = { id: j.id, signature: app.pending ? app.pending.signature : signature(),
    screen_os: j.screen_os, screen_assets: j.screen_assets, file_size: r.file_size };
  $('result').classList.remove('hidden');
  $('r-flash').textContent = fmt(r.flash_used) + ' / ' + fmt(r.flash_region) + ' B (' + r.flash_percent + '%)';
  const diff = r.flash_used - runningFlash();
  $('r-delta').textContent = diff === 0 ? 'same size' : (diff < 0 ? fmt(-diff) + ' B smaller' : fmt(diff) + ' B larger');
  if (j.predicted && j.predicted.flash !== null && j.predicted.flash !== undefined) {
    $('r-pred').textContent = fmt(j.predicted.flash) + ' B';
    const err = r.flash_used - j.predicted.flash;
    $('r-err').textContent = err === 0 ? 'exact' : signed(err) + ' B';
  } else {
    $('r-pred').textContent = 'not measured for this version';
    $('r-err').textContent = '-';
  }
  $('r-ram').textContent = fmt(r.ram_used) + ' / ' + fmt(r.ram_total) + ' B';
  $('r-size').textContent = fmt(r.file_size) + ' B';
  $('r-sha').textContent = r.sha256;

  const sc = app.catalog.screen;
  const o = sc.os.find((x) => x.id === j.screen_os);
  const a = sc.assets.find((x) => x.id === j.screen_assets);
  $('r-screen').textContent = (o ? o.label : j.screen_os) + '  +  ' + (a ? a.label : j.screen_assets);
  $('r-bundle').textContent = 'firmware.bin + screen/firmware.zlib + screen/private (' +
    (a ? a.files : 0) + ' files) + FLASH-THIS.txt';

  const d = j.diff || { added: [], removed: [] };
  const parts = [];
  if (d.removed && d.removed.length) parts.push('off: ' + d.removed.join(', '));
  if (d.added && d.added.length) parts.push('on: ' + d.added.join(', '));
  for (const x of (j.auto_added || [])) parts.push('auto +' + x.feature + ' (needed by ' + x.because + ')');
  for (const x of (j.auto_removed || [])) parts.push('auto -' + x.feature + ' (needed by ' + x.because + ')');
  $('r-changes').textContent = parts.length ? parts.join('   |   ') : 'none - identical to what you run';

  const w = (j.warnings || []).join(' ');
  $('r-warn').textContent = w;
  $('r-warn').classList.toggle('hidden', !w);

  $('status').classList.add('hidden');
  $('download').href = '/api/build/' + j.id + '/firmware.bin';
  $('manifest').href = '/api/build/' + j.id + '/manifest.json';
  updateBundleLink(j.id);
  $('result').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  updateWriteState();
}

// --------------------------------------------------------------------- write
async function doWrite() {
  const d = selectedDevice();
  const parts = [];
  if ($('part-board').checked) parts.push('board');
  if ($('part-screen').checked) parts.push('screen');
  const sc = app.catalog.screen;
  const osId = $('screen-os').value;
  const packId = $('screen-assets').value;
  const osEntry = sc.os.find((x) => x.id === osId);
  const packEntry = sc.assets.find((x) => x.id === packId);

  const what = [];
  if (parts.indexOf('board') !== -1) what.push('the mainboard firmware from build ' + app.build.id);
  if (parts.indexOf('screen') !== -1) what.push('screen OS: ' + (osEntry ? osEntry.label : '?'));
  if (parts.indexOf('screen') !== -1) what.push('screen assets: ' + (packEntry ? packEntry.label : '?'));

  const ok = await modal(
    'Erase ' + d.path + ' and write to it?',
    '<p><b>' + d.path + '</b> - ' + d.size_human + ', ' + d.model + ' (' + d.transport + ')</p>' +
    (d.mounted.length ? '<p>Mounted at <span class="mono">' + d.mounted.join(', ') + '</span>; it will be unmounted first.</p>' : '') +
    '<p>Everything on it is erased. This writes:</p><ul>' + what.map((w) => '<li>' + w + '</li>').join('') + '</ul>' +
    '<p>Formatted MBR + FAT32 with 4096-byte clusters, which is what the Creality bootloader needs.</p>',
    'Erase and write');
  if (!ok) return;

  app.busy = true;
  updateWriteState();
  $('write-result').classList.add('hidden');
  $('status').classList.remove('hidden');
  $('phase').textContent = 'queued';
  $('log').textContent = '';
  try {
    const res = await fetch('/api/write', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device: d.path, parts: parts, build_id: app.build ? app.build.id : '',
        screen_os: osId, screen_assets: packId })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    $('jobid').textContent = data.id;
    poll(data.id);
  } catch (e) {
    app.busy = false;
    updateWriteState();
    $('phase').textContent = 'refused';
    toast('Write refused: ' + e.message);
  }
}

function showWriteResult(j) {
  $('write-result').classList.remove('hidden');
  const r = j.result || {};
  const bits = (r.written || []).map((w) => w.what + (w.file ? ' (' + w.file + ')' : ' (' + w.files + ' files)'));
  $('w-summary').textContent = r.device + ': ' + (bits.join(', ') || 'nothing written');
  $('w-next').textContent = 'Power the printer off. Mainboard: card in the front slot, power on, wait up to 60 s ' +
    '(nothing appears on screen), then verify with M115 at 250000 baud. Screen: card in the panel microSD with the ' +
    'front cover off; the panel flashes blue/orange for about a minute, then holds the logo ~30 s on first boot.';
  $('write-result').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

// --------------------------------------------------------------------- modal
function modal(title, bodyHtml, okLabel) {
  return new Promise((resolve) => {
    $('modal-title').textContent = title;
    $('modal-body').innerHTML = bodyHtml;
    $('modal-ok').textContent = okLabel || 'Continue';
    $('modal').classList.remove('hidden');

    const previous = document.activeElement;
    const close = (value) => {
      $('modal').classList.add('hidden');
      document.removeEventListener('keydown', onKey);
      $('modal-ok').onclick = null;
      $('modal-cancel').onclick = null;
      if (previous && previous.focus) previous.focus();
      resolve(value);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); close(false); }
      else if (e.key === 'Enter') { e.preventDefault(); close(true); }
    };
    document.addEventListener('keydown', onKey);
    $('modal-ok').onclick = () => close(true);
    $('modal-cancel').onclick = () => close(false);
    $('modal-ok').focus();
  });
}

// ---------------------------------------------------------------------- boot
function markDirty() {
  renderBudget();
  $('write-result').classList.add('hidden');
}

async function boot() {
  try {
    app.catalog = await (await fetch('/api/catalog')).json();
  } catch (e) {
    $('banner').classList.remove('hidden');
    $('banner').textContent = 'The build service is not answering. Start it with: python3 tools/configurator/server.py';
    return;
  }
  for (const f of app.catalog.features) app.state[f.id] = f.on_by_default;

  renderMachines();
  renderScreen();
  renderGroups();
  renderBudget();

  $('machine').onchange = () => { renderBudget(); };
  $('screen-os').onchange = () => { renderScreenNote(); updateBundleLink(); };
  $('screen-assets').onchange = () => { renderScreenNote(); updateBundleLink(); };
  $('build').onclick = startBuild;
  $('write').onclick = doWrite;
  $('refresh-devices').onclick = loadDevices;
  $('source-fetch').onclick = fetchVersion;
  $('source-refresh').onclick = () => loadVersions(true);
  $('part-board').onchange = updateWriteState;
  $('part-screen').onchange = updateWriteState;
  $('filter').oninput = (e) => { app.filter = e.target.value; renderGroups(); };
  $('show-log').onclick = () => {
    const st = $('status');
    st.classList.toggle('hidden');
    $('show-log').textContent = st.classList.contains('hidden') ? 'show build log' : 'hide build log';
  };
  $('show-unavailable').onchange = (e) => {
    app.showUnavailable = e.target.checked;
    renderMachines();
    renderScreen();
    renderGroups();
    renderBudget();
  };
  document.querySelectorAll('.preset').forEach((el) => { el.onclick = () => applyPreset(el.dataset.preset); });

  const cal = app.catalog.calibration || {};
  const calibEl = $('calib');
  if (calibEl) calibEl.textContent = cal.date ? ('measured ' + cal.date) : '';

  if (!app.catalog.build.toolchain_ready) {
    $('banner').classList.remove('hidden');
    $('banner').textContent = 'Build tree not ready: ' + app.catalog.build.hint;
  }
  await loadVersions(false);
  await loadDevices();
}

boot();
