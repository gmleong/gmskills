#!/usr/bin/env node
import { cpSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, renameSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const skillName = "gms-vibedesign";
const source = fileURLToPath(new URL(`../skills/${skillName}/`, import.meta.url));
const { version } = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const help = `gmskills ${version} — Codex Skill 安装器

  gmskills install gms-vibedesign [--global | --project]
  gmskills status  gms-vibedesign [--global | --project]
  gmskills --version

默认安装到 ~/.agents/skills/gms-vibedesign，供当前用户的各项目使用。
--project 仅安装到当前目录的 .agents/skills/gms-vibedesign。
识别 ~/.codex/skills/gms-vibedesign；更新前备份，不覆盖符号链接。
无需模型 API Key；Skill 由当前智能体执行，配色校验需要 Python 3。`;

function entry(path) {
  try { return lstatSync(path); }
  catch (error) { if (error.code === "ENOENT") return null; throw error; }
}

function files(directory, prefix = "") {
  return readdirSync(directory, { withFileTypes: true }).flatMap((item) => {
    const relative = join(prefix, item.name);
    if (item.isDirectory()) return files(join(directory, item.name), relative);
    if (!item.isFile()) throw new Error(`不支持的文件类型：${join(directory, item.name)}`);
    return [relative];
  }).sort();
}

function matches(target, bundled) {
  try {
    const installed = files(target);
    return JSON.stringify(installed) === JSON.stringify(bundled)
      && bundled.every((file) => readFileSync(join(source, file)).equals(readFileSync(join(target, file))));
  } catch { return false; }
}

function destination(home, cwd, project) {
  const current = join(project ? cwd : home, ".agents", "skills", skillName);
  if (project) return current;
  const legacy = join(home, ".codex", "skills", skillName);
  if (!entry(legacy)) return current;
  if (!entry(current)) return legacy;
  if (realpathSync(current) === realpathSync(legacy)) return current;
  throw new Error(`发现两份用户级 Skill，请先保留需要的一份：\n${current}\n${legacy}`);
}

function install(target) {
  const existing = entry(target);
  if (existing?.isSymbolicLink()) {
    throw new Error(`已有符号链接，未修改：${target}\n请更新链接指向的源目录，或自行迁移后重试。`);
  }
  if (existing && !existing.isDirectory()) throw new Error(`目标不是文件夹，未修改：${target}`);

  const base = dirname(dirname(target));
  mkdirSync(base, { recursive: true });
  const staging = mkdtempSync(join(base, `.${skillName}-stage-`));
  let backup;
  let moved = false;
  try {
    cpSync(source, join(staging, skillName), { recursive: true, force: false, errorOnExist: true });
    mkdirSync(dirname(target), { recursive: true });
    if (existing) {
      const backupRoot = join(base, `${skillName}-backups`);
      mkdirSync(backupRoot, { recursive: true });
      const stamp = new Date().toISOString().replaceAll(":", "-");
      backup = join(mkdtempSync(join(backupRoot, `${stamp}-`)), skillName);
      renameSync(target, backup);
      moved = true;
    }
    renameSync(join(staging, skillName), target);
  } catch (error) {
    if (moved) {
      try {
        if (entry(target)) throw new Error("目标已被其他进程创建");
        renameSync(backup, target);
      } catch {
        throw new Error(`安装失败，原文件保存在：${backup}\n${error.message}`, { cause: error });
      }
    }
    throw error;
  } finally {
    rmSync(staging, { recursive: true, force: true });
  }
  return backup;
}

export function run(args, { home = homedir(), cwd = process.cwd(), log = console.log } = {}) {
  const { values, positionals } = parseArgs({
    args, allowPositionals: true, strict: true,
    options: {
      global: { type: "boolean" }, project: { type: "boolean" },
      help: { type: "boolean", short: "h" }, version: { type: "boolean", short: "v" },
    },
  });
  if (values.global && values.project) throw new Error("--global 与 --project 不能同时使用。");
  if (values.help) { log(help); return 0; }
  if (values.version) { log(version); return 0; }
  if (positionals.length === 0) { log(help); return 0; }
  const [command, requestedSkill] = positionals;
  if (positionals.length !== 2 || !["install", "status"].includes(command) || requestedSkill !== skillName) {
    throw new Error(`请使用 install ${skillName}、status ${skillName} 或 --help。`);
  }
  const bundled = files(source);
  if (!bundled.includes("SKILL.md")) throw new Error("安装包缺少 SKILL.md，请重新获取安装包。");
  const target = destination(home, cwd, values.project);
  if (entry(target) && matches(target, bundled)) {
    log(`已安装，与 VibeDesign ${version} 内容一致：${target}`);
    return 0;
  }
  if (command === "status") {
    log(`${entry(target) ? "已存在，但与当前安装包内容不同" : "尚未安装"}：${target}`);
    return 1;
  }
  const backup = install(target);
  log(`已安装 VibeDesign ${version}：${target}`);
  if (backup) log(`原文件备份：${backup}`);
  log("在 Codex 中调用 $gms-vibedesign；若未显示，请重启 Codex。无需额外模型 API Key，配色校验需要 Python 3。");
  return 0;
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.exitCode = run(process.argv.slice(2)); }
  catch (error) { console.error(`VibeDesign: ${error.message}`); process.exitCode = 1; }
}
