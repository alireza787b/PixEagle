#!/usr/bin/env node
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const BUILD_FINGERPRINT_FORMAT = 'pixeagle-dashboard-build-fingerprint-v2';

class ContractError extends Error {}

function usage() {
  return [
    'Usage:',
    '  dashboard_contract.js dependency-fingerprint <dashboard-dir> <node-version-file>',
    '  dashboard_contract.js dependencies-ready <dashboard-dir> <node-version-file> [cache-file]',
    '  dashboard_contract.js build-fingerprint <dashboard-dir> <node-version-file>',
    '  dashboard_contract.js build-complete <dashboard-dir>',
  ].join('\n');
}

function requireOperandCount(command, operands, minimum, maximum = minimum) {
  if (operands.length < minimum || operands.length > maximum) {
    const expected = minimum === maximum ? `${minimum}` : `${minimum}-${maximum}`;
    throw new ContractError(
      `${command} expects ${expected} path argument(s); received ${operands.length}`,
    );
  }
}

function requireRegularFile(filePath, label, { rejectSymlink = false } = {}) {
  let stat;
  try {
    stat = rejectSymlink ? fs.lstatSync(filePath) : fs.statSync(filePath);
  } catch (error) {
    if (error.code === 'ENOENT') {
      throw new ContractError(`${label} is missing: ${filePath}`);
    }
    throw error;
  }
  if (rejectSymlink && stat.isSymbolicLink()) {
    throw new ContractError(`${label} must not be a symbolic link: ${filePath}`);
  }
  if (!stat.isFile()) {
    throw new ContractError(`${label} is not a file: ${filePath}`);
  }
}

function requireDirectory(directory, label, { rejectSymlink = false } = {}) {
  let stat;
  try {
    stat = rejectSymlink ? fs.lstatSync(directory) : fs.statSync(directory);
  } catch (error) {
    if (error.code === 'ENOENT') {
      throw new ContractError(`${label} is missing: ${directory}`);
    }
    throw error;
  }
  if (rejectSymlink && stat.isSymbolicLink()) {
    throw new ContractError(`${label} must not be a symbolic link: ${directory}`);
  }
  if (!stat.isDirectory()) {
    throw new ContractError(`${label} is not a directory: ${directory}`);
  }
}

function sha256File(filePath, label) {
  requireRegularFile(filePath, label, { rejectSymlink: true });
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function dependencyFingerprint(dashboardDirectory, nodeVersionFile) {
  requireDirectory(dashboardDirectory, 'dashboard directory', {
    rejectSymlink: true,
  });
  // The path is part of the stable CLI signature shared with build-fingerprint.
  // Node's platform, architecture, and ABI remain the dependency cache inputs.
  requireRegularFile(nodeVersionFile, 'Node version file');
  const packageHash = sha256File(
    path.join(dashboardDirectory, 'package.json'),
    'dashboard package manifest',
  );
  const lockHash = sha256File(
    path.join(dashboardDirectory, 'package-lock.json'),
    'dashboard package lock',
  );

  const npmrcPath = path.join(dashboardDirectory, '.npmrc');
  let npmrcHash = 'absent';
  try {
    fs.lstatSync(npmrcPath);
    npmrcHash = sha256File(npmrcPath, 'dashboard npm configuration');
  } catch (error) {
    if (error.code !== 'ENOENT') {
      throw error;
    }
  }

  const nodeRuntime = [
    process.platform,
    process.arch,
    `abi-${process.versions.modules || 'none'}`,
  ].join(':');
  return `${packageHash}_${lockHash}_${npmrcHash}_${nodeRuntime}`;
}

function readCacheValue(cacheFile) {
  const stat = fs.lstatSync(cacheFile);
  if (stat.isSymbolicLink() || !stat.isFile()) {
    return null;
  }

  const content = fs.readFileSync(cacheFile, 'utf8');
  const value = content.replace(/\r?\n$/, '');
  if (!value || /[\r\n]/.test(value)) {
    return null;
  }
  return value;
}

function npmTreeIsValid(dashboardDirectory) {
  let command = 'npm';
  let argumentsList = ['ls', '--all', '--silent'];

  if (process.platform === 'win32') {
    command = process.env.ComSpec || 'cmd.exe';
    argumentsList = ['/d', '/s', '/c', 'npm.cmd ls --all --silent'];
  }

  const result = spawnSync(command, argumentsList, {
    cwd: dashboardDirectory,
    stdio: 'ignore',
    windowsHide: true,
  });
  return !result.error && result.status === 0;
}

function dependenciesReady(dashboardDirectory, nodeVersionFile, cacheFile) {
  try {
    requireDirectory(dashboardDirectory, 'dashboard directory', {
      rejectSymlink: true,
    });
    requireDirectory(
      path.join(dashboardDirectory, 'node_modules'),
      'dashboard dependency tree',
      { rejectSymlink: true },
    );

    const cachedFingerprint = readCacheValue(cacheFile);
    if (!cachedFingerprint) {
      return false;
    }
    if (
      cachedFingerprint
      !== dependencyFingerprint(dashboardDirectory, nodeVersionFile)
    ) {
      return false;
    }
    return npmTreeIsValid(dashboardDirectory);
  } catch {
    return false;
  }
}

function addHashPart(hash, kind, logicalPath, content = Buffer.alloc(0)) {
  const bytes = Buffer.isBuffer(content) ? content : Buffer.from(String(content));
  hash.update(
    `${kind}\0${Buffer.byteLength(logicalPath)}\0${logicalPath}\0${bytes.length}\0`,
  );
  hash.update(bytes);
}

function addBuildFile(hash, logicalPath, filePath) {
  if (!fs.existsSync(filePath)) {
    addHashPart(hash, 'missing', logicalPath);
    return;
  }
  const stat = fs.statSync(filePath);
  if (!stat.isFile()) {
    throw new ContractError(`dashboard fingerprint input is not a file: ${filePath}`);
  }
  addHashPart(hash, 'file', logicalPath, fs.readFileSync(filePath));
}

function addBuildDirectory(hash, directory, logicalRoot) {
  if (!fs.existsSync(directory)) {
    addHashPart(hash, 'missing-directory', logicalRoot);
    return;
  }
  const entries = fs.readdirSync(directory, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name, 'en'));
  if (entries.length === 0) {
    addHashPart(hash, 'empty-directory', logicalRoot);
  }

  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    const logicalPath = path.posix.join(logicalRoot, entry.name);
    if (entry.isDirectory()) {
      addBuildDirectory(hash, fullPath, logicalPath);
    } else if (entry.isFile()) {
      addBuildFile(hash, logicalPath, fullPath);
    } else if (entry.isSymbolicLink()) {
      addHashPart(hash, 'symlink', logicalPath, fs.readlinkSync(fullPath));
      const targetStat = fs.statSync(fullPath);
      if (!targetStat.isFile()) {
        throw new ContractError(
          `dashboard fingerprint does not support directory symlinks: ${fullPath}`,
        );
      }
      addBuildFile(hash, `${logicalPath}:target`, fullPath);
    }
  }
}

function buildFingerprint(dashboardDirectory, nodeVersionFile) {
  requireDirectory(dashboardDirectory, 'dashboard directory');
  requireRegularFile(nodeVersionFile, 'Node version file');

  const hash = crypto.createHash('sha256');
  addHashPart(hash, 'format', BUILD_FINGERPRINT_FORMAT);
  addBuildDirectory(hash, path.join(dashboardDirectory, 'src'), 'src');
  addBuildDirectory(hash, path.join(dashboardDirectory, 'public'), 'public');
  for (const name of [
    'package.json',
    'package-lock.json',
    '.env',
    '.env.local',
    '.env.production',
    '.env.production.local',
  ]) {
    addBuildFile(hash, name, path.join(dashboardDirectory, name));
  }
  addBuildFile(hash, '../.nvmrc', nodeVersionFile);
  return hash.digest('hex');
}

function portableReferenceParts(reference) {
  const withoutQuery = reference.split(/[?#]/, 1)[0].replace(/^\.\//, '');
  if (
    !withoutQuery
    || path.posix.isAbsolute(withoutQuery)
    || path.win32.isAbsolute(withoutQuery)
  ) {
    return null;
  }
  return withoutQuery.replaceAll('\\', '/').split('/');
}

function buildCompleteness(dashboardDirectory) {
  const buildDirectory = path.join(dashboardDirectory, 'build');
  try {
    requireDirectory(buildDirectory, 'dashboard build directory');
  } catch {
    return { complete: false, message: '' };
  }

  const manifestPath = path.join(buildDirectory, 'asset-manifest.json');
  const indexPath = path.join(buildDirectory, 'index.html');
  if (!fs.existsSync(indexPath) || !fs.statSync(indexPath).isFile()) {
    return { complete: false, message: 'dashboard build is missing index.html' };
  }
  if (!fs.existsSync(manifestPath) || !fs.statSync(manifestPath).isFile()) {
    return {
      complete: false,
      message: 'dashboard build is missing asset-manifest.json',
    };
  }

  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  } catch (error) {
    return {
      complete: false,
      message: `dashboard asset manifest is invalid: ${error.message}`,
    };
  }

  const files = manifest && typeof manifest.files === 'object' && manifest.files
    ? Object.values(manifest.files)
    : [];
  const entrypoints = Array.isArray(manifest?.entrypoints) ? manifest.entrypoints : [];
  if (!files.some(
    (value) => typeof value === 'string' && /\.js(?:$|[?#])/.test(value),
  )) {
    return {
      complete: false,
      message: 'dashboard asset manifest has no JavaScript bundle',
    };
  }

  const references = [...new Set([...files, ...entrypoints])];
  for (const reference of references) {
    if (typeof reference !== 'string' || !reference.trim()) {
      return {
        complete: false,
        message: 'dashboard asset manifest contains an invalid reference',
      };
    }

    const referenceParts = portableReferenceParts(reference);
    if (!referenceParts) {
      return {
        complete: false,
        message: `dashboard asset reference is not relative: ${reference}`,
      };
    }
    const resolved = path.resolve(buildDirectory, ...referenceParts);
    const relative = path.relative(buildDirectory, resolved);
    if (
      path.isAbsolute(relative)
      || relative === '..'
      || relative.startsWith(`..${path.sep}`)
    ) {
      return {
        complete: false,
        message: `dashboard asset reference escapes the build: ${reference}`,
      };
    }
    if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
      return {
        complete: false,
        message: `dashboard build is missing referenced asset: ${reference}`,
      };
    }
  }

  return { complete: true, message: '' };
}

function writeResult(value) {
  process.stdout.write(`${value}\n`);
}

function run(argv) {
  const command = argv[0];
  if (!command || command === '--help' || command === '-h') {
    process.stdout.write(`${usage()}\n`);
    return command ? 0 : 2;
  }
  const operands = argv.slice(1);

  if (command === 'dependency-fingerprint') {
    requireOperandCount(command, operands, 2);
    writeResult(
      dependencyFingerprint(path.resolve(operands[0]), path.resolve(operands[1])),
    );
    return 0;
  }
  if (command === 'dependencies-ready') {
    requireOperandCount(command, operands, 2, 3);
    const dashboardDirectory = path.resolve(operands[0]);
    const nodeVersionFile = path.resolve(operands[1]);
    const cacheFile = operands[2]
      ? path.resolve(operands[2])
      : path.join(dashboardDirectory, '.pixeagle_cache', 'deps_hash');
    const ready = dependenciesReady(
      dashboardDirectory,
      nodeVersionFile,
      cacheFile,
    );
    writeResult(ready ? 'true' : 'false');
    return ready ? 0 : 1;
  }
  if (command === 'build-fingerprint') {
    requireOperandCount(command, operands, 2);
    writeResult(
      buildFingerprint(path.resolve(operands[0]), path.resolve(operands[1])),
    );
    return 0;
  }
  if (command === 'build-complete') {
    requireOperandCount(command, operands, 1);
    const result = buildCompleteness(path.resolve(operands[0]));
    writeResult(result.complete ? 'true' : 'false');
    if (!result.complete && result.message) {
      process.stderr.write(`${result.message}\n`);
    }
    return result.complete ? 0 : 1;
  }

  throw new ContractError(`unknown command: ${command}`);
}

try {
  process.exitCode = run(process.argv.slice(2));
} catch (error) {
  process.stderr.write(`dashboard contract: ${error.message}\n`);
  process.exitCode = 2;
}
