#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const argv = process.argv.slice(2);
let briefPath = null;
let cdDir = process.cwd();
let outDir = null;
let model = null;
let effort = null;
let timeout = null;
let printTimeout = null;
let readOnly = false;
let dangerouslySkipPermissions = false;
let ignoreUserConfig = false;
let skipGitRepoCheck = false;
let lane = null;
let maxTurns = null;

for (let i = 0; i < argv.length; i++) {
  const arg = argv[i];
  if (arg === "--brief") briefPath = argv[++i];
  else if (arg === "--cd") cdDir = argv[++i];
  else if (arg === "--out-dir") outDir = argv[++i];
  else if (arg === "--model") model = argv[++i];
  else if (arg === "--effort") effort = argv[++i];
  else if (arg === "--timeout") timeout = argv[++i];
  else if (arg === "--print-timeout") printTimeout = argv[++i];
  else if (arg === "--read-only") readOnly = true;
  else if (arg === "--dangerously-skip-permissions") dangerouslySkipPermissions = true;
  else if (arg === "--ignore-user-config") ignoreUserConfig = true;
  else if (arg === "--skip-git-repo-check") skipGitRepoCheck = true;
  else if (arg === "--lane") lane = argv[++i];
  else if (arg === "--max-turns") maxTurns = argv[++i];
}

if (!outDir) {
  process.stderr.write("fake-relay: missing --out-dir\n");
  process.exit(2);
}
fs.mkdirSync(outDir, { recursive: true });

// 1. write argv.json
fs.writeFileSync(path.join(outDir, "argv.json"), JSON.stringify(argv, null, 2) + "\n");

// 2. copy brief to brief.txt
let briefContent = Buffer.alloc(0);
if (briefPath && fs.existsSync(briefPath)) {
  briefContent = fs.readFileSync(briefPath);
  fs.writeFileSync(path.join(outDir, "brief.txt"), briefContent);
}

// 3. parse directive line
const briefStr = briefContent.toString("utf8");
const match = briefStr.match(/fake-relay:\s*([^\r\n]+)/);
let status = "completed";
let finalFile = null;
let exitCode = null;
let errorText = null;
let violation = false;

if (match) {
  const directive = match[1].trim();
  const sMatch = directive.match(/\bstatus=(\S+)/);
  if (sMatch) status = sMatch[1];

  const fMatch = directive.match(/\bfinal=(\S+)/);
  if (fMatch) finalFile = fMatch[1];

  const eMatch = directive.match(/\bexit=(\d+)/);
  if (eMatch) exitCode = parseInt(eMatch[1], 10);

  const vMatch = directive.match(/\bviolation=(true|false)/);
  if (vMatch) violation = (vMatch[1] === "true");

  const errMatch = directive.match(/\berror="([^"]+)"/) || directive.match(/\berror=([^\n\r]+?)(?=(\s+(?:status|final|exit|violation)=|$))/);
  if (errMatch) errorText = errMatch[1].trim();
}

if (status === "none") {
  process.exit(exitCode !== null ? exitCode : 2);
}

let finalMessage = "";
if (finalFile) {
  if (fs.existsSync(finalFile)) {
    finalMessage = fs.readFileSync(finalFile, "utf8");
    fs.writeFileSync(path.join(outDir, "final.txt"), finalMessage);
  }
}

if (exitCode === null) {
  exitCode = (status === "completed") ? 0 : 1;
}

let readOnlyViolation = null;
if (violation) {
  readOnlyViolation = true;
} else if (readOnly) {
  readOnlyViolation = false;
}

const result = {
  status: status,
  exitCode: exitCode,
  signal: null,
  finalMessage: finalMessage,
  readOnlyViolation: readOnlyViolation,
  threadId: "fake-thread",
  touchedFiles: [],
  usage: null
};

if (errorText !== null) {
  result.error = errorText;
}

fs.writeFileSync(path.join(outDir, "result.json"), JSON.stringify(result, null, 2) + "\n");
process.exit(exitCode);
