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
import csv
import io
import base64
from typing import List
from dotenv import load_dotenv
from contextvars import ContextVar
from fastapi import FastAPI, Response
from fastapi.responses import FileResponse
import uvicorn
import re

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
async def search_network(query: str, limit: int = 10) -> str:
    """
    Search your actual LinkedIn network contacts by name, job title, company, skills, or keywords.
    
    IMPORTANT: This searches REAL data from your LinkedIn network stored in the database. 
    Always use this when the user asks about people, contacts, or network connections.
    
    Examples of when to use:
    - "find AI people in my network" -> search_network("AI", limit=20)
    - "who works at Google?" -> search_network("Google")
    - "show me founders" -> search_network("founder")
    - "people with marketing skills" -> search_network("marketing")
    - "search for Chen Katz" -> search_network("Chen Katz")
    
    Args:
        query: Search term (name, title, company, experience, skill, keyword - will match across all fields)
        limit: Maximum results to return (default: 10)
    
    Returns:
        JSON string with matching profiles from your actual LinkedIn network
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
async def filter_by_keywords(keywords: List[str], limit: int = 20) -> str:
    """
    Filter your LinkedIn network contacts by specific keywords found in their profiles.
    
    IMPORTANT: This searches REAL keyword data from your LinkedIn network database.
    Use this when the user wants to find people with specific expertise, roles, or interests.
    
    Examples of when to use:
    - "find people with AI experience" -> filter_by_keywords(["ai"], limit=20)
    - "show me founders and investors" -> filter_by_keywords(["founder", "investor"])
    - "people in marketing and sales" -> filter_by_keywords(["marketing", "sales"])
    - "who has saas or cloud skills?" -> filter_by_keywords(["saas", "cloud"])
    
    Args:
        keywords: List of keyword strings to match (e.g., ["ai", "founder", "saas"])
        limit: Maximum results to return (default: 20)
    
    Returns:
        JSON string with matching profiles that contain the specified keywords
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
    Get statistics and insights about your LinkedIn network.
    
    IMPORTANT: This analyzes REAL data from your LinkedIn network stored in the database.
    Use this when the user asks about network statistics, overview, or wants to understand their network composition.
    
    Examples of when to use:
    - "analyze my network" -> analyze_network()
    - "what's in my LinkedIn network?" -> analyze_network()
    - "give me network stats" -> analyze_network()
    - "how many connections do I have?" -> analyze_network()
    - "what are the top companies in my network?" -> analyze_network()
    
    Returns:
        JSON with network stats including:
        - Total number of connections
        - Unique companies
        - Top keywords (most common tags)
        - Top companies (by number of connections)
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

def extract_search_keywords(query: str) -> List[str]:
    """
    Extract relevant keywords from natural language query.
    Examples:
    - "AI people" -> ["ai"]
    - "founders and investors" -> ["founder", "investor"]
    - "people with marketing or sales skills" -> ["marketing", "sales"]
    """
    query_lower = query.lower()
    
    # Common patterns to extract keywords
    keywords = []
    
    # Keywords that should be extracted
    common_keywords = [
        'ai', 'artificial intelligence', 'machine learning', 'ml', 'founder', 'founders',
        'investor', 'ceo', 'cfo', 'cto', 'coo', 'cmo', 'marketing', 'sales', 
        'saas', 'startup', 'startups', 'venture', 'vc', 'funding', 'tech',
        'software', 'developer', 'engineer', 'consultant', 'consulting',
        'operations', 'operations', 'product', 'designer', 'design'
    ]
    
    for kw in common_keywords:
        if kw in query_lower:
            keywords.append(kw)
    
    # Also extract quoted terms or specific phrases
    quoted = re.findall(r'"([^"]+)"', query)
    keywords.extend([q.lower() for q in quoted])
    
    # Extract single important words (3+ chars, not common words)
    stop_words = {'the', 'and', 'or', 'in', 'on', 'at', 'with', 'for', 'my', 'me', 'i', 'people', 'show', 'find', 'get'}
    words = re.findall(r'\b[a-z]{3,}\b', query_lower)
    important_words = [w for w in words if w not in stop_words and w not in keywords]
    
    # Take top 3 important words
    keywords.extend(important_words[:3])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)
    
    return unique_keywords[:5]  # Limit to 5 keywords

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
    Export your LinkedIn network contacts as a formatted table that displays in Cursor.
    
    CRITICAL: This function ONLY returns REAL data from PostgreSQL database. NEVER generates or hallucinates data.
    All data must come from the 'people' table WHERE user_id matches the authenticated user.
    If database query fails or returns no results, return error message - NEVER create fake table data.
    
    IMPORTANT: This exports REAL data from your LinkedIn network database as a markdown table.
    Use this when the user wants to see their network in a table/CSV-like format.
    
    Examples of when to use:
    - "show my network as a table" -> export_network_table(limit=50)
    - "export my network" -> export_network_table(limit=50)
    - "give me my contacts in table format" -> export_network_table(limit=100)
    
    Columns included: Full Name, Email, LinkedIn URL, Current Company, Skills, Keywords
    
    Args:
        limit: Maximum number of contacts to display (default: 50)
    
    Returns:
        Markdown table with network data formatted for display in Cursor (ONLY real database data)
    """
    try:
        user_id = await get_user_id()
        pool = await get_db()
        
        # CRITICAL: Only get data from PostgreSQL - never make up data
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
            
            # If no results from database, return error - DO NOT create fake data
            if not results or len(results) == 0:
                return "No data found in your network."
            
            # Build table - ONLY using data from database rows
            output = []
            output.append("| Full Name | Email | LinkedIn URL | Current Company | Skills | Keywords |")
            output.append("|-----------|-------|--------------|-----------------|--------|----------|")
            
            # Process each database row - NEVER create rows that don't exist in database
            for row in results:
                # Extract data directly from database row - no fabrication
                full_name = format_cell(row.get('full_name', '') or '', 25)
                email = format_cell(row.get('email', '') or '', 30)
                linkedin_url = format_cell(row.get('linkedin_url', '') or '', 35)
                company = extract_company_name(row.get('current_company', '') or row.get('current_company_detail', ''))
                company = format_cell(company, 30)
                
                # Format skills from database data only
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
                
                # Format keywords from database data only
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
                
                # Only add row if it came from database
                output.append(f"| {full_name} | {email} | {linkedin_url} | {company} | {skills} | {keywords} |")
            
            return "\n".join(output)
            
    except Exception as e:
        # If database error occurs, return error - NEVER create fake table
        return f"Error accessing database: {str(e)}. Cannot generate table without real data."

@mcp.tool()
async def export_network_csv() -> str:
    """
    Export your entire LinkedIn network to a CSV file.
    
    IMPORTANT: Use this when the user wants to download or export their network.
    
    Examples of when to use:
    - "export my network to CSV" -> export_network_csv()
    - "download my network" -> export_network_csv()
    - "get my network as CSV" -> export_network_csv()
    - "save my contacts to a file" -> export_network_csv()
    - "export all my contacts" -> export_network_csv()
    
    Returns:
        CSV content as base64 string that can be saved to the user's computer.
        The CSV maintains the exact same format as the PostgreSQL database.
    """
    try:
        user_id = await get_user_id()
        pool = await get_db()
        
        # Get ALL data from PostgreSQL - same format as your database
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
            
            if not results or len(results) == 0:
                return json.dumps({
                    "status": "error",
                    "message": "No data found in your network."
                }, indent=2)
            
            # Define exact fieldnames from database
            fieldnames = [
                'full_name', 'email', 'linkedin_url', 'headline', 'about',
                'current_company', 'current_company_linkedin_url',
                'current_company_website_url', 'current_company_detail',
                'experiences', 'skills', 'education', 'keywords'
            ]
            
            # Create CSV in memory
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            
            for person in results:
                # Convert to dict with exact database format
                row = {}
                for field in fieldnames:
                    value = person.get(field)
                    
                    # Keep JSON fields as JSON strings (same as PostgreSQL format)
                    if field in ['experiences', 'skills', 'education', 'keywords']:
                        if value:
                            row[field] = json.dumps(value, default=str)
                        else:
                            row[field] = ''
                    else:
                        row[field] = value if value is not None else ''
                
                writer.writerow(row)
            
            # Get CSV content
            csv_content = output.getvalue()
            csv_bytes = csv_content.encode('utf-8')
            
            # Save CSV file to disk automatically
            filename = "linkedin_network_export.csv"
            filepath = os.path.join(os.getcwd(), filename)
            
            with open(filepath, 'wb') as f:
                f.write(csv_bytes)
            
            # Encode as base64 (for compatibility with existing code that might expect it)
            encoded = base64.b64encode(csv_bytes).decode('utf-8')
            
            return json.dumps({
                "status": "success",
                "filename": filename,
                "filepath": filepath,
                "row_count": len(results),
                "size_kb": round(len(csv_bytes) / 1024, 2),
                "csv_base64": encoded,
                "message": f"Successfully exported {len(results)} contacts to {filepath}"
            }, indent=2)
            
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Export failed: {str(e)}"
        }, indent=2)


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
        async def health(): 
            return {"status":"ok","service":"LinkedIn Network MCP"}
        
        @fastapi_root.get("/download/csv")
        async def download_csv():
            """Download the exported CSV file"""
            try:
                # Validate API key (export_network_csv will also call get_user_id internally)
                await get_user_id()
                filename = "linkedin_network_export.csv"
                filepath = os.path.join(os.getcwd(), filename)
                
                # Check if file exists
                if not os.path.exists(filepath):
                    # Generate it if it doesn't exist
                    result_json = await export_network_csv()
                    result = json.loads(result_json)
                    if result.get("status") != "success":
                        return Response(
                            content=json.dumps({"error": "Failed to generate CSV"}),
                            status_code=500,
                            media_type="application/json"
                        )
                
                # Return the file
                return FileResponse(
                    filepath,
                    filename=filename,
                    media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
                )
            except Exception as e:
                return Response(
                    content=json.dumps({"error": str(e)}),
                    status_code=500,
                    media_type="application/json"
                )
        
        fastapi_root.mount("/", wrapped_sse_app)

        uvicorn.run(fastapi_root, host="0.0.0.0", port=port)
    else:
        print("🔧 Starting MCP server in STDIO mode (for Cursor)")
        mcp.run()