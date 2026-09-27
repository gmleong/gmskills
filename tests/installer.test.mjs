import assert from "node:assert/strict";
import { cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { run } from "../bin/vibedesign.mjs";

const source = fileURLToPath(new URL("../skills/vibedesign/", import.meta.url));

test("安装器隔离全局与项目目录，幂等安装，更新前保留全部原文件", (t) => {
  const root = mkdtempSync(join(tmpdir(), "vibedesign-installer-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const home = join(root, "home");
  const cwd = join(root, "project with spaces");
  const options = { home, cwd, log: () => {} };
  const globalTarget = join(home, ".agents", "skills", "vibedesign");
  const projectTarget = join(cwd, ".agents", "skills", "vibedesign");
  assert.equal(run(["status"], options), 1);
  assert.equal(existsSync(home), false);
  assert.equal(run(["install", "--project"], options), 0);
  assert.equal(existsSync(home), false);
  assert.equal(run(["status", "--project"], options), 0);
  assert.deepEqual(readFileSync(join(projectTarget, "SKILL.md")), readFileSync(join(source, "SKILL.md")));

  assert.equal(run(["install"], options), 0);
  const original = lstatSync(globalTarget);
  assert.equal(run(["install", "--global"], options), 0);
  assert.equal(lstatSync(globalTarget).mtimeMs, original.mtimeMs);
  assert.equal(existsSync(join(home, ".agents", "vibedesign-backups")), false);

  writeFileSync(join(globalTarget, "SKILL.md"), "user's local changes");
  writeFileSync(join(globalTarget, "notes.txt"), "keep me");
  assert.equal(run(["status"], options), 1);
  assert.equal(run(["install"], options), 0);
  assert.equal(run(["status"], options), 0);
  const backups = join(home, ".agents", "vibedesign-backups");
  assert.equal(readdirSync(backups).length, 1);
  const backup = join(backups, readdirSync(backups)[0], "vibedesign");
  assert.equal(readFileSync(join(backup, "SKILL.md"), "utf8"), "user's local changes");
  assert.equal(readFileSync(join(backup, "notes.txt"), "utf8"), "keep me");
  assert.equal(existsSync(join(globalTarget, "notes.txt")), false);
  assert.equal(readdirSync(join(home, ".agents")).some((name) => name.startsWith(".vibedesign-stage-")), false);
});

test("安装器识别旧版链接，拒绝改写链接、冲突安装与非目录目标", (t) => {
  const root = mkdtempSync(join(tmpdir(), "vibedesign-links-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const home = join(root, "home");
  const legacy = join(home, ".codex", "skills", "vibedesign");
  const current = join(home, ".agents", "skills", "vibedesign");
  const linkedSource = join(root, "linked-source");
  const options = { home, cwd: root, log: () => {} };
  cpSync(source, linkedSource, { recursive: true });
  mkdirSync(join(home, ".codex", "skills"), { recursive: true });
  symlinkSync(linkedSource, legacy, "dir");
  assert.equal(run(["install"], options), 0);
  assert.equal(lstatSync(legacy).isSymbolicLink(), true);
  assert.equal(existsSync(current), false);
  writeFileSync(join(linkedSource, "SKILL.md"), "preserve linked source");
  assert.equal(run(["status"], options), 1);
  assert.throws(() => run(["install"], options), /符号链接/);
  assert.equal(readFileSync(join(linkedSource, "SKILL.md"), "utf8"), "preserve linked source");
  rmSync(linkedSource, { recursive: true });
  assert.throws(() => run(["install"], options), /符号链接/);
  rmSync(legacy);

  cpSync(source, legacy, { recursive: true });
  writeFileSync(join(legacy, "SKILL.md"), "legacy changes");
  assert.equal(run(["install"], options), 0);
  assert.equal(run(["status"], options), 0);
  assert.equal(existsSync(current), false);
  cpSync(source, current, { recursive: true });
  assert.throws(() => run(["install"], options), /两份/);
  rmSync(current, { recursive: true });
  rmSync(legacy, { recursive: true });
  writeFileSync(current, "not a skill directory");
  assert.throws(() => run(["install"], options), /不是文件夹/);
  assert.equal(readFileSync(current, "utf8"), "not a skill directory");
});

test("安装器校验命令参数，帮助和版本不写文件", () => {
  const options = { log: () => {} };
  assert.equal(run([], options), 0);
  assert.equal(run(["--help"], options), 0);
  assert.equal(run(["--version"], options), 0);
  for (const args of [["delete"], ["install", "extra"], ["install", "--global", "--project"], ["install", "--unknown"]]) {
    assert.throws(() => run(args, options));
  }
});
