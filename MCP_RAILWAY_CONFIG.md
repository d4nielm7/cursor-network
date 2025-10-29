# MCP Configuration for Railway Deployment

## If Cursor supports SSE transport:

Update your `mcp.json` to connect to Railway:

```json
{
  "mcpServers": {
    "linkedin-network": {
      "url": "https://your-railway-app.up.railway.app/sse",
      "type": "sse",
      "headers": {
        "API_KEY": "x"
      }
    }
  }
}
```

## If Cursor only supports STDIO (most likely):

Keep your current `mcp.json` - it's already correct:



**Note:** Railway deployment is running for web/HTTP access. Cursor continues using your local server.py via STDIO.

