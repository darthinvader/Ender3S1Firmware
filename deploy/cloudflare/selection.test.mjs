import { validateSelection, canonicalSelection, hashSelection, tagFor, tagLine } from "./selection.js";

let pass = 0, fail = 0;
const ok = (name, cond, detail = "") => {
  if (cond) { pass++; console.log("ok   " + name); }
  else { fail++; console.log("FAIL " + name + " " + detail); }
};

const good = validateSelection({ machine: "ender3s1-f103", off: ["arc_support", "babystepping"], mesh: 7 });
ok("valid selection accepted", !good.error && good.off.length === 2, JSON.stringify(good));

ok("unknown machine refused", !!validateSelection({ machine: "ender3s1-f401" }).error);
ok("mesh 12 refused", !!validateSelection({ mesh: 12 }).error);
ok("mesh 9 accepted", !validateSelection({ mesh: 9 }).error);
ok("bad feature id refused", !!validateSelection({ off: ["../etc/passwd"] }).error);
ok("on/off overlap refused", !!validateSelection({ on: ["arc_support"], off: ["arc_support"] }).error);
ok("too many entries refused", !!validateSelection({ off: Array.from({ length: 121 }, (_, i) => "f" + i) }).error);

const canon = canonicalSelection(good);
const h1 = await hashSelection(canon);
const h2 = await hashSelection(canonicalSelection(validateSelection({ machine: "ender3s1-f103", off: ["babystepping", "arc_support"], mesh: 7 })));
ok("order does not change the hash", h1 === h2, h1 + " vs " + h2);
ok("hash is 12 hex chars", /^[a-f0-9]{12}$/.test(h1), h1);

const tag = await tagFor(good);
ok("tag matches the workflow shape", /^build-[a-f0-9]{12}$/.test(tag), tag);
console.log("tag line:", tagLine(good));

const empty = validateSelection({ machine: "ender3s1-f103" });
ok("empty selection is valid", !empty.error && empty.off.length === 0);
console.log("empty tag:", await tagFor(empty));

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);

