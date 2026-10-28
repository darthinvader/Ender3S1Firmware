// Pure helpers, so they can be tested without a Worker runtime.
// The tag rule MUST match .github/workflows/configurator.yml.

const MACHINES = ["ender3s1-f103"];
const ID = /^[a-z0-9_]{2,48}$/;

export function validateSelection(body) {
  if (!body || typeof body !== "object") return { error: "send a JSON object" };
  const machine = String(body.machine || "ender3s1-f103");
  if (!MACHINES.includes(machine)) return { error: "unknown machine " + machine };

  const clean = (value, label) => {
    if (value === undefined || value === null) return [];
    if (!Array.isArray(value)) return label + " must be an array";
    if (value.length > 120) return label + " has too many entries";
    for (const item of value) {
      if (typeof item !== "string" || !ID.test(item)) return label + " has an invalid id: " + String(item).slice(0, 20);
    }
    return [...new Set(value)].sort();
  };

  const off = clean(body.off, "off");
  if (typeof off === "string") return { error: off };
  const on = clean(body.on, "on");
  if (typeof on === "string") return { error: on };
  if (off.some((x) => on.includes(x))) return { error: "a feature cannot be both on and off" };

  let mesh = body.mesh;
  if (mesh === undefined || mesh === null || mesh === "") mesh = null;
  else {
    mesh = Number(mesh);
    if (!Number.isInteger(mesh) || mesh < 3 || mesh > 9) return { error: "mesh must be 3..9" };
  }

  return { machine, on, off, mesh };
}

export function canonicalSelection(selection) {
  return JSON.stringify({
    machine: selection.machine,
    on: selection.on,
    off: selection.off,
    mesh: selection.mesh === null ? null : Number(selection.mesh),
  });
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function hashSelection(text) {
  return (await sha256Hex(text)).slice(0, 12);
}

// exactly the string the workflow hashes: machine=<m>;off=<csv>;mesh=<v>
export function tagLine(selection) {
  return "machine=" + selection.machine + ";off=" + selection.off.join(",") + ";mesh=" + (selection.mesh === null ? "" : selection.mesh);
}

export async function tagFor(selection) {
  return "build-" + (await sha256Hex(tagLine(selection))).slice(0, 12);
}

