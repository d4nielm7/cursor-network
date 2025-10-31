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
from typing import List
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
# TOOLS - LinkedIn Network Query Tools
# -------------------------------------------------------------------
# IMPORTANT FOR AI ASSISTANT:
# These tools access REAL LinkedIn network data from a PostgreSQL database.
# Never make up or hallucinate network data - always use these tools to retrieve actual information.
# When user mentions "network", "connections", "contacts", "LinkedIn", search/filter/profile tools should be used.
# When user mentions specific topics like "AI", "founder", extract keywords and search the actual network.
# -------------------------------------------------------------------

@mcp.tool()
async def search_network(query: str) -> str:
    """
    Search your actual LinkedIn network contacts by name, job title, company, skills, or keywords.
    
    IMPORTANT: This searches REAL data from your LinkedIn network stored in the database. 
    Always use this when the user asks about people, contacts, or network connections.
    Returns ALL matching results with no limit.
    
    Examples of when to use:
    - "find AI people in my network" -> search_network("AI")
    - "who works at Google?" -> search_network("Google")
    - "show me founders" -> search_network("founder")
    - "people with marketing skills" -> search_network("marketing")
    - "search for Chen Katz" -> search_network("Chen Katz")
    
    Args:
        query: Search term (name, title, company, experience, skill, keyword - will match across all fields)
    
    Returns:
        JSON string with ALL matching profiles from your actual LinkedIn network
    """
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
            """,
            user_id, f"%{query}%"
        )
        return json.dumps([dict(r) for r in results], indent=2, default=str)

@mcp.tool()
async def get_profile(name: str) -> str:
    """
    Get detailed profile information for a specific person in your LinkedIn network.
    
    IMPORTANT: This retrieves REAL profile data from your LinkedIn network database.
    Use this when the user asks about a specific person by name or wants detailed info about someone.
    
    Examples of when to use:
    - "tell me about Chen Katz" -> get_profile("Chen Katz")
    - "what's Esther's background?" -> get_profile("Esther")
    - "show me details on Omer Har" -> get_profile("Omer Har")
    
    Args:
        name: Person's full name or partial name (e.g., "Chen Katz" or just "Chen")
    
    Returns:
        JSON string with full profile data including headline, company, experience, skills, etc.
    """
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
async def filter_by_keywords(keywords: List[str]) -> str:
    """
    Filter your LinkedIn network contacts by specific keywords found in their profiles.
    
    IMPORTANT: This searches REAL keyword data from your LinkedIn network database.
    Use this when the user wants to find people with specific expertise, roles, or interests.
    Returns ALL matching results with no limit.
    
    Examples of when to use:
    - "find people with AI experience" -> filter_by_keywords(["ai"])
    - "show me founders and investors" -> filter_by_keywords(["founder", "investor"])
    - "people in marketing and sales" -> filter_by_keywords(["marketing", "sales"])
    - "who has saas or cloud skills?" -> filter_by_keywords(["saas", "cloud"])
    
    Args:
        keywords: List of keyword strings to match (e.g., ["ai", "founder", "saas"])
    
    Returns:
        JSON string with ALL matching profiles that contain the specified keywords
    """
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
        """, user_id)
        return json.dumps([dict(r) for r in results], indent=2, default=str)

@mcp.tool()
async def analyze_network() -> str:
    """
    Get all contacts from your LinkedIn network with essential information.
    
    IMPORTANT: This returns REAL data from your LinkedIn network stored in the database.
    Use this when the user asks about their network, wants to see all contacts, or analyze their network.
    Returns ALL contacts with no limit - name, email, linkedin, current company, and skills.
    
    Examples of when to use:
    - "analyze my network" -> analyze_network()
    - "what's in my LinkedIn network?" -> analyze_network()
    - "show me my network" -> analyze_network()
    - "list all my connections" -> analyze_network()
    
    Returns:
        JSON array with ALL contacts including: full_name, email, linkedin_url, current_company, skills
    """
    user_id = await get_user_id()
    pool = await get_db()
    async with pool.acquire() as conn:
        results = await conn.fetch(
            """
            SELECT 
                full_name, 
                email, 
                linkedin_url, 
                current_company, 
                skills
            FROM people
            WHERE user_id = $1
            ORDER BY full_name
            """,
            user_id
        )
        return json.dumps([dict(r) for r in results], indent=2, default=str)



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
