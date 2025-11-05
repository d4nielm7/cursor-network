# LinkedIn Network MCP

Local npm MCP server that fetches LinkedIn network data from your backend server and exports to CSV.

## Architecture

```
Cursor (MCP Client)
    ↓ npx
Local MCP Server (server.js)
    ↓ HTTP GET /api/network (with X-UUID header)
Backend Server (Railway)
    ↓ Queries database
PostgreSQL Database
    ↓ Returns data
Backend Server
    ↓ Returns JSON response
Local MCP Server
    ↓ Converts to CSV
CSV File (saved locally)
```

**Important:** The MCP server does NOT connect directly to the database. 
It only communicates with your backend server via HTTP API.

## Quick Start

1. **Make sure Node.js 18+ is installed** (dependencies will be installed automatically)

2. **Configure `~/.cursor/mcp.json`:**
   ```json
   {
     "mcpServers": {
       "network-mcp-node": {
         "command": "npx",
         "args": ["-y", "@ghostteam/network-mcp-node@latest"],
         "env": {
           "UUID": "your-uuid-here",
           "OUT_DIR": "C:\\Users\\User\\Documents"
         }
       }
     }
   }
   ```

3. **Restart Cursor**

4. **Use the `download_csv` MCP tool**

## How It Works

1. **MCP Client** (Cursor) runs `npx @ghostteam/network-mcp-node@latest`
2. **Local MCP Server** starts (Node.js/JavaScript)
3. **User calls export tool** → Server sends HTTP GET to backend:
   ```
   GET /api/network
   Headers: X-UUID: your-uuid-here
   ```
4. **Backend Server** queries database for that UUID
5. **Backend returns** JSON array of contacts
6. **MCP Server** saves CSV file to `OUT_DIR`

## Backend API Required

Your backend server needs this endpoint:

```
GET /api/network
Headers:
  X-UUID: <user-uuid>

Response:
  [
    {
      "full_name": "...",
      "email": "...",
      ...
    },
    ...
  ]
```

## Environment Variables

- **UUID** (required): User identifier sent to backend server
- **OUT_DIR** (optional): Where to save CSV files (defaults to current directory)

**Note:** Backend URL is hardcoded in the package and cannot be changed via configuration.

## Publishing to npm

```bash
npm login
npm publish --access public
```
