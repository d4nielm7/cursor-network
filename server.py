"""
LinkedIn Network MCP Server
Hosted on Railway - connects to Neon Postgres
Users only need their API_KEY, DATABASE_URL is configured on Railway
"""
#.venv\Scripts\activate   
from fastmcp import FastMCP
from fastmcp.server.http import create_sse_app
import asyncpg
import os
import json
from dotenv import load_dotenv
from contextvars import ContextVar
from fastapi import FastAPI
import uvicorn

# Load environment variables from .env file (override=False means existing env vars take precedence)
load_dotenv(override=False)

# Create MCP server
mcp = FastMCP("LinkedIn Network")

# Per-request API key storage
current_api_key: ContextVar[str | None] = ContextVar("current_api_key", default=None)

# DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL must be set in .env file (local) or Railway environment variables")

# API_KEY (fallback for local/STDIO only)
API_KEY = os.getenv("API_KEY")

db_pool = None

async def get_db():
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
    return db_pool

async def get_user_id():
    header_key = current_api_key.get()
    user_id = header_key or os.getenv("API_KEY") or API_KEY
    if not user_id:
        raise Exception("API_KEY not set. Provide it via 'API_KEY'/'X-API-Key' header or env.")
    return user_id

# -------------------------------------------------------------------
# TOOLS
# -------------------------------------------------------------------
@mcp.tool()
async def search_network(query: str, limit: int = 10) -> str:
    user_id = await get_user_id()
    pool = await get_db()
    async with pool.acquire() as conn:
        results = await conn.fetch(
            """
            SELECT 
                full_name, email, linkedin_url, headline, about,
                current_company, current_company_linkedin_url,
                current_company_website_url, current_company_detail,
                experiences, skills, education, keywords
            FROM people
            WHERE user_id = $1
              AND (
                  full_name ILIKE $2 
                  OR headline ILIKE $2 
                  OR about ILIKE $2
                  OR current_company ILIKE $2
                  OR keywords::text ILIKE $2
                  OR skills::text ILIKE $2
                  OR experiences::text ILIKE $2
              )
            LIMIT $3
            """,
            user_id, f"%{query}%", limit
        )
        return json.dumps([dict(r) for r in results], indent=2, default=str)

@mcp.tool()
async def get_profile(name: str) -> str:
    user_id = await get_user_id()
    pool = await get_db()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM people WHERE user_id = $1 AND full_name ILIKE $2 LIMIT 1",
            user_id, f"%{name}%"
        )
        if result:
            return json.dumps(dict(result), indent=2, default=str)
        return json.dumps({"error": f"No profile found for: {name}"})

@mcp.tool()
async def filter_by_keywords(keywords: list[str], limit: int = 20) -> str:
    user_id = await get_user_id()
    pool = await get_db()
    async with pool.acquire() as conn:
        keyword_conditions = " OR ".join([f"keywords::text ILIKE '%{kw}%'" for kw in keywords])
        results = await conn.fetch(f"""
            SELECT 
                full_name, email, linkedin_url, headline, about,
                current_company, current_company_linkedin_url,
                current_company_website_url, current_company_detail,
                experiences, skills, education, keywords
            FROM people
            WHERE user_id = $1 AND ({keyword_conditions})
            LIMIT $2
        """, user_id, limit)
        return json.dumps([dict(r) for r in results], indent=2, default=str)

@mcp.tool()
async def analyze_network() -> str:
    user_id = await get_user_id()
    pool = await get_db()
    async with pool.acquire() as conn:
        stats = await conn.fetchrow(
            "SELECT COUNT(*) as total_connections, COUNT(DISTINCT current_company) as unique_companies FROM people WHERE user_id = $1",
            user_id
        )
        top_keywords = await conn.fetch(
            """
            SELECT unnest(string_to_array(replace(replace(keywords::text, '[', ''), ']', ''))) as keyword, COUNT(*) as count
            FROM people
            WHERE user_id = $1 AND keywords IS NOT NULL
            GROUP BY keyword
            ORDER BY count DESC
            LIMIT 10
            """,
            user_id
        )
        top_companies = await conn.fetch(
            """
            SELECT current_company, COUNT(*) as count
            FROM people
            WHERE user_id = $1 AND current_company IS NOT NULL AND current_company != ''
            GROUP BY current_company
            ORDER BY count DESC
            LIMIT 10
            """,
            user_id
        )
        analysis = {
            "overview": dict(stats),
            "top_keywords": [dict(r) for r in top_keywords],
            "top_companies": [dict(r) for r in top_companies]
        }
        return json.dumps(analysis, indent=2)

@mcp.tool()
async def export_network_csv() -> str:
    user_id = await get_user_id()
    pool = await get_db()
    async with pool.acquire() as conn:
        results = await conn.fetch(
            """
            SELECT 
                full_name, email, linkedin_url, headline, about,
                current_company, current_company_linkedin_url,
                current_company_website_url, current_company_detail,
                experiences, skills, education, keywords
            FROM people
            WHERE user_id = $1
            ORDER BY full_name
            """,
            user_id
        )
        if not results:
            return "No data found in your network."
        import csv, io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Name','Email','LinkedIn URL','Headline','About',
            'Company','Company LinkedIn','Company Website','Company Detail',
            'Experiences','Skills','Education','Keywords'
        ])
        for row in results:
            writer.writerow([
                row.get('full_name', ''), row.get('email', ''), row.get('linkedin_url', ''),
                row.get('headline', ''), row.get('about', ''), row.get('current_company', ''),
                row.get('current_company_linkedin_url', ''), row.get('current_company_website_url', ''),
                json.dumps(row.get('current_company_detail')) if row.get('current_company_detail') else '',
                json.dumps(row.get('experiences')) if row.get('experiences') else '',
                json.dumps(row.get('skills')) if row.get('skills') else '',
                json.dumps(row.get('education')) if row.get('education') else '',
                json.dumps(row.get('keywords')) if row.get('keywords') else ''
            ])
        csv_content = output.getvalue()
        output.close()
        return f"Your LinkedIn network CSV ({len(results)} contacts):\n\n{csv_content}"

# -------------------------------------------------------------------
# Deployment
# -------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT") or "8000")

    if os.getenv("PORT"):
        print(f"🚀 Starting MCP server on port {port} (Railway mode)")

        # Use trailing slash on messages
        sse_app = create_sse_app(
            mcp,
            message_path="/messages/",   # <-- changed here
            sse_path="/sse",
        )

        class HeaderToContextMiddleware:
            def __init__(self, app): self.app = app
            async def __call__(self, scope, receive, send):
                if scope["type"] in ("http","websocket"):
                    headers = {k.decode().lower(): v.decode() for k,v in scope.get("headers",[])}
                    api_key = headers.get("api_key") or headers.get("x-api-key") or headers.get("api-key") or headers.get("authorization")
                    if api_key and api_key.lower().startswith("bearer "):
                        api_key = api_key.split(" ",1)[1].strip()
                    token = current_api_key.set(api_key)
                    try: await self.app(scope, receive, send)
                    finally: current_api_key.reset(token)
                else: await self.app(scope, receive, send)

        wrapped_sse_app = HeaderToContextMiddleware(sse_app)

        fastapi_root = FastAPI()
        @fastapi_root.get("/")
        async def health(): return {"status":"ok","service":"LinkedIn Network MCP"}
        fastapi_root.mount("/", wrapped_sse_app)

        uvicorn.run(fastapi_root, host="0.0.0.0", port=port)
    else:
        print("🔧 Starting MCP server in STDIO mode (for Cursor)")
        mcp.run()
