# LinkedIn Network MCP

Export your LinkedIn network data to CSV using npx and MCP.

## Quick Start

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure `~/.cursor/mcp.json`:**
   ```json
   {
     "mcpServers": {
       "network-mcp-node": {
         "command": "npx",
         "args": ["-y", "@ghostteam/network-mcp-node@latest"],
         "env": {
           "API_KEY": "your_api_key",
           "OUT_DIR": "C:\\Users\\User\\Documents"
         }
       }
     }
   }
   ```

   **Note:** The package automatically connects to the cloud database. You only need to add `DATABASE_URL` to `env` if you want to use a different database.

3. **Restart Cursor**

4. **Use the `export_network_csv_to_file` MCP tool** - it will save to the directory specified in `OUT_DIR`

## Publishing to npm

```bash
npm login
npm publish --access public
```
