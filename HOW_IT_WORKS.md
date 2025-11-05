# How It Works After Publishing

## 📦 What Gets Published to npm

When you run `npm publish`, npm includes:
- `bin/cli.js` - JavaScript wrapper
- `server.py` - Python MCP server
- `requirements.txt` - Python dependencies list
- `README.md` - Documentation
- `package.json` - Package metadata

The package gets published as: `@ghostteam/network-mcp-node`

## 🔄 Complete Flow (User Perspective)

### Step 1: User Configures mcp.json

User adds this to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "network-mcp-node": {
      "command": "npx",
      "args": ["-y", "@ghostteam/network-mcp-node@latest"],
      "env": {
        "API_KEY": "their_api_key",
        "OUT_DIR": "C:\\Users\\User\\Documents"
      }
    }
  }
}
```

### Step 2: User Restarts Cursor

Cursor reads `mcp.json` and sees the `network-mcp-node` server configuration.

### Step 3: Cursor Starts the MCP Server

When Cursor needs to communicate with the MCP server, it runs:
```bash
npx -y @ghostteam/network-mcp-node@latest
```

**What happens:**
1. **npx** checks if package is cached locally
2. If not cached, **npx downloads** the package from npm registry
3. Package gets extracted to: `~/.npm/_npx/.../` (temporary location)
4. **npx executes** `bin/cli.js` from the downloaded package

### Step 4: JavaScript Wrapper Runs

`bin/cli.js` executes and:
1. **Checks for Python** - Verifies Python 3.8+ is installed
2. **Finds server.py** - Locates `server.py` in the package directory
3. **Reads environment variables** from `mcp.json`:
   - `API_KEY` → Used for authentication
   - `OUT_DIR` → Where CSV files will be saved
4. **Spawns Python process** - Runs: `python server.py`
5. **Passes environment variables** - All env vars from `mcp.json` are passed to Python

### Step 5: Python Server Starts

`server.py` runs in **STDIO mode** (because no `PORT` env var is set):
1. **Loads environment variables**:
   - `API_KEY` from env (passed from mcp.json)
   - `DATABASE_URL` from env (passed from mcp.json) OR uses default cloud database
   - `OUT_DIR` from env (passed from mcp.json)
2. **Connects to PostgreSQL** using `DATABASE_URL` (defaults to cloud database if not provided)
3. **Starts MCP server** - Listens on stdin/stdout for MCP protocol messages
4. **Registers tools** - Makes `export_network_csv_to_file` available

### Step 6: User Calls Export Tool

When user asks Cursor to export their network:

1. **Cursor sends MCP message** via stdin to the Python process
2. **Python receives** the `export_network_csv_to_file` tool call
3. **Server authenticates** using `API_KEY` from environment
4. **Queries database** - Fetches contacts matching the `user_id` (which is the API_KEY)
5. **Reads `OUT_DIR`** from environment variable
6. **Saves CSV file** to: `{OUT_DIR}/network.csv`
   - Example: `C:\Users\User\Documents\network.csv`
7. **Returns success message** via stdout to Cursor
8. **Cursor displays** the result to the user

## 📍 Important Points

### Environment Variables

**From mcp.json (automatically passed):**
- `API_KEY` - **Required** - Used for authentication (identifies which user's data to fetch)
- `OUT_DIR` - **Required** - Where CSV files are saved
- `DATABASE_URL` - **Optional** - PostgreSQL connection string (defaults to cloud database if not provided)

### File Locations

**Package files** (downloaded by npx):
- Stored in: `~/.npm/_npx/.../` (temporary, managed by npx)

**CSV export file**:
- Saved to: `{OUT_DIR}/network.csv` (from mcp.json)
- User's local machine, in their specified directory

### Prerequisites

Users need:
1. **Node.js 14+** (for npx)
2. **Python 3.8+** (for server.py)
3. **Python packages installed**: `pip install -r requirements.txt`
4. **Configure `mcp.json`** with `API_KEY` and `OUT_DIR` (and optionally `DATABASE_URL`)

## 🎯 Summary

```
User's mcp.json
    ↓
Cursor starts: npx @ghostteam/network-mcp-node@latest
    ↓
npx downloads package from npm
    ↓
bin/cli.js runs (checks Python, finds server.py)
    ↓
Python server.py starts (reads env vars, connects to DB)
    ↓
User calls export_network_csv_to_file
    ↓
Server queries database, saves CSV to OUT_DIR
    ↓
File appears in user's specified directory
```

**Key**: Everything is automatic once published. Users just:
1. Configure `mcp.json` with their `API_KEY` and `OUT_DIR` (DATABASE_URL is optional - defaults to cloud database)
2. Restart Cursor
3. Use the tool!

