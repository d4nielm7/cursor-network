#!/usr/bin/env node

const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} = require('@modelcontextprotocol/sdk/types.js');
const fs = require('fs').promises;
const path = require('path');
const os = require('os');

// HTTP client - using built-in fetch (Node 18+)
// Node 18+ has built-in fetch, so we use that
if (!globalThis.fetch) {
  console.error('Error: fetch is not available. Node.js 18+ is required.');
  process.exit(1);
}
const fetch = globalThis.fetch;

// CSV writing helper - matches Python's csv.QUOTE_ALL behavior
function arrayToCSV(data) {
  if (!data || data.length === 0) {
    return '';
  }

  const columns = Object.keys(data[0]);
  const escapeCSV = (value) => {
    if (value === null || value === undefined) {
      return '""';
    }
    const str = String(value);
    // Always quote values (QUOTE_ALL behavior), escape internal quotes
    return `"${str.replace(/"/g, '""')}"`;
  };

  const rows = [
    columns.map(escapeCSV).join(','),
    ...data.map(row => 
      columns.map(col => {
        const value = row[col];
        if (value === null || value === undefined) {
          return '""';
        }
        if (typeof value === 'object') {
          // Stringify objects/arrays and clean newlines
          const jsonStr = JSON.stringify(value, null, 0).replace(/\n/g, ' ').replace(/\r/g, ' ');
          return escapeCSV(jsonStr);
        }
        // Clean newlines from string values
        const cleanStr = String(value).replace(/\n/g, ' ').replace(/\r/g, ' ');
        return escapeCSV(cleanStr);
      }).join(',')
    )
  ];

  return rows.join('\n');
}

// Load MCP config from ~/.cursor/mcp.json
function loadMCPConfig() {
  const mcpJsonPath = path.join(os.homedir(), '.cursor', 'mcp.json');
  const fsSync = require('fs');
  
  try {
    if (!fsSync.existsSync(mcpJsonPath)) {
      return { uuid: null, outDir: null };
    }
    
    const configContent = fsSync.readFileSync(mcpJsonPath, 'utf-8');
    const config = JSON.parse(configContent);
    
    const serverConfig = config.mcpServers?.['network-mcp-node'] || {};
    const env = serverConfig.env || {};
    
    return {
      uuid: env.UUID || null,
      outDir: env.OUT_DIR || null
    };
  } catch (error) {
    return { uuid: null, outDir: null };
  }
}

const { uuid: _MCP_UUID, outDir: _mcp_out_dir } = loadMCPConfig();

// Determine OUT_DIR: env var > mcp.json > current directory
const OUT_DIR = process.env.OUT_DIR || _mcp_out_dir || process.cwd();

// Backend URL
const BACKEND_URL = process.env.BACKEND_URL || 'https://web-production-e31ba.up.railway.app';

// Current UUID context (for per-request UUID if needed)
let currentUuid = null;

async function getUuid() {
  if (currentUuid) {
    return currentUuid;
  }
  if (process.env.UUID) {
    return process.env.UUID;
  }
  if (_MCP_UUID) {
    return _MCP_UUID;
  }
  throw new Error("UUID missing. Provide via 'X-UUID' header, env var, or mcp.json.");
}

async function downloadCSVImpl(outDir = '', table = 'people', filename = '', useUuidFilter = true) {
  let uuid = null;
  
  if (useUuidFilter) {
    try {
      uuid = await getUuid();
    } catch (e) {
      uuid = null;
    }
  }
  
  if (!uuid) {
    return "Error: UUID is required to fetch data from backend.";
  }
  
  const saveDir = outDir || OUT_DIR;
  const absoluteSaveDir = path.isAbsolute(saveDir) 
    ? saveDir 
    : path.join(process.cwd(), saveDir);
  
  // Ensure directory exists
  await fs.mkdir(absoluteSaveDir, { recursive: true });
  
  const csvFilename = filename || `${table}.csv`;
  const filepath = path.join(absoluteSaveDir, csvFilename);
  
  try {
    // Create AbortController for timeout (Node 18+ compatible)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout
    
    const response = await fetch(`${BACKEND_URL}/api/network`, {
      method: 'GET',
      headers: {
        'X-UUID': uuid
      },
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      const errorText = await response.text();
      return `Error: Backend returned status ${response.status}: ${errorText}`;
    }
    
    const data = await response.json();
    
    if (!data) {
      return "No records found. Nothing written.";
    }
    
    if (!Array.isArray(data)) {
      return `Error: Backend returned unexpected data format. Expected array, got ${typeof data}.`;
    }
    
    if (data.length === 0) {
      return "No records found. Nothing written.";
    }
    
    // Convert to CSV
    const csvContent = arrayToCSV(data);
    
    // Ensure parent directory exists
    const parentDir = path.dirname(filepath);
    if (parentDir && parentDir !== '.') {
      await fs.mkdir(parentDir, { recursive: true });
    }
    
    // Write CSV file
    await fs.writeFile(filepath, csvContent, 'utf-8');
    
    const cwd = process.cwd();
    return (
      `Fetched ${data.length} records from backend.\n` +
      `Working dir: ${cwd}\nOUT_DIR used: ${absoluteSaveDir}\nSaved to: ${filepath}`
    );
  } catch (error) {
    if (error.name === 'AbortError' || error.name === 'TimeoutError' || error.message.includes('timeout')) {
      return `Error: Request timed out after 30 seconds. Backend may be unresponsive.`;
    }
    if (error.code === 'ECONNREFUSED' || error.code === 'ENOTFOUND' || error.message.includes('fetch failed')) {
      return `Error: Failed to connect to backend: ${error.message}`;
    }
    return `Error: ${error.message || String(error)}`;
  }
}

// Create MCP server
const server = new Server(
  {
    name: 'LinkedIn Network',
    version: '1.0.0',
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// List tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: 'download_csv',
        description: 'Download network data from backend and save as CSV file',
        inputSchema: {
          type: 'object',
          properties: {
            out_dir: {
              type: 'string',
              description: 'Output directory for CSV file (defaults to OUT_DIR env var or current directory)',
            },
            table: {
              type: 'string',
              description: 'Table name (used for default filename, defaults to "people")',
              default: 'people',
            },
            filename: {
              type: 'string',
              description: 'Custom filename for CSV (defaults to "{table}.csv")',
            },
          },
        },
      },
    ],
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  
  if (name === 'download_csv') {
    const { out_dir = '', table = 'people', filename = '' } = args || {};
    const result = await downloadCSVImpl(out_dir, table, filename, true);
    return {
      content: [
        {
          type: 'text',
          text: result,
        },
      ],
    };
  }
  
  throw new Error(`Unknown tool: ${name}`);
});

// Main function
async function main() {
  if (_MCP_UUID) {
    console.error(`MCP Server: Loaded UUID from mcp.json: ${_MCP_UUID}`);
  }
  if (_mcp_out_dir) {
    console.error(`MCP Server: Loaded OUT_DIR from mcp.json: ${_mcp_out_dir}`);
  }
  console.error(`MCP Server: Using OUT_DIR: ${OUT_DIR}`);
  console.error('MCP Server: Starting in STDIO mode...');
  
  const transport = new StdioServerTransport();
  await server.connect(transport);
  
  console.error('MCP Server: Connected and ready');
}

// Handle errors
process.on('uncaughtException', (error) => {
  console.error('Uncaught exception:', error);
  process.exit(1);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled rejection at:', promise, 'reason:', reason);
  process.exit(1);
});

// Start server
main().catch((error) => {
  console.error('Failed to start server:', error);
  process.exit(1);
});

