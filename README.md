# LinkedIn Network MCP Server - Simple Setup

Super simple MCP server to connect your LinkedIn network data in Neon to Cursor.

## 🚀 Quick Start

### How to Run

To run the `server.py` script, execute the following command in your terminal:

```bash
python server.py
```

### How to Test

To test the database connection, execute the following command in your terminal:

```bash
python test_mcp.py
```

For more detailed setup instructions, see the [Step-by-Step Setup](#-step-by-step-setup) section below.

## 🎯 What This Does

Your n8n workflow scrapes LinkedIn → stores in Neon → MCP server exposes it → Cursor can query it naturally!

Example Cursor queries:
- "Find all founders in my network"
- "Who works at AI companies?"
- "Show me connections with 'machine learning' skills"

---

## 📋 Step-by-Step Setup

### Step 1: Set Up Neon Database

1. Go to https://neon.tech and create a free account
2. Create a new project (name it "linkedin-network" or whatever)
3. Copy your connection string (looks like `postgresql://user:password@host.neon.tech/dbname`)
4. Open the SQL Editor in Neon
5. Copy and paste the contents of `schema.sql` and run it
   - This creates the `people` table with all the fields your n8n workflow needs

### Step 2: Update Your n8n Workflow

Your n8n workflow (from the JSON you shared) needs to insert data into this Neon database.

In the n8n workflow, update the "Insert People" node to use your Neon connection string.

The workflow should insert data with this structure:
```json
{
  "full_name": "John Doe",
  "headline": "CEO at TechCorp",
  "location": "San Francisco, CA",
  "linkedin_url": "https://linkedin.com/in/johndoe",
  "current_company": {
    "title": "CEO",
    "name": "TechCorp",
    "industry": "Technology"
  },
  "skills_top": ["ai", "leadership", "saas"],
  "keywords": ["founder", "ai", "saas", "ceo", "enterprise"]
}
```

### Step 3: Install MCP Server

On your computer (or wherever you want to run the server):

```bash
# Clone or download these files
cd /path/to/this/folder

# Install dependencies
pip install -r requirements.txt
```

### Step 4: Configure Database Connection

Create a `.env` file in the project root with your Neon connection string:

```bash
# Create .env file
DATABASE_URL=postgresql://user:password@host.neon.tech/dbname
```

**Note**: Replace with your actual Neon connection string from Step 1.

### Step 5: Test the Connection

```bash
# Test database connection
python test_connection.py
```

This will verify:
- ✅ Database connection works
- ✅ `people` table exists
- ✅ Data is present in the database

### Step 6: Run the Server

```bash
python server.py
```

If it works, you'll see: `Server started successfully`

### Step 7: Connect to Cursor

Open Cursor, go to **Settings → Features → MCP**

Click "Add New MCP Server" and add this configuration:

```json
{
  "mcpServers": {
    "linkedin-network": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"],
      "env": {
        "API_KEY": "your-api-key-here"
      }
    }
  }
}
```

**Note**: 
- For local development: Create a `.env` file with `DATABASE_URL` or set it in your environment
- The server automatically loads DATABASE_URL from `.env` file or environment variables
- Only API_KEY needs to be in the mcp.json `env` section
- **Important**: Replace `/absolute/path/to/server.py` with the FULL path (like `/Users/yourname/projects/mcp-server/server.py`)

### Step 8: Test in Cursor

1. Restart Cursor
2. Open a new chat
3. Look for the MCP icon (hammer) in the chat - should show "linkedin-network" is connected
4. Try asking: **"How many people are in my LinkedIn network?"**
5. Cursor should use the `analyze_network` tool and give you stats!

---

## 🛠️ Available Tools (What Cursor Can Do)

| Tool | What It Does | Example Query |
|------|--------------|---------------|
| `search_network` | Search by name, title, company, skills | "Find all people who work at Google" |
| `get_profile` | Get detailed info about someone | "Tell me about John Doe's background" |
| `filter_by_keywords` | Filter by AI keywords | "Show founders in AI" |
| `analyze_network` | Get network statistics | "Analyze my LinkedIn network" |

---

## 🔧 Troubleshooting

### "Database connection failed"
- Check your `.env` file has the correct DATABASE_URL
- Make sure Neon project is running (check neon.tech dashboard)
- Run `python test_connection.py` to test the connection

### "No data found"
- Make sure your n8n workflow has run and inserted data
- Check data in Neon: `SELECT COUNT(*) FROM people;`

### "MCP server not connecting in Cursor"
- Make sure you used the FULL absolute path to server.py
- Check Cursor logs (Settings → Output → MCP)
- Try running `python server.py` manually first

### "Python module not found"
- Make sure you ran `pip install -r requirements.txt`
- Check you're using the right Python version: `python --version` (needs 3.8+)

---

## 🚀 Deploy to Railway

### Railway Setup

1. **Create Railway Account**: Go to https://railway.app
2. **Create New Project**: Click "New Project" → Select "Deploy from GitHub repo" (or use Railway CLI)
3. **Connect Your Repository**: Link this project to Railway
4. **Add Environment Variables**:
   - Go to your service → Settings → Variables
   - Add `API_KEY` with your API key value
   - Add `DATABASE_URL` (Railway will auto-set this if you add a Postgres service)
5. **Deploy**: Railway will automatically detect Python and deploy

### Using Railway Server from Cursor

After deploying to Railway, your mcp.json configuration is simple:

```json
{
  "mcpServers": {
    "linkedin-network": {
      "command": "python",
      "args": ["path/to/server.py"],
      "env": {
        "API_KEY": "your-api-key-here"
      }
    }
  }
}
```

**Key Points**:
- ✅ DATABASE_URL is handled by Railway automatically - no need to set in mcp.json
- ✅ For local dev: Create `.env` file with DATABASE_URL or set it as environment variable
- ✅ For Railway: DATABASE_URL is provided by Railway automatically
- ✅ API_KEY is the only value needed in mcp.json env section

## 🚀 Next Steps (After It Works)

Once you verify it works:

1. **Add Multi-User Support**: Generate unique API keys per user → validate in MCP server
2. **Deploy to Railway**: Follow Railway setup above for always-on availability
3. **Scale**: Add more features like connection search, company analytics, etc.

---

## 📝 File Structure

```
.
├── server.py           # Main MCP server (FastMCP)
├── test_connection.py # Test script to verify database connection
├── schema.sql          # Database schema for Neon
├── requirements.txt    # Python dependencies
├── Procfile            # Railway deployment file
├── runtime.txt         # Python version for Railway
├── .env                # Database connection (create this file - not in git)
├── .gitignore         # Git ignore file
└── README.md          # This file
```

## 🔑 Environment Variables

### Local Development

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql://user:password@host.neon.tech/dbname
API_KEY=your-api-key-here
```

### Railway Deployment

Add environment variables in Railway dashboard:

1. Go to your service → Settings → Variables
2. Add:
   - `API_KEY` = your-api-key-here
   - `DATABASE_URL` = your-database-url (Railway will auto-set if using Railway Postgres)

### Using with Cursor (mcp.json)

Your `~/.cursor/mcp.json` should look like this:

```json
{
  "mcpServers": {
    "linkedin-network": {
      "command": "python",
      "args": ["C:\\full\\path\\to\\server.py"],
      "env": {
        "API_KEY": "your-api-key-here"
      }
    }
  }
}
```

**Important**: 
- DATABASE_URL is NOT needed in mcp.json - it loads from `.env` file or environment automatically
- API_KEY is the ONLY thing needed in the env section of mcp.json

---

## 💡 Tips

- **Start Simple**: Get it working with just the database first
- **Use .env File**: Create a `.env` file with your DATABASE_URL for easy configuration
- **Test Each Step**: Use `python test_connection.py` to verify database setup before testing MCP
- **Use Neon Console**: Great for debugging SQL queries
- **Check Cursor Logs**: Settings → Output → MCP shows connection issues

Need help? Check the Anthropic MCP docs: https://docs.anthropic.com/en/docs/mcp
