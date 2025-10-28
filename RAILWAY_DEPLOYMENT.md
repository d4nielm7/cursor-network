# Railway Deployment Guide

## How This Works

### The Architecture:
1. **Railway**: Hosts the server 24/7 with DATABASE_URL configured
2. **Your Computer**: Each user has their own copy of the code locally
3. **mcp.json**: Points to your LOCAL server.py file
4. **API_KEY**: Each user gets their own user_id (which is the API_KEY)

### Why args MUST Point to Local File:

MCP servers use **stdio** (standard input/output) to communicate with Cursor. This means:
- Cursor spawns a local process
- You **CANNOT** connect to a Railway-hosted server via MCP stdio protocol
- Each user must have server.py running locally

## Deployment Steps:

### 1. Deploy to Railway:

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Add environment variable in Railway dashboard:
# DATABASE_URL = postgresql://your-db-url
# (No need for API_KEY - that's per-user)
```

Or use Railway's GitHub integration to auto-deploy.

### 2. Set Up Railway Environment Variables:

Go to Railway Dashboard → Your Project → Variables:
- Add: `DATABASE_URL` = your Neon Postgres URL

### 3. For Each User (local setup):

```json
// ~/.cursor/mcp.json
{
  "mcpServers": {
    "linkedin-network": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"],
      "env": {
        "API_KEY": "their-user-id-here"
      }
    }
  }
}
```

## Key Points:

✅ **Railway hosts**: Keeps server running, provides DATABASE_URL  
✅ **Local server.py**: Each user runs their own copy (via Cursor)  
✅ **API_KEY**: Unique per user (their user_id from database)  
✅ **args**: MUST point to local file path  

## Summary:

- **For Railway**: Just deploy - it runs server.py with DATABASE_URL from env vars
- **For Users**: Clone repo, add their API_KEY to mcp.json, point args to local server.py

