#!/usr/bin/env bash
# Content-addressed dashboard build-cache helpers.

pixeagle_dashboard_build_fingerprint() {
    local dashboard_dir="${1:-}"
    local node_version_file="${2:-}"
    [[ -d "$dashboard_dir" && -f "$node_version_file" ]] || return 1

    node - "$dashboard_dir" "$node_version_file" <<'NODE'
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const dashboardDir = path.resolve(process.argv[2]);
const nodeVersionFile = path.resolve(process.argv[3]);
const hash = crypto.createHash('sha256');

const addPart = (kind, logicalPath, content = Buffer.alloc(0)) => {
  const bytes = Buffer.isBuffer(content) ? content : Buffer.from(String(content));
  hash.update(`${kind}\0${Buffer.byteLength(logicalPath)}\0${logicalPath}\0${bytes.length}\0`);
  hash.update(bytes);
};

const addFile = (logicalPath, filePath) => {
  if (!fs.existsSync(filePath)) {
    addPart('missing', logicalPath);
    return;
  }
  const stat = fs.statSync(filePath);
  if (!stat.isFile()) {
    throw new Error(`dashboard fingerprint input is not a file: ${filePath}`);
  }
  addPart('file', logicalPath, fs.readFileSync(filePath));
};

const walk = (directory, logicalRoot) => {
  if (!fs.existsSync(directory)) {
    addPart('missing-directory', logicalRoot);
    return;
  }
  const entries = fs.readdirSync(directory, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name, 'en'));
  if (entries.length === 0) {
    addPart('empty-directory', logicalRoot);
  }
  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    const logicalPath = path.posix.join(logicalRoot, entry.name);
    if (entry.isDirectory()) {
      walk(fullPath, logicalPath);
    } else if (entry.isFile()) {
      addFile(logicalPath, fullPath);
    } else if (entry.isSymbolicLink()) {
      const target = fs.readlinkSync(fullPath);
      addPart('symlink', logicalPath, target);
      const targetStat = fs.statSync(fullPath);
      if (!targetStat.isFile()) {
        throw new Error(`dashboard fingerprint does not support directory symlinks: ${fullPath}`);
      }
      addFile(`${logicalPath}:target`, fullPath);
    }
  }
};

addPart('format', 'pixeagle-dashboard-build-fingerprint-v2');
walk(path.join(dashboardDir, 'src'), 'src');
walk(path.join(dashboardDir, 'public'), 'public');
for (const name of [
  'package.json',
  'package-lock.json',
  '.env',
  '.env.local',
  '.env.production',
  '.env.production.local',
]) {
  addFile(name, path.join(dashboardDir, name));
}
addFile('../.nvmrc', nodeVersionFile);
process.stdout.write(`${hash.digest('hex')}\n`);
NODE
}

pixeagle_dashboard_build_is_complete() {
    local dashboard_dir="${1:-}"
    local build_dir="$dashboard_dir/build"
    [[ -d "$build_dir" ]] || return 1

    node - "$build_dir" <<'NODE'
const fs = require('fs');
const path = require('path');

const buildDir = path.resolve(process.argv[2]);
const manifestPath = path.join(buildDir, 'asset-manifest.json');
const indexPath = path.join(buildDir, 'index.html');

if (!fs.existsSync(indexPath) || !fs.statSync(indexPath).isFile()) {
  process.stderr.write('dashboard build is missing index.html\n');
  process.exit(1);
}
if (!fs.existsSync(manifestPath) || !fs.statSync(manifestPath).isFile()) {
  process.stderr.write('dashboard build is missing asset-manifest.json\n');
  process.exit(1);
}

let manifest;
try {
  manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
} catch (error) {
  process.stderr.write(`dashboard asset manifest is invalid: ${error.message}\n`);
  process.exit(1);
}

const files = manifest && typeof manifest.files === 'object' && manifest.files
  ? Object.values(manifest.files)
  : [];
const entrypoints = Array.isArray(manifest?.entrypoints) ? manifest.entrypoints : [];
if (!files.some((value) => typeof value === 'string' && /\.js(?:$|[?#])/.test(value))) {
  process.stderr.write('dashboard asset manifest has no JavaScript bundle\n');
  process.exit(1);
}

const references = [...new Set([...files, ...entrypoints])];
for (const reference of references) {
  if (typeof reference !== 'string' || !reference.trim()) {
    process.stderr.write('dashboard asset manifest contains an invalid reference\n');
    process.exit(1);
  }
  const cleanReference = reference.split(/[?#]/, 1)[0].replace(/^\.\//, '');
  if (!cleanReference || path.isAbsolute(cleanReference)) {
    process.stderr.write(`dashboard asset reference is not relative: ${reference}\n`);
    process.exit(1);
  }
  const resolved = path.resolve(buildDir, cleanReference);
  if (resolved !== buildDir && !resolved.startsWith(`${buildDir}${path.sep}`)) {
    process.stderr.write(`dashboard asset reference escapes the build: ${reference}\n`);
    process.exit(1);
  }
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
    process.stderr.write(`dashboard build is missing referenced asset: ${reference}\n`);
    process.exit(1);
  }
}
NODE
}

pixeagle_dashboard_build_cache_is_valid() {
    local dashboard_dir="${1:-}"
    local node_version_file="${2:-}"
    local cache_file="${3:-}"
    [[ -f "$cache_file" && ! -L "$cache_file" ]] || return 1
    pixeagle_dashboard_build_is_complete "$dashboard_dir" || return 1

    local cached_fingerprint current_fingerprint
    IFS= read -r cached_fingerprint < "$cache_file" || return 1
    [[ "$cached_fingerprint" =~ ^[a-f0-9]{64}$ ]] || return 1
    current_fingerprint="$(
        pixeagle_dashboard_build_fingerprint "$dashboard_dir" "$node_version_file"
    )" || return 1
    [[ "$cached_fingerprint" == "$current_fingerprint" ]]
}

pixeagle_dashboard_publish_build_fingerprint() {
    local dashboard_dir="${1:-}"
    local node_version_file="${2:-}"
    local cache_file="${3:-}"
    pixeagle_dashboard_build_is_complete "$dashboard_dir" || return 1

    local cache_dir fingerprint temporary
    fingerprint="$(
        pixeagle_dashboard_build_fingerprint "$dashboard_dir" "$node_version_file"
    )" || return 1
    [[ "$fingerprint" =~ ^[a-f0-9]{64}$ ]] || return 1

    cache_dir="$(dirname "$cache_file")"
    [[ ! -L "$cache_dir" && ! -L "$cache_file" ]] || return 1
    mkdir -p -- "$cache_dir" || return 1
    [[ "$(stat -Lc '%u' -- "$cache_dir" 2>/dev/null || true)" == "$(id -u)" ]] \
        || return 1
    temporary="$(mktemp "${cache_file}.tmp.XXXXXX")" || return 1
    if ! printf '%s\n' "$fingerprint" > "$temporary"; then
        rm -f -- "$temporary"
        return 1
    fi
    chmod 0600 "$temporary" || {
        rm -f -- "$temporary"
        return 1
    }
    mv -fT -- "$temporary" "$cache_file"
}
