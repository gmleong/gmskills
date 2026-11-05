import assert from "node:assert/strict";
import { cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { run } from "../bin/gmskills.mjs";

const source = fileURLToPath(new URL("../skills/gms-vibedesign/", import.meta.url));

test("安装器隔离全局与项目目录，幂等安装，更新前保留全部原文件", (t) => {
  const root = mkdtempSync(join(tmpdir(), "gms-vibedesign-installer-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const home = join(root, "home");
  const cwd = join(root, "project with spaces");
  const options = { home, cwd, log: () => {} };
  const globalTarget = join(home, ".agents", "skills", "gms-vibedesign");
  const projectTarget = join(cwd, ".agents", "skills", "gms-vibedesign");
  assert.equal(run(["status", "gms-vibedesign"], options), 1);
  assert.equal(existsSync(home), false);
  assert.equal(run(["install", "gms-vibedesign", "--project"], options), 0);
  assert.equal(existsSync(home), false);
  assert.equal(run(["status", "gms-vibedesign", "--project"], options), 0);
  assert.deepEqual(readFileSync(join(projectTarget, "SKILL.md")), readFileSync(join(source, "SKILL.md")));

  assert.equal(run(["install", "gms-vibedesign"], options), 0);
  const original = lstatSync(globalTarget);
  assert.equal(run(["install", "gms-vibedesign", "--global"], options), 0);
  assert.equal(lstatSync(globalTarget).mtimeMs, original.mtimeMs);
  assert.equal(existsSync(join(home, ".agents", "gms-vibedesign-backups")), false);

  writeFileSync(join(globalTarget, "SKILL.md"), "user's local changes");
  writeFileSync(join(globalTarget, "notes.txt"), "keep me");
  assert.equal(run(["status", "gms-vibedesign"], options), 1);
  assert.equal(run(["install", "gms-vibedesign"], options), 0);
  assert.equal(run(["status", "gms-vibedesign"], options), 0);
  const backups = join(home, ".agents", "gms-vibedesign-backups");
  assert.equal(readdirSync(backups).length, 1);
  const backup = join(backups, readdirSync(backups)[0], "gms-vibedesign");
  assert.equal(readFileSync(join(backup, "SKILL.md"), "utf8"), "user's local changes");
  assert.equal(readFileSync(join(backup, "notes.txt"), "utf8"), "keep me");
  assert.equal(existsSync(join(globalTarget, "notes.txt")), false);
  assert.equal(readdirSync(join(home, ".agents")).some((name) => name.startsWith(".gms-vibedesign-stage-")), false);
});

test("安装器识别旧版链接，拒绝改写链接、冲突安装与非目录目标", (t) => {
  const root = mkdtempSync(join(tmpdir(), "gms-vibedesign-links-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const home = join(root, "home");
  const legacy = join(home, ".codex", "skills", "gms-vibedesign");
  const current = join(home, ".agents", "skills", "gms-vibedesign");
  const linkedSource = join(root, "linked-source");
  const options = { home, cwd: root, log: () => {} };
  cpSync(source, linkedSource, { recursive: true });
  mkdirSync(join(home, ".codex", "skills"), { recursive: true });
  symlinkSync(linkedSource, legacy, "dir");
  assert.equal(run(["install", "gms-vibedesign"], options), 0);
  assert.equal(lstatSync(legacy).isSymbolicLink(), true);
  assert.equal(existsSync(current), false);
  writeFileSync(join(linkedSource, "SKILL.md"), "preserve linked source");
  assert.equal(run(["status", "gms-vibedesign"], options), 1);
  assert.throws(() => run(["install", "gms-vibedesign"], options), /符号链接/);
  assert.equal(readFileSync(join(linkedSource, "SKILL.md"), "utf8"), "preserve linked source");
  rmSync(linkedSource, { recursive: true });
  assert.throws(() => run(["install", "gms-vibedesign"], options), /符号链接/);
  rmSync(legacy);

  cpSync(source, legacy, { recursive: true });
  writeFileSync(join(legacy, "SKILL.md"), "legacy changes");
  assert.equal(run(["install", "gms-vibedesign"], options), 0);
  assert.equal(run(["status", "gms-vibedesign"], options), 0);
  assert.equal(existsSync(current), false);
  cpSync(source, current, { recursive: true });
  assert.throws(() => run(["install", "gms-vibedesign"], options), /两份/);
  rmSync(current, { recursive: true });
  rmSync(legacy, { recursive: true });
  writeFileSync(current, "not a skill directory");
  assert.throws(() => run(["install", "gms-vibedesign"], options), /不是文件夹/);
  assert.equal(readFileSync(current, "utf8"), "not a skill directory");
});

test("安装器校验命令参数，帮助和版本不写文件", () => {
  const options = { log: () => {} };
  assert.equal(run([], options), 0);
  assert.equal(run(["--help"], options), 0);
  assert.equal(run(["--version"], options), 0);
  for (const args of [["delete"], ["install", "extra"], ["install", "gms-vibedesign", "--global", "--project"], ["install", "gms-vibedesign", "--unknown"]]) {
    assert.throws(() => run(args, options));
  }
});

test("安装 img2svg 时包含运行时，与 VibeDesign 的安装位置独立", (t) => {
  const cwd = mkdtempSync(join(tmpdir(), "gms-img2svg-installer-"));
  t.after(() => rmSync(cwd, { recursive: true, force: true }));
  const options = { cwd, log: () => {} };
  const target = join(cwd, ".agents", "skills", "gms-img2svg");
  assert.equal(run(["install", "gms-img2svg", "--project"], options), 0);
  assert.equal(run(["status", "gms-img2svg", "--project"], options), 0);
  assert.equal(run(["status", "gms-vibedesign", "--project"], options), 1);
  assert.match(readFileSync(join(target, "SKILL.md"), "utf8"), /^name: gms-img2svg$/m);
  assert.equal(readFileSync(join(target, "scripts", "vendor", "vtracer_v1", "pkg", "vtracer_wasm_bg.wasm")).subarray(0, 4).toString("hex"), "0061736d");
});
