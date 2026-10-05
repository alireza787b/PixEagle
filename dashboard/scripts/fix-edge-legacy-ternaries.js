const fs = require('fs');
const path = require('path');

// EdgeHTML tokenizes `condition?.42:.5` as optional chaining. Terser emits this
// compact form for numeric ternary branches, and EdgeHTML then raises SCRIPT1028.
// A numeric property access is not valid JavaScript, so this narrow rewrite is
// unambiguous and leaves real optional chaining untouched.
const buildDir = path.resolve(__dirname, '..', 'build', 'static', 'js');
const indexFile = path.resolve(__dirname, '..', 'build', 'index.html');

if (!fs.existsSync(buildDir)) {
  throw new Error(`Dashboard build directory not found: ${buildDir}`);
}

for (const name of fs.readdirSync(buildDir)) {
  if (!name.endsWith('.js')) {
    continue;
  }
  const file = path.join(buildDir, name);
  const source = fs.readFileSync(file, 'utf8');
  const rewritten = source.replace(/\?\.([0-9])/g, '? .$1');
  if (rewritten !== source) {
    fs.writeFileSync(file, rewritten);
  }
}

// The JavaScript bytes changed after CRA computed its hashed filename. Add a
// stable cache-busting query and a build marker so an already-open dashboard
// cannot keep the pre-rewrite bundle through a 304 response.
let index = fs.readFileSync(indexFile, 'utf8');
index = index.replace(/(static\/js\/[^"']+\.js)(?!\?)/g, '$1?compat=edgehtml');
index = index.replace('</head>', '<!-- PixEagle EdgeHTML compatibility bundle -->\n</head>');
fs.writeFileSync(indexFile, index);
