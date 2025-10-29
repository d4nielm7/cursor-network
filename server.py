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

def parse_json_field(field_data):
    """Parse JSON field from text or JSONB, return formatted string"""
    if not field_data:
        return ''
    
    try:
        # If it's already a dict/list, use it
        if isinstance(field_data, (dict, list)):
            data = field_data
        # If it's a string, try to parse it
        elif isinstance(field_data, str):
            data = json.loads(field_data)
        else:
            return str(field_data)
        
        # Format based on type
        if isinstance(data, list):
            # For arrays like keywords or skills
            formatted_items = []
            for item in data:
                if isinstance(item, dict):
                    # Extract title/name from dict items
                    title = item.get('title') or item.get('name') or item.get('skill') or ''
                    if title:
                        formatted_items.append(title)
                    else:
                        formatted_items.append(str(item))
                else:
                    formatted_items.append(str(item))
            return ' | '.join([str(x) for x in formatted_items if x]) if formatted_items else ''
        elif isinstance(data, dict):
            # For objects like experience or company detail
            # Try to extract meaningful fields
            if 'title' in data and 'name' in data:
                return f"{data.get('title', '')} at {data.get('name', '')}"
            elif 'name' in data:
                return data.get('name', '')
            else:
                return json.dumps(data, ensure_ascii=False)
        else:
            return str(data)
    except (json.JSONDecodeError, TypeError, AttributeError):
        # If parsing fails, return as string (might be comma-separated)
        return str(field_data) if field_data else ''

def format_experiences(experiences):
    """Format experiences into readable text"""
    if not experiences:
        return ''
    
    try:
        if isinstance(experiences, str):
            exp_data = json.loads(experiences)
        else:
            exp_data = experiences
        
        if isinstance(exp_data, list):
            formatted = []
            for exp in exp_data:
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
            return ' | '.join(formatted) if formatted else ''
        elif isinstance(exp_data, dict):
            return parse_json_field(exp_data)
        else:
            return str(exp_data)
    except:
        return str(experiences) if experiences else ''

def format_skills(skills):
    """Format skills into readable text"""
    if not skills:
        return ''
    
    try:
        if isinstance(skills, str):
            skills_data = json.loads(skills)
        else:
            skills_data = skills
        
        if isinstance(skills_data, list):
            skill_names = []
            for skill in skills_data:
                if isinstance(skill, dict):
                    name = skill.get('title') or skill.get('name') or skill.get('skill', '')
                    if name:
                        skill_names.append(name)
                else:
                    skill_names.append(str(skill))
            return ' | '.join([s for s in skill_names if s]) if skill_names else ''
        else:
            return str(skills_data)
    except:
        return str(skills) if skills else ''

def format_keywords(keywords):
    """Format keywords into readable array-like string"""
    if not keywords:
        return ''
    
    try:
        if isinstance(keywords, str):
            # Try to parse as JSON first
            if keywords.strip().startswith('['):
                kw_data = json.loads(keywords)
            else:
                # Comma-separated string
                kw_data = [k.strip() for k in keywords.split(',') if k.strip()]
        elif isinstance(keywords, list):
            kw_data = keywords
        else:
            return str(keywords)
        
        if isinstance(kw_data, list):
            # Filter out empty strings and nulls
            clean_kw = [str(k).strip() for k in kw_data if k and str(k).strip() and str(k).strip().lower() != 'null']
            return ' | '.join(clean_kw) if clean_kw else ''
        else:
            return str(kw_data)
    except:
        return str(keywords) if keywords else ''

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
        
        # Match the structure from the image: Full Name, Email, URL, Headline, Location, About, Current Company, Experience, Skills, Keywords
        writer.writerow([
            'Full Name', 'Email', 'URL', 'Headline', 'Location', 'About', 
            'Current Company', 'Experience', 'Skills', 'Keywords'
        ])
        
        for row in results:
            # Extract company name from current_company (may contain additional text)
            company_text = row.get('current_company', '') or ''
            # Try to extract just the company name if it's in a structured format
            company_name = company_text.split('|')[0].strip() if '|' in company_text else company_text.split('(')[0].strip()
            
            # Format experiences
            formatted_experiences = format_experiences(row.get('experiences'))
            
            # Format skills
            formatted_skills = format_skills(row.get('skills'))
            
            # Format keywords
            formatted_keywords = format_keywords(row.get('keywords'))
            
            # Clean up about text (limit length for CSV readability)
            about_text = row.get('about', '') or ''
            if len(about_text) > 500:
                about_text = about_text[:500] + '...'
            
            writer.writerow([
                row.get('full_name', '') or '',
                row.get('email', '') or '',
                row.get('linkedin_url', '') or '',
                row.get('headline', '') or '',
                '',  # Location - not in current schema, but keeping column for future
                about_text,
                company_name,
                formatted_experiences,
                formatted_skills,
                formatted_keywords
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
