// Exercises the Pages Function logic against a stubbed GitHub, without an account.
// Run: node functions/selftest.mjs
import { validate, tagLine, tagFor, dispatchBody } from "./_lib.js";

let pass = 0, fail = 0;
const ok = (name, cond, detail = "") => {
  if (cond) { pass++; console.log("ok   " + name); } else { fail++; console.log("FAIL " + name + " " + detail); }
};

const good = validate({ machine: "ender3s1-f103", off: ["arc_support"], on: ["bezier_curve_support"], mesh: 7 });
ok("selection accepted", !good.error, JSON.stringify(good));
ok("sorts and dedupes", good.off.length === 1 && good.enable.length === 1);
ok("mesh range enforced", !!validate({ mesh: 12 }).error);
ok("unknown id refused", !!validate({ off: ["../x"] }).error);
ok("on/off overlap refused", !!validate({ on: ["arc_support"], off: ["arc_support"] }).error);

const line = tagLine(good);
ok("tag line matches the workflow rule", line === "machine=ender3s1-f103;off=arc_support;mesh=7;on=bezier_curve_support", line);

const body = dispatchBody(good);
ok("dispatch names the enable input", body.inputs.enable === "bezier_curve_support");
ok("dispatch names the disable input", body.inputs.disable === "arc_support");
ok("dispatch sends the mesh as a string", body.inputs.mesh === "7");

const tagA = await tagFor(good);
const tagB = await tagFor(validate({ machine: "ender3s1-f103", on: ["bezier_curve_support"], off: ["arc_support"], mesh: 7 }));
ok("order does not change the tag", tagA === tagB, tagA + " vs " + tagB);
ok("tag shape", /^build-[a-f0-9]{12}$/.test(tagA), tagA);

const plain = await tagFor(validate({ machine: "ender3s1-f103", off: ["arc_support"], on: [], mesh: 7 }));
ok("disable-only tags keep the old shape", plain === "build-e93da78f5654", plain);
console.log("tag for the enabling selection:", tagA);

// the two functions, with a stubbed fetch and env
const seen = [];
globalThis.fetch = async (url, init = {}) => {
  seen.push({ url: String(url), method: init.method || "GET", body: init.body });
  if (String(url).includes("/releases/tags/")) return new Response("{}", { status: 404 });
  if (String(url).includes("/dispatches")) return new Response(null, { status: 204 });
  return new Response("{}", { status: 200 });
};
process.env.GH_TOKEN = "test-token";
const build = await import("./api/build.js");
const response = await build.onRequestPost({
  request: new Request("https://x/api/build", { method: "POST",
    body: JSON.stringify({ machine: "ender3s1-f103", off: ["arc_support"], on: [], mesh: 7 }) }),
  env: { GH_TOKEN: "test-token" },
});
const payload = await response.json();
ok("POST returns 202 building", response.status === 202 && payload.status === "building", JSON.stringify(payload));
const dispatch = seen.find((s) => s.url.includes("/dispatches"));
ok("dispatch used the workflow endpoint", !!dispatch);
ok("dispatch carried disable", dispatch && JSON.parse(dispatch.body).inputs.disable === "arc_support");
ok("dispatch ref is main", dispatch && JSON.parse(dispatch.body).ref === "main");

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);

