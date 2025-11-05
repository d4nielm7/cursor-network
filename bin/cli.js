#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// Get the directory where this script is located
// When installed via npm, server.py will be in the same package directory
const scriptDir = __dirname;
const packageRoot = path.resolve(scriptDir, '..');
const serverPath = path.join(packageRoot, 'server.py');

// Verify server.py exists
if (!fs.existsSync(serverPath)) {
  console.error(`Error: server.py not found at ${serverPath}`);
  console.error('Make sure the package is properly installed.');
  process.exit(1);
}

// Check if Python is available
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

// Main execution
async function main() {
  try {
    const pythonCmd = await checkPython();
    
    // Change to current working directory (where user runs the command)
    process.chdir(process.cwd());
    
    // Run the Python server
    // Use stdio: 'inherit' for MCP - this passes stdin/stdout/stderr through
    // All environment variables from mcp.json are automatically passed through
    const pythonProcess = spawn(pythonCmd, [serverPath], {
      stdio: 'inherit',
      cwd: process.cwd(),
      env: {
        ...process.env  // Includes DATABASE_URL, API_KEY, OUT_DIR from mcp.json
      }
    });
    
    pythonProcess.on('error', (error) => {
      console.error('Error starting Python server:', error.message);
      process.exit(1);
    });
    
    pythonProcess.on('exit', (code) => {
      process.exit(code || 0);
    });
    
    // Handle graceful shutdown
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

