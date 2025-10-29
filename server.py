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
# TOOLS
# -------------------------------------------------------------------
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
    """
    Get detailed profile for a specific person in your network
    
    Args:
        name: Person's full name (partial match supported)
    
    Returns:
        JSON string with full profile data
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
async def filter_by_keywords(keywords: List[str], limit: int = 20) -> str:
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
    """
    Get statistics about your LinkedIn network
    
    Returns:
        JSON with network stats (total connections, top skills, keywords, companies)
    """
    user_id = await get_user_id()
    pool = await get_db()
    async with pool.acquire() as conn:
        stats = await conn.fetchrow(
            "SELECT COUNT(*) as total_connections, COUNT(DISTINCT current_company) as unique_companies FROM people WHERE user_id = $1",
            user_id
        )
        # Extract keywords from text field - handle JSON array strings
        # Keywords stored as text, may be JSON array like '["ai", "founder"]' or comma-separated
        try:
            top_keywords = await conn.fetch(
                """
                SELECT trim(both ' "' from keyword) as keyword, COUNT(*) as count
                FROM (
                    SELECT jsonb_array_elements_text(keywords::jsonb) as keyword
                    FROM people
                    WHERE user_id = $1 
                      AND keywords IS NOT NULL 
                      AND keywords != ''
                      AND keywords != '[]'
                      AND trim(keywords) != ''
                ) AS keywords_unnested
                WHERE keyword IS NOT NULL 
                  AND trim(keyword) != '' 
                  AND trim(keyword) != 'null'
                GROUP BY keyword
                ORDER BY count DESC
                LIMIT 10
                """,
                user_id
            )
        except Exception:
            # Fallback: parse as comma-separated text
            top_keywords = await conn.fetch(
                """
                SELECT trim(both ' "' from keyword) as keyword, COUNT(*) as count
                FROM (
                    SELECT unnest(string_to_array(keywords::text, ',')) as keyword
                    FROM people
                    WHERE user_id = $1 
                      AND keywords IS NOT NULL 
                      AND keywords != ''
                ) AS keywords_unnested
                WHERE keyword IS NOT NULL 
                  AND trim(keyword) != '' 
                  AND trim(keyword) != 'null'
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

def format_cell(text, max_length=50):
    """Format cell content for table, truncate if too long"""
    if not text:
        return ""
    text = str(text).strip()
    # Remove newlines and extra spaces
    text = " ".join(text.split())
    if len(text) > max_length:
        return text[:max_length-3] + "..."
    return text

def extract_company_name(company_text):
    """Extract company name from current_company field"""
    if not company_text:
        return ""
    # Try to extract just the company name
    company_text = str(company_text).strip()
    # If it contains "at" or "|", take the first part
    if " at " in company_text:
        company_text = company_text.split(" at ")[1].split(" (")[0].strip()
    elif "|" in company_text:
        company_text = company_text.split("|")[0].strip()
    elif "(" in company_text:
        company_text = company_text.split("(")[0].strip()
    return format_cell(company_text, 40)

def format_experiences_for_table(experiences):
    """Format experiences into readable text for table"""
    if not experiences:
        return ""
    
    try:
        if isinstance(experiences, str):
            exp_data = json.loads(experiences)
        else:
            exp_data = experiences
        
        if isinstance(exp_data, list):
            formatted = []
            for exp in exp_data[:2]:  # Limit to first 2 experiences
                if isinstance(exp, dict):
                    title = exp.get('title', '')
                    company = exp.get('name') or exp.get('company', '')
                    period = exp.get('period', '')
                    if title and company:
                        exp_str = f"{title} at {company}"
                        if period:
                            exp_str += f" ({period})"
                        formatted.append(exp_str)
                    elif title:
                        formatted.append(title)
            return " | ".join(formatted) if formatted else ""
        else:
            return str(exp_data)
    except:
        return format_cell(str(experiences), 50)

@mcp.tool()
async def export_network_table(limit: int = 50) -> str:
    """
    Export your LinkedIn network as a formatted table (CSV-like) that displays in Cursor
    
    Args:
        limit: Maximum number of contacts to display (default: 50)
    
    Returns:
        Markdown table with network data formatted for display in Cursor
    """
    user_id = await get_user_id()
    pool = await get_db()
    async with pool.acquire() as conn:
        results = await conn.fetch(
            """
            SELECT 
                full_name, email, linkedin_url, headline, about,
                current_company, current_company_detail, experiences, skills, keywords
            FROM people
            WHERE user_id = $1
            ORDER BY full_name
            LIMIT $2
            """,
            user_id, limit
        )
        if not results:
            return "No data found in your network."
        
        # Build table with specified columns
        output = []
        output.append("| Full Name | Email | LinkedIn URL | Current Company | Skills | Keywords |")
        output.append("|-----------|-------|--------------|-----------------|--------|----------|")
        
        # Table rows
        for row in results:
            full_name = format_cell(row.get('full_name', '') or '', 25)
            email = format_cell(row.get('email', '') or '', 30)
            linkedin_url = format_cell(row.get('linkedin_url', '') or '', 35)
            company = extract_company_name(row.get('current_company', '') or row.get('current_company_detail', ''))
            company = format_cell(company, 30)
            
            # Format skills
            skills_text = row.get('skills', '') or ''
            if skills_text:
                try:
                    skills_data = json.loads(skills_text) if isinstance(skills_text, str) else skills_text
                    if isinstance(skills_data, list):
                        skills_list = [str(s.get('title', s.get('name', s.get('skill', s))) if isinstance(s, dict) else s) for s in skills_data]
                        skills = ", ".join(skills_list)
                    else:
                        skills = str(skills_data)
                except:
                    skills = str(skills_text)
            else:
                skills = ""
            skills = format_cell(skills, 40)
            
            # Format keywords
            keywords_text = row.get('keywords', '') or ''
            if keywords_text:
                try:
                    if isinstance(keywords_text, str):
                        if keywords_text.strip().startswith('['):
                            kw_data = json.loads(keywords_text)
                        else:
                            kw_data = [k.strip() for k in keywords_text.split(',') if k.strip()]
                    else:
                        kw_data = keywords_text
                    if isinstance(kw_data, list):
                        keywords = " | ".join([str(k) for k in kw_data if k and str(k).strip().lower() != 'null'])
                    else:
                        keywords = str(kw_data)
                except:
                    keywords = str(keywords_text)
            else:
                keywords = ""
            keywords = format_cell(keywords, 40)
            
            # Escape pipes in cells
            full_name = full_name.replace('|', '\\|')
            email = email.replace('|', '\\|')
            linkedin_url = linkedin_url.replace('|', '\\|')
            company = company.replace('|', '\\|')
            skills = skills.replace('|', '\\|')
            keywords = keywords.replace('|', '\\|')
            
            output.append(f"| {full_name} | {email} | {linkedin_url} | {company} | {skills} | {keywords} |")
        
        return "\n".join(output)


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
