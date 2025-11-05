#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const scriptDir = __dirname;
const packageRoot = path.resolve(scriptDir, '..');
const serverPath = path.join(packageRoot, 'server.py');
const requirementsPath = path.join(packageRoot, 'requirements.txt');

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

function installRequirements(pythonCmd) {
  return new Promise((resolve, reject) => {
    if (!fs.existsSync(requirementsPath)) {
      resolve(); // No requirements file, skip
      return;
    }
    
    console.error('Installing Python dependencies...');
    const pip = spawn(pythonCmd, ['-m', 'pip', 'install', '-q', '-r', requirementsPath], {
      stdio: ['ignore', 'pipe', 'pipe'],
      cwd: packageRoot
    });
    
    let stderr = '';
    pip.stderr.on('data', (data) => {
      stderr += data.toString();
    });
    
    pip.on('close', (code) => {
      if (code === 0) {
        console.error('Dependencies installed successfully.');
        resolve();
      } else {
        console.error('Warning: Failed to install dependencies:', stderr);
        console.error('You may need to run: pip install -r requirements.txt');
        resolve(); // Continue anyway
      }
    });
    
    pip.on('error', () => {
      console.error('Warning: Could not install dependencies automatically.');
      resolve(); // Continue anyway
    });
  });
}

async function main() {
  try {
    const pythonCmd = await checkPython();
    
    // Try to install requirements if needed
    await installRequirements(pythonCmd);
    
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
