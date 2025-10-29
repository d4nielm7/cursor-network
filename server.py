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
from fastapi import FastAPI, Request
import uvicorn

# Load environment variables from .env file (override=False means existing env vars take precedence)
# This loads DATABASE_URL for local development
# API_KEY from mcp.json env section takes priority over .env
load_dotenv(override=False)

# Create MCP server
mcp = FastMCP("LinkedIn Network")

# Per-request API key storage (safe for async/concurrent usage)
current_api_key: ContextVar[str | None] = ContextVar("current_api_key", default=None)

# DATABASE_URL: 
# - Local dev: loaded from .env file
# - Railway: set in Railway environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL must be set in .env file (local) or Railway environment variables")

# API_KEY: 
# - For STDIO (local): from mcp.json env section
# - For SSE (Railway): from HTTP headers
# - NEVER from .env file
API_KEY = os.getenv("API_KEY")  # Will be set from headers for SSE transport

db_pool = None

async def get_db():
    """Get database connection pool"""
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
    return db_pool

async def get_user_id():
    """Get user_id from API_KEY (prefer per-request header; fall back to env)"""
    # Prefer header captured for this request
    header_key = current_api_key.get()
    # Fall back to environment/global for local dev or legacy usage
    user_id = header_key or os.getenv("API_KEY") or API_KEY
    
    if not user_id:
        raise Exception("API_KEY not set. Provide it via 'API_KEY'/'X-API-Key' header or env.")
    
    # API_KEY is the user_id
    return user_id


@mcp.tool()
async def search_network(query: str, limit: int = 10) -> str:
    """
    Search your LinkedIn network by name, job title, company, or skills
    
    Args:
        query: Search query (name, title, company, keyword)
        limit: Maximum results to return (default: 10)
    
    Returns:
        JSON string with matching profiles
    """
    user_id = await get_user_id()
    pool = await get_db()
    async with pool.acquire() as conn:
        results = await conn.fetch("""
            SELECT 
                full_name,
                email,
                linkedin_url,
                headline,
                about,
                current_company,
                current_company_linkedin_url,
                current_company_website_url,
                current_company_detail,
                experiences,
                skills,
                education,
                keywords
            FROM people
            WHERE 
                user_id = $1
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
        """, user_id, f"%{query}%", limit)
        
        return json.dumps([dict(r) for r in results], indent=2, default=str)


@mcp.tool()
async def get_profile(name: str) -> str:
    """
    Get detailed profile for a specific person in your network
    
    Args:
        name: Person's full name
    
    Returns:
        JSON string with full profile data
    """
    user_id = await get_user_id()
    pool = await get_db()
    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            SELECT *
            FROM people
            WHERE user_id = $1 AND full_name ILIKE $2
            LIMIT 1
        """, user_id, f"%{name}%")
        
        if result:
            return json.dumps(dict(result), indent=2, default=str)
        else:
            return json.dumps({"error": f"No profile found for: {name}"})


@mcp.tool()
async def filter_by_keywords(keywords: list[str], limit: int = 20) -> str:
    """
    Filter network by targeting keywords (e.g., 'ai', 'founder', 'saas')
    
    Args:
        keywords: List of keywords to match
        limit: Maximum results (default: 20)
    
    Returns:
        JSON string with matching profiles
    """
    user_id = await get_user_id()
    pool = await get_db()
    async with pool.acquire() as conn:
        # Build a query that checks if any keyword appears in the keywords column
        keyword_conditions = " OR ".join([f"keywords::text ILIKE '%{kw}%'" for kw in keywords])
        
        results = await conn.fetch(f"""
            SELECT 
                full_name,
                email,
                linkedin_url,
                headline,
                about,
                current_company,
                current_company_linkedin_url,
                current_company_website_url,
                current_company_detail,
                experiences,
                skills,
                education,
                keywords
            FROM people
            WHERE user_id = $1 AND ({keyword_conditions})
            LIMIT $2
        """, user_id, limit)
        
        return json.dumps([dict(r) for r in results], indent=2, default=str)


@mcp.tool()
async def analyze_network() -> str:
    """
    Get statistics about your LinkedIn network
    
    Returns:
        JSON with network stats (total connections, top skills, keywords, companies)
    """
    user_id = await get_user_id()
    pool = await get_db()
    async with pool.acquire() as conn:
        # Basic stats
        stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_connections,
                COUNT(DISTINCT current_company) as unique_companies
            FROM people
            WHERE user_id = $1
        """, user_id)
        
        # Top keywords (extract from JSON/text field)
        top_keywords = await conn.fetch("""
            SELECT 
                unnest(string_to_array(replace(replace(keywords::text, '[', ''), ']', ''), ',')) as keyword,
                COUNT(*) as count
            FROM people
            WHERE user_id = $1 AND keywords IS NOT NULL
            GROUP BY keyword
            ORDER BY count DESC
            LIMIT 10
        """, user_id)
        
        # Top companies
        top_companies = await conn.fetch("""
            SELECT 
                current_company,
                COUNT(*) as count
            FROM people
            WHERE user_id = $1 AND current_company IS NOT NULL AND current_company != ''
            GROUP BY current_company
            ORDER BY count DESC
            LIMIT 10
        """, user_id)
        
        analysis = {
            "overview": dict(stats),
            "top_keywords": [dict(r) for r in top_keywords],
            "top_companies": [dict(r) for r in top_companies]
        }
        
        return json.dumps(analysis, indent=2)


@mcp.tool()
async def export_network_csv() -> str:
    """
    Export your entire LinkedIn network to CSV format
    
    Returns:
        CSV string with all your network data (full_name, email, company, skills, etc.)
    """
    user_id = await get_user_id()
    pool = await get_db()
    
    async with pool.acquire() as conn:
        # Get all user's network data
        results = await conn.fetch("""
            SELECT 
                full_name,
                email,
                linkedin_url,
                headline,
                about,
                current_company,
                current_company_linkedin_url,
                current_company_website_url,
                current_company_detail,
                experiences,
                skills,
                education,
                keywords
            FROM people
            WHERE user_id = $1
            ORDER BY full_name
        """, user_id)
        
        if not results:
            return "No data found in your network."
        
        # Generate CSV
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Name', 'Email', 'LinkedIn URL', 'Headline', 'About',
            'Company', 'Company LinkedIn', 'Company Website', 'Company Detail',
            'Experiences', 'Skills', 'Education', 'Keywords'
        ])
        
        # Write data rows
        for row in results:
            writer.writerow([
                row.get('full_name', ''),
                row.get('email', ''),
                row.get('linkedin_url', ''),
                row.get('headline', ''),
                row.get('about', ''),
                row.get('current_company', ''),
                row.get('current_company_linkedin_url', ''),
                row.get('current_company_website_url', ''),
                json.dumps(row.get('current_company_detail')) if row.get('current_company_detail') else '',
                json.dumps(row.get('experiences')) if row.get('experiences') else '',
                json.dumps(row.get('skills')) if row.get('skills') else '',
                json.dumps(row.get('education')) if row.get('education') else '',
                json.dumps(row.get('keywords')) if row.get('keywords') else ''
            ])
        
        csv_content = output.getvalue()
        output.close()
        
        return f"Your LinkedIn network CSV ({len(results)} contacts):\n\n{csv_content}"


# Railway/Deployment configuration
if __name__ == "__main__":
    port = int(os.getenv("PORT") or "8000")
    
    # Check if running locally (no PORT) or on Railway (PORT set)
    if os.getenv("PORT"):
        # Running on Railway - use FastAPI with middleware for header capture
        print(f"🚀 Starting MCP server on port {port} (Railway mode)")
        
        # Build a FastAPI app and mount FastMCP's SSE app
        app = FastAPI()
        
        @app.middleware("http")
        async def capture_api_key(request: Request, call_next):
            # Accept several common header spellings
            api_key = (
                request.headers.get("api_key")
                or request.headers.get("API_KEY")
                or request.headers.get("x-api-key")
                or request.headers.get("X-API-Key")
                or request.headers.get("authorization")  # e.g., "Bearer <token>"
            )
            # If Authorization: Bearer <token>, extract token
            if api_key and api_key.lower().startswith("bearer "):
                api_key = api_key.split(" ", 1)[1].strip()
            
            # Store per-request
            token = current_api_key.set(api_key)
            try:
                response = await call_next(request)
            finally:
                current_api_key.reset(token)
            return response
        
        # Mount the SSE endpoint served by FastMCP (using modern API)
        sse_app = create_sse_app(mcp)
        app.mount("/sse", sse_app)
        app.mount("/", sse_app)  # Also mount at root for compatibility
        
        # Run with uvicorn (works on Railway)
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Running locally - use STDIO transport (for Cursor)
        print("🔧 Starting MCP server in STDIO mode (for Cursor)")
        mcp.run()