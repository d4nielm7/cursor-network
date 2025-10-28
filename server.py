"""
Simple LinkedIn Network MCP Server
Connects to Neon Postgres and exposes LinkedIn data to Cursor
Each user's API key filters to show only their network
"""

from fastmcp import FastMCP
import asyncpg
import os
import json
from dotenv import load_dotenv
import sys

# Load environment variables from .env file (for local development)
load_dotenv()

# Create MCP server
mcp = FastMCP("LinkedIn Network")

# Database connection - loaded from environment variables
# For Railway: Set DATABASE_URL in Railway dashboard
# For local dev: Set in .env file or mcp.json env section
DATABASE_URL = os.getenv("DATABASE_URL")
# API_KEY comes from mcp.json env section
API_KEY = os.getenv("API_KEY")

db_pool = None

async def get_db():
    """Get database connection pool"""
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
    return db_pool

async def get_user_id():
    """Get user_id from API key - this ensures each user only sees their data"""
    if not API_KEY:
        raise Exception("API_KEY not set. Please set your API key in Cursor config.")
    
    pool = await get_db()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT user_id FROM users WHERE api_key = $1::uuid",
            API_KEY
        )
        
        if not result:
            raise Exception(f"Invalid API key")
        
        return result['user_id']


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
    user_id = await get_user_id()  # Gets user_id from their API key
    pool = await get_db()
    async with pool.acquire() as conn:
        results = await conn.fetch("""
            SELECT 
                full_name, headline, linkedin_url, email,
                current_company, current_company_website_url, skills, keywords
            FROM people
            WHERE 
                user_id = $1
                AND (
                    full_name ILIKE $2 
                    OR headline ILIKE $2 
                    OR current_company ILIKE $2
                    OR keywords::text ILIKE $2
                    OR skills::text ILIKE $2
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
    user_id = await get_user_id()  # Gets user_id from their API key
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
    user_id = await get_user_id()  # Gets user_id from their API key
    pool = await get_db()
    async with pool.acquire() as conn:
        # Build a query that checks if any keyword appears in the keywords column
        keyword_conditions = " OR ".join([f"keywords::text ILIKE '%{kw}%'" for kw in keywords])
        
        results = await conn.fetch(f"""
            SELECT 
                full_name, headline, linkedin_url,
                current_company, skills, keywords
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
    user_id = await get_user_id()  # Gets user_id from their API key
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


# This runs the server
if __name__ == "__main__":
    mcp.run()