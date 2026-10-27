// Configurator UI: fetch the catalogue, keep a live budget, drive the build API.
let catalog = null;
let state = {};
let pollTimer = null;

const $ = (id) => document.getElementById(id);
const fmt = (n) => n.toLocaleString('en-US');

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
  const first = catalog.machines.find((m) => m.supported);
  sel.value = first.id;
  sel.onchange = () => { renderNote(); renderBudget(); };
  renderNote();
}

function renderNote() {
  const m = machineById($('machine').value);
  $('machine-note').textContent = m.supported
    ? (m.bootloader_note || '')
    : (m.reason || '');
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
    h.textContent = group;
    box.appendChild(h);
    for (const f of feats) {
      const row = document.createElement('label');
      row.className = 'row';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = state[f.id];
      cb.onchange = () => { state[f.id] = cb.checked; renderBudget(); };
      const text = document.createElement('div');
      const name = document.createElement('div');
      name.className = 'name';
      name.textContent = f.label;
      const sub = document.createElement('div');
      sub.className = 'sub';
      sub.textContent = f.summary;
      text.appendChild(name);
      text.appendChild(sub);
      const cost = document.createElement('span');
      cost.className = 'cost' + (f.cost_source === 'symbol' ? ' sym' : '');
      cost.textContent = (f.flash >= 0 ? '+' : '') + fmt(f.flash) + ' B' +
        (f.cost_source === 'estimate' ? ' est' : '');
      row.appendChild(cb);
      row.appendChild(text);
      row.appendChild(cost);
      box.appendChild(row);
    }
    host.appendChild(box);
  }
}

function predicted() {
  const base = catalog.baseline;
  let flash = base.flash + (base.stamp_offset || 0);
  let ram = base.ram;
  for (const f of catalog.features) {
    const want = state[f.id];
    const def = f.on_by_default;
    if (want === def) continue;
    const sign = want ? 1 : -1;
    flash += sign * f.flash;
    ram += sign * f.ram;
  }
  return { flash: flash, ram: ram };
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
  const warn = $('budget-warn');
  const bad = p.flash > region;
  warn.classList.toggle('hidden', !bad);
  if (bad) warn.textContent = 'Over budget by ' + fmt(over) + ' B. Turn off a feature or two before building.';
  $('build').disabled = bad || !catalog.build.toolchain_ready;
}

function resetState(mode) {
  for (const f of catalog.features) {
    if (mode === 'slim') state[f.id] = false;
    else state[f.id] = f.on_by_default;
  }
  document.querySelectorAll('.row input').forEach((cb, i) => { cb.checked = state[cb.dataset.fid]; });
  // simplest reliable path: re-render
  renderGroups();
  renderBudget();
}

function selection() {
  const on = [];
  const off = [];
  for (const f of catalog.features) {
    (state[f.id] ? on : off).push(f.id);
  }
  return { machine: $('machine').value, on: on, off: off };
}

async function startBuild() {
  $('result').classList.add('hidden');
  $('status').classList.remove('hidden');
  $('phase').textContent = 'submitting';
  $('log').textContent = '';
  const res = await fetch('/api/build', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(selection())
  });
  const data = await res.json();
  if (!res.ok) { $('phase').textContent = data.error || 'rejected'; return; }
  $('jobid').textContent = data.id;
  poll(data.id);
}

function poll(id) {
  if (pollTimer) clearTimeout(pollTimer);
  fetch('/api/build/' + id).then((r) => r.json()).then((j) => {
    $('phase').textContent = j.phase || j.status;
    if (j.log) $('log').textContent = j.log.join('\n');
    $('log').scrollTop = $('log').scrollHeight;
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
  $('r-pred').textContent = fmt(pred) + ' B';
  const err = r.flash_used - pred;
  $('r-err').textContent = (err === 0 ? 'exact' : (err > 0 ? '+' : '') + fmt(err) + ' B');
  $('r-ram').textContent = fmt(r.ram_used) + ' / ' + fmt(r.ram_total) + ' B';
  $('r-size').textContent = fmt(r.file_size) + ' B';
  $('r-sha').textContent = r.sha256;
  $('download').href = '/api/build/' + j.id + '/firmware.bin';
  $('manifest').href = '/api/build/' + j.id + '/manifest.json';
}

async function boot() {
  catalog = await (await fetch('/api/catalog')).json();
  $('baseline-label').textContent = catalog.baseline.label;
  for (const f of catalog.features) state[f.id] = f.on_by_default;
  renderMachines();
  renderGroups();
  renderBudget();
  $('build').onclick = startBuild;
  $('reset').onclick = () => resetState('default');
  $('slim').onclick = () => resetState('slim');
  const b = catalog.build;
  if (!b.toolchain_ready) {
    $('banner').classList.remove('hidden');
    $('banner').textContent = 'Build tree not ready: ' + b.hint;
  }
}

boot();
