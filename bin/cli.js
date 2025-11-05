#!/usr/bin/env node

const path = require('path');
const fs = require('fs');

const scriptDir = __dirname;
const packageRoot = path.resolve(scriptDir, '..');
const serverPath = path.join(packageRoot, 'server.js');

if (!fs.existsSync(serverPath)) {
  console.error(`Error: server.js not found at ${serverPath}`);
  process.exit(1);
}

// Check Node.js version (need 18+ for built-in fetch)
const nodeVersion = process.version;
const majorVersion = parseInt(nodeVersion.slice(1).split('.')[0], 10);

if (majorVersion < 18) {
  console.error(`Error: Node.js 18+ required. Current version: ${nodeVersion}`);
  console.error('Please upgrade Node.js or install node-fetch: npm install node-fetch@2');
  process.exit(1);
}

// Run the JavaScript server directly
require(serverPath);
