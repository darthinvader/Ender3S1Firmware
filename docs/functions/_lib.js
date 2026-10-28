// Shared, testable logic for the Pages Function that dispatches builds.
// The tag rule MUST match .github/workflows/configurator.yml.

const MACHINES = ["ender3s1-f103"];
const ID = /^[a-z0-9_]{2,48}$/;

export function validate(body) {
  if (!body || typeof body !== "object") return { error: "send a JSON object" };
  const machine = String(body.machine || "ender3s1-f103");
  if (!MACHINES.includes(machine)) return { error: "unknown machine " + machine };
  const list = (value, label) => {
    if (value === undefined || value === null) return [];
    if (!Array.isArray(value)) return label + " must be an array";
    if (value.length > 120) return label + " has too many entries";
    for (const item of value) {
      if (typeof item !== "string" || !ID.test(item)) return label + " has an invalid id";
    }
    return [...new Set(value)].sort();
  };
  const off = list(body.off, "off");
  if (typeof off === "string") return { error: off };
  const enable = list(body.on, "on");
  if (typeof enable === "string") return { error: enable };
  if (off.some((x) => enable.includes(x))) return { error: "a feature cannot be both on and off" };
  let mesh = body.mesh;
  if (mesh === undefined || mesh === null || mesh === "") mesh = null;
  else {
    mesh = Number(mesh);
    if (!Number.isInteger(mesh) || mesh < 3 || mesh > 9) return { error: "mesh must be 3..9" };
  }
  return { machine, off, enable, mesh };
}

export function tagLine(selection) {
  let line = "machine=" + selection.machine + ";off=" + selection.off.join(",") +
    ";mesh=" + (selection.mesh === null ? "" : selection.mesh);
  if (selection.enable.length) line += ";on=" + selection.enable.join(",");
  return line;
}

export async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function tagFor(selection) {
  return "build-" + (await sha256Hex(tagLine(selection))).slice(0, 12);
}

export function dispatchBody(selection) {
  return {
    ref: "main",
    inputs: {
      machine: selection.machine,
      disable: selection.off.join(","),
      enable: selection.enable.join(","),
      mesh: selection.mesh === null ? "" : String(selection.mesh),
    },
  };
}

