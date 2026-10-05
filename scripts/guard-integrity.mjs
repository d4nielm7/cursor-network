#!/usr/bin/env node
/**
 * Integrity guard (generic), written after the attacks of 4 March, 3 April and 5 October 2026.
 *
 * Reads the working tree (never runs any of it) and refuses, with the file and the reason, when it finds one of
 * the shapes those attacks used:
 *   - code hidden after a long run of spaces on one line (the payload in postcss/tailwind/next/vite configs,
 *     main.py and others);
 *   - JavaScript-obfuscator output (_0x52a532 names);
 *   - a config file that reaches for eval, programs, hidden decoding, or the global object by name;
 *   - an editor task that runs when the folder opens, or that downloads and runs code;
 *   - the fake Font Awesome set (fa-*.woff2/.ttf/.eot/.svg) outside the top-level public/ folder, or binaries
 *     (.exe .dll .so .dylib) anywhere;
 *   - a .bat/.cmd/.ps1/.vbs file, or a .gitignore that hides one;
 *   - a committed .env file when .gitignore no longer ignores it;
 *   - an npm script that launches public/index.js, fetches code, or runs inline code.
 *
 * Use:   node scripts/guard-integrity.mjs        (exit 1 and a list on a finding)
 * Wire:  "build": "node scripts/guard-integrity.mjs && <the real build>"  and run it first in CI.
 *
 * WHAT IT IS NOT: a guard that lives in the repo can be edited out by whoever can rewrite the repo. What stops
 * the rest is outside it: branches that refuse force-pushes, a login that is not stolen, no secrets at build time.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const SKIP_DIRS = new Set(["site-packages", ".git", ".next", ".turbo", ".venv", "venv", "__pycache__", "node_modules", "coverage", "dist", "build", ".cache"]);
const SOURCE = new Set([".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".mts", ".cts", ".py"]);
const CONFIG = /(^|\/)((next|postcss|tailwind|eslint|prettier|vitest|jest|vite|webpack|rollup|babel|nuxt|svelte|astro|playwright|drizzle)\.config\.(c|m)?[jt]s|\.(eslint|prettier)rc(\.(c|m)?js)?|biome\.jsonc?)$/;
const CONFIG_TOKENS = [
  [/\bglobal(This)?\s*\[/, "reaches into the global object by name"],
  [/\beval\s*\(/, "calls eval"],
  [/\bnew\s+Function\s*\(/, "builds a function from a string"],
  [/\bchild_process\b/, "starts programs"],
  [/\b(exec|execSync|spawn|spawnSync)\s*\(/, "starts programs"],
  [/\batob\s*\(|fromCharCode|["']base64["']/, "decodes hidden text"],
];
const BINARY_ANYWHERE = new Set([".exe", ".dll", ".dylib", ".so"]);
const FAKE_FONT = /(^|\/)fa-(solid|regular|brands|light|duotone)-[0-9]+\.(woff2?|ttf|eot|svg)$/i;
const SCRIPTS_WE_NEVER_SHIP = new Set([".bat", ".cmd", ".ps1", ".vbs", ".scr"]);
const SCRIPT_BAD = /(public\/index\.js|\bnode\s+-e\b|\bcurl\b[^"]*\|[^"]*(sh|bash|node)|\bwget\b[^"]*\|[^"]*(sh|bash|node)|Invoke-WebRequest|base64\s+(-d|--decode))/;

function* walk(root, dir = root) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name) || name.startsWith(".next")) continue;
    const path = join(dir, name);
    const info = statSync(path, { throwIfNoEntry: false });
    if (!info) continue;
    if (info.isDirectory()) yield* walk(root, path);
    else if (info.isFile()) yield path;
  }
}

/** Findings for one tree: [{ file, rule, why }]. */
export function scanTree(root) {
  const found = [];
  let gitignore = null;
  let hasEnvFile = false;
  for (const path of walk(root)) {
    const posix = relative(root, path).split(sep).join("/");
    const ext = extname(posix).toLowerCase();
    const add = (rule, why) => found.push({ file: posix, rule, why });

    if (SCRIPTS_WE_NEVER_SHIP.has(ext)) add("stray-script", `a ${ext} file: nothing here ships or runs one`);
    if (BINARY_ANYWHERE.has(ext)) add("binary-out-of-place", `a ${ext} file`);
    if (FAKE_FONT.test(posix) && !/^public\/fonts\//.test(posix) && !/^public\/[^/]+\.(woff2?|ttf|eot|svg)$/.test(posix)) {
      add("fake-font-set", "a Font Awesome file outside the top-level public/ folder (the attack's decoy)");
    }
    if (/(^|\/)\.env($|\.)/.test(posix) && !/\.(example|sample|template)$/.test(posix)) hasEnvFile = true;
    if (posix === ".gitignore") gitignore = readFileSync(path, "utf8").split(/\r?\n/).map((l) => l.trim());
    if (posix.endsWith(".vscode/tasks.json")) {
      const text = readFileSync(path, "utf8");
      if (/folderOpen/.test(text)) add("runs-on-open", "a task that runs when the folder is opened");
      if (/\b(curl|wget|powershell|Invoke-WebRequest|node\s+-e|bash\s+-c|cmd\s*\/c)\b/i.test(text)) add("task-fetches-code", "a task that downloads or runs inline code");
    }
    if (posix.endsWith("package.json") && !posix.includes("node_modules/")) {
      try {
        const scripts = JSON.parse(readFileSync(path, "utf8")).scripts ?? {};
        for (const [name, cmd] of Object.entries(scripts)) {
          if (SCRIPT_BAD.test(String(cmd))) add("bad-npm-script", `script "${name}" launches public/index.js, fetches or runs inline code`);
        }
      } catch { add("unreadable-package-json", "package.json is not valid JSON"); }
    }
    if (!SOURCE.has(ext) || posix.startsWith("public/") || posix.startsWith("docs/")) continue;
    const text = readFileSync(path, "utf8");
    if (text.split("\n").some((line) => /[ \t]{60,}\S/.test(line))) add("hidden-after-whitespace", "code after a long run of spaces on one line");
    if ((text.match(/_0x[0-9a-f]{4,6}/g) ?? []).length >= 3) add("obfuscated", "variable names in the style of a JavaScript obfuscator");
    if (CONFIG.test(posix)) for (const [pattern, why] of CONFIG_TOKENS) if (pattern.test(text)) add("config-does-too-much", `a config file that ${why}`);
  }
  if (gitignore) {
    if (gitignore.some((l) => /\.(bat|cmd)$/.test(l))) found.push({ file: ".gitignore", rule: "ignores-a-script", why: "ignores a .bat or .cmd file: a place to hide one" });
    if (hasEnvFile && !(gitignore.includes(".env*") || gitignore.includes(".env"))) found.push({ file: ".gitignore", rule: "env-not-ignored", why: "a .env file is here and .gitignore no longer ignores it" });
  }
  return found;
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const findings = scanTree(process.cwd());
  if (findings.length === 0) {
    console.log("guard-integrity: the tree looks as it should");
  } else {
    console.error("guard-integrity: REFUSED. The tree has a shape an attack used (2026):\n");
    for (const f of findings) console.error(`  ${f.file}: ${f.why}  [${f.rule}]`);
    console.error("\nNothing was built or run. Read the files above WITHOUT running them (cat, git show).");
    process.exit(1);
  }
}
