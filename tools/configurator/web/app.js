// Configurator UI: catalogue, live budget, presets, build API.
let catalog = null;
let state = {};
let pollTimer = null;

const $ = (id) => document.getElementById(id);
const fmt = (n) => Number(n).toLocaleString('en-US');
const signed = (n) => (n > 0 ? '+' : (n < 0 ? '-' : '+-')) + fmt(Math.abs(n));

function runningFlash() { return catalog.baseline.running_flash || catalog.baseline.flash; }
function priced(f) { return typeof f.flash === 'number' && f.flash > 0; }
function machineById(id) { return catalog.machines.find((m) => m.id === id); }

function renderMachines() {
  const sel = $('machine');
  sel.innerHTML = '';
  for (const m of catalog.machines) {
    const o = document.createElement('option');
    o.value = m.id;
    o.textContent = m.label + (m.supported ? '' : '  (not supported)');
    o.disabled = !m.supported;
    sel.appendChild(o);
  }
  sel.value = catalog.machines.find((m) => m.supported).id;
  sel.onchange = () => { renderNote(); renderBudget(); };
  renderNote();
}

function renderNote() {
  const m = machineById($('machine').value);
  $('machine-note').textContent = m.supported ? (m.bootloader_note || '') : (m.reason || '');
}

function renderGroups() {
  const host = $('groups');
  host.innerHTML = '';
  for (const group of catalog.groups) {
    const feats = catalog.features.filter((f) => f.group === group);
    if (!feats.length) continue;
    const box = document.createElement('div');
    box.className = 'group';
    const h = document.createElement('h2');
    h.dataset.group = group;
    h.textContent = group;
    box.appendChild(h);
    for (const f of feats) {
      const row = document.createElement('label');
      row.className = 'row';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.dataset.fid = f.id;
      if (f.buildable === false) {
        // it cannot be toggled, but it is still part of the build: keep its default state
        state[f.id] = f.on_by_default;
        cb.disabled = true;
        cb.title = f.build_failed || 'cannot be toggled on this board';
      }
      cb.checked = !!state[f.id];
      cb.onchange = () => { state[f.id] = cb.checked; renderBudget(); };
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
      sub.textContent = f.summary;
      text.appendChild(name);
      text.appendChild(sub);
      const cost = document.createElement('span');
      cost.className = 'cost' + (f.cost_source === 'measured' ? ' measured' : '');
      if (f.buildable === false) {
        cost.textContent = f.on_by_default ? 'fixed on' : 'not available';
        cost.title = f.build_failed || '';
      } else {
        cost.textContent = priced(f) ? signed(f.flash) + ' B' : 'measuring';
      }
      row.appendChild(cb);
      row.appendChild(text);
      row.appendChild(cost);
      box.appendChild(row);
    }
    host.appendChild(box);
  }
}

function refreshCounts() {
  const on = catalog.features.filter((f) => state[f.id]).length;
  $('countline').textContent = on + ' of ' + catalog.features.length + ' features selected';
  for (const group of catalog.groups) {
    const feats = catalog.features.filter((f) => f.group === group);
    const h = document.querySelector('.group h2[data-group="' + group + '"]');
    if (h) h.textContent = group + '  (' + feats.filter((f) => state[f.id]).length + '/' + feats.length + ')';
  }
}

function predicted() {
  const base = catalog.baseline;
  let flash = base.flash + (base.stamp_offset || 0);
  let ram = base.ram;
  for (const f of catalog.features) {
    if (state[f.id] === f.on_by_default) continue;
    const sign = state[f.id] ? 1 : -1;
    flash += sign * (f.flash || 0);
    ram += sign * (f.ram || 0);
  }
  const margin = (base.add_margin_per_feature || 0) *
    catalog.features.filter((f) => state[f.id] && !f.on_by_default).length;
  return { flash: flash + margin, ram: ram, margin: margin };
}

function renderBudget() {
  const m = machineById($('machine').value);
  const region = m.flash_region;
  const p = predicted();
  const used = Math.min(p.flash, region);
  const over = Math.max(0, p.flash - region);
  $('predicted').textContent = fmt(p.flash) + ' B';
  $('bar-used').style.width = (100 * used / region).toFixed(2) + '%';
  $('bar-over').style.width = (100 * over / region).toFixed(2) + '%';
  $('free').textContent = (p.flash > region ? 'over by ' + fmt(over) : fmt(region - p.flash) + ' B free');
  $('region').textContent = fmt(region) + ' B region';
  const diff = p.flash - runningFlash();
  const el = $('delta');
  const pct = Math.abs(100 * diff / runningFlash()).toFixed(1);
  if (diff === 0) { el.textContent = 'same size as the image you run now'; el.className = 'delta'; }
  else if (diff < 0) { el.textContent = fmt(-diff) + ' B smaller than what you run now (' + pct + '%)'; el.className = 'delta good'; }
  else { el.textContent = fmt(diff) + ' B larger than what you run now (' + pct + '%)'; el.className = 'delta bad'; }
  $('ramline').textContent = 'RAM ' + fmt(p.ram) + ' B of ' + fmt(m.ram_total) + ' B' +
    (p.margin ? '  (+' + fmt(p.margin) + ' B stacking margin)' : '');
  const warn = $('budget-warn');
  const bad = p.flash > region;
  warn.classList.toggle('hidden', !bad);
  if (bad) warn.textContent = 'Over budget by ' + fmt(over) + ' B. Turn something off before building.';
  $('build').disabled = bad || !catalog.build.toolchain_ready;
  refreshCounts();
}

function syncCheckboxes() {
  document.querySelectorAll('.row input').forEach((cb) => { cb.checked = !!state[cb.dataset.fid]; });
}

function applyPreset(name) {
  for (const b of document.querySelectorAll('.preset')) b.classList.remove('active');
  if (name === 'min') {
    for (const f of catalog.features) state[f.id] = false;
  } else if (name === 'now') {
    for (const f of catalog.features) state[f.id] = f.on_by_default;
  } else if (name === 'fit') {
    for (const f of catalog.features) state[f.id] = f.on_by_default;
    const region = machineById($('machine').value).flash_region;
    const candidates = catalog.features.filter((f) => !state[f.id] && priced(f) && f.buildable !== false && f.flash > 0)
      .sort((a, b) => a.flash - b.flash);
    for (const f of candidates) {
      const blocked = (f.conflicts || []).some((other) => state[other]);
      if (blocked) continue;
      state[f.id] = true;
      if (predicted().flash > region) state[f.id] = false;
    }
  }
  syncCheckboxes();
  renderBudget();
  const btn = document.querySelector('.preset[data-preset="' + name + '"]');
  if (btn) btn.classList.add('active');
}

function selection() {
  const on = [], off = [];
  for (const f of catalog.features) (state[f.id] ? on : off).push(f.id);
  return { machine: $('machine').value, on: on, off: off };
}

async function startBuild() {
  $('result').classList.add('hidden');
  $('status').classList.remove('hidden');
  $('phase').textContent = 'submitting';
  $('log').textContent = '';
  const res = await fetch('/api/build', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(selection()) });
  const data = await res.json();
  if (!res.ok) { $('phase').textContent = data.error || 'rejected'; return; }
  $('jobid').textContent = data.id;
  poll(data.id);
}

function poll(id) {
  if (pollTimer) clearTimeout(pollTimer);
  fetch('/api/build/' + id).then((r) => r.json()).then((j) => {
    $('phase').textContent = j.phase || j.status;
    if (j.log) { $('log').textContent = j.log.join('\n'); $('log').scrollTop = $('log').scrollHeight; }
    if (j.status === 'succeeded') { showResult(j); return; }
    if (j.status === 'failed') { $('phase').textContent = 'failed: ' + (j.error || ''); return; }
    pollTimer = setTimeout(() => poll(id), 1200);
  }).catch(() => { pollTimer = setTimeout(() => poll(id), 2500); });
}

function showResult(j) {
  $('result').classList.remove('hidden');
  const r = j.result;
  const pred = j.predicted.flash;
  $('r-flash').textContent = fmt(r.flash_used) + ' / ' + fmt(r.flash_region) + ' B (' + r.flash_percent + '%)';
  const diff = r.flash_used - runningFlash();
  $('r-delta').textContent = (diff === 0 ? 'same size' : (diff < 0 ? fmt(-diff) + ' B smaller' : fmt(diff) + ' B larger'));
  $('r-pred').textContent = fmt(pred) + ' B';
  const err = r.flash_used - pred;
  $('r-err').textContent = (err === 0 ? 'exact' : signed(err) + ' B');
  $('r-ram').textContent = fmt(r.ram_used) + ' / ' + fmt(r.ram_total) + ' B';
  $('r-size').textContent = fmt(r.file_size) + ' B';
  $('r-sha').textContent = r.sha256;
  $('download').href = '/api/build/' + j.id + '/firmware.bin';
  $('manifest').href = '/api/build/' + j.id + '/manifest.json';

  const d = j.diff || { added: [], removed: [] };
  const parts = [];
  if (d.removed && d.removed.length) parts.push('removed: ' + d.removed.join(', '));
  if (d.added && d.added.length) parts.push('added: ' + d.added.join(', '));
  $('r-changes').textContent = parts.length ? parts.join('  |  ') : 'none - identical feature set to what you run';
  const w = j.warnings && j.warnings.length ? j.warnings.join(' ') : '';
  $('r-warn').textContent = w;
  $('r-warn').classList.toggle('hidden', !w);
}

async function boot() {
  catalog = await (await fetch('/api/catalog')).json();
  for (const f of catalog.features) state[f.id] = f.on_by_default;
  renderMachines();
  renderGroups();
  renderBudget();
  const cal = catalog.calibration || {};
  $('calib').textContent = cal.date ? ('measured ' + cal.date) : '';
  $('build').onclick = startBuild;
  document.querySelectorAll('.preset').forEach((el) => {
    el.dataset.preset = el.id.replace('preset-', '');
    el.onclick = () => applyPreset(el.dataset.preset);
  });
  const b = catalog.build;
  if (!b.toolchain_ready) {
    $('banner').classList.remove('hidden');
    $('banner').textContent = 'Build tree not ready: ' + b.hint;
  }
}

boot();
