"""
LinkedIn Network MCP Server
Hosted on Railway - connects to Neon Postgres
Users only need their API_KEY, DATABASE_URL is configured on Railway
"""
#.venv\Scripts\activate   
from fastmcp import FastMCP
import asyncpg
import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file (override=False means existing env vars take precedence)
# This loads DATABASE_URL for local development
# API_KEY from mcp.json env section takes priority over .env
load_dotenv(override=False)

# Create MCP server
mcp = FastMCP("LinkedIn Network")

# DATABASE_URL: 
# - Local dev: loaded from .env file
# - Railway: set in Railway environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL must be set in .env file (local) or Railway environment variables")

# API_KEY: ONLY from mcp.json env section, NEVER from .env file
# mcp.json sets this when Cursor spawns the process
# override=False ensures mcp.json's API_KEY is never overwritten by .env
API_KEY = os.getenv("API_KEY")

db_pool = None

async def get_db():
    """Get database connection pool"""
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
    return db_pool

async def get_user_id():
    """API_KEY is the user_id directly"""
    if not API_KEY:
        raise Exception("API_KEY not set. Please add your API key to Cursor MCP config.")
    
    # API_KEY is the user_id
    return API_KEY


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


# Railway configuration
if __name__ == "__main__":
    mcp.run()