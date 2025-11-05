#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const scriptDir = __dirname;
const packageRoot = path.resolve(scriptDir, '..');
const serverPath = path.join(packageRoot, 'server.py');

if (!fs.existsSync(serverPath)) {
  console.error(`Error: server.py not found at ${serverPath}`);
  process.exit(1);
}

function checkPython() {
  return new Promise((resolve, reject) => {
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    const check = spawn(pythonCmd, ['--version']);
    
    check.on('close', (code) => {
      if (code === 0) {
        resolve(pythonCmd);
      } else {
        reject(new Error('Python not found. Please install Python 3.8+'));
      }
    });
    
    check.on('error', () => {
      reject(new Error('Python not found. Please install Python 3.8+'));
    });
  });
}

async function main() {
  try {
    const pythonCmd = await checkPython();
    
    const pythonProcess = spawn(pythonCmd, [serverPath], {
      stdio: 'inherit',
      cwd: process.cwd(),
      env: {
        ...process.env  // Includes UUID, OUT_DIR from mcp.json
      }
    });
    
    pythonProcess.on('error', (error) => {
      console.error('Error starting Python server:', error.message);
      process.exit(1);
    });
    
    pythonProcess.on('exit', (code) => {
      process.exit(code || 0);
    });
    
    process.on('SIGINT', () => {
      pythonProcess.kill('SIGINT');
    });
    
    process.on('SIGTERM', () => {
      pythonProcess.kill('SIGTERM');
    });
    
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}

main();
