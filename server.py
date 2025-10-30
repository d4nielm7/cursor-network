"""
LinkedIn Network MCP Server - Auto-Export to CSV
When connected, automatically exports your network to local CSV
Then provides tools to query the CSV data
"""

from fastmcp import FastMCP
import asyncpg
import os
import json
import csv
from pathlib import Path
from typing import List
import pandas as pd
from dotenv import load_dotenv
from contextvars import ContextVar
from fastapi import FastAPI
import uvicorn
from fastmcp.server.http import create_sse_app
import base64

load_dotenv(override=False)

mcp = FastMCP("LinkedIn Network CSV")

# Per-request API key storage
current_api_key: ContextVar[str | None] = ContextVar("current_api_key", default=None)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY")

if not DATABASE_URL:
    raise Exception("DATABASE_URL must be set in .env file or Railway environment variables")

async def get_user_id():
    """Get user_id from context or env"""
    header_key = current_api_key.get()
    user_id = header_key or os.getenv("API_KEY") or API_KEY
    if not user_id:
        raise Exception("API_KEY not set. Provide it via 'API_KEY'/'X-API-Key' header or env.")
    return user_id

# -------------------------------------------------------------------
# TOOLS - CSV Export and Query
# -------------------------------------------------------------------

@mcp.tool()
async def export_network_to_csv() -> str:
    """
    Export your LinkedIn network from database to CSV format.
    This returns the CSV content as base64 that you can save locally.
    
    Use this first to download your network data!
    """
    try:
        # Connect to database
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Get user_id
        user_id = await get_user_id()
        
        # Get all data for this user
        people = await conn.fetch(
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
        
        await conn.close()
        
        if not people:
            return json.dumps({
                "status": "error",
                "message": "No data found in database for your user_id"
            }, indent=2)
        
        # Create CSV in memory
        import io
        output = io.StringIO()
        
        # Get all unique keys across all rows to handle dynamic fields
        all_keys = set()
        for person in people:
            all_keys.update(person.keys())
        
        # Convert to sorted list for consistent column order
        fieldnames = sorted(list(all_keys))
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for person in people:
            # Convert JSON fields to strings for CSV
            row = dict(person)
            for key in ['experiences', 'skills', 'education', 'keywords']:
                if row.get(key):
                    row[key] = json.dumps(row[key], default=str)
            writer.writerow(row)
        
        # Get CSV content
        csv_content = output.getvalue()
        
        # Save CSV to file automatically
        csv_filename = "linkedin_network_export.csv"
        csv_path = Path(csv_filename)
        csv_path.write_text(csv_content, encoding='utf-8')
        
        # Encode as base64 for transmission
        csv_bytes = csv_content.encode('utf-8')
        encoded = base64.b64encode(csv_bytes).decode('utf-8')
        
        return json.dumps({
            "status": "success",
            "filename": csv_filename,
            "file_path": str(csv_path.absolute()),
            "row_count": len(people),
            "size_bytes": len(csv_bytes),
            "csv_content_base64": encoded,
            "message": f"CSV saved to: {csv_path.absolute()}"
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Export failed: {str(e)}"
        }, indent=2)

@mcp.tool()
async def get_csv_data_sample() -> str:
    """
    Get a sample of the CSV data (first 10 rows) to preview.
    Use export_network_to_csv() to get the full dataset.
    """
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        user_id = await get_user_id()
        
        people = await conn.fetch(
            """
            SELECT 
                full_name, email, linkedin_url, headline, current_company
            FROM people
            WHERE user_id = $1
            ORDER BY full_name
            LIMIT 10
            """,
            user_id
        )
        
        await conn.close()
        
        return json.dumps([dict(p) for p in people], indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

@mcp.tool()
async def search_network(query: str, limit: int = 10) -> str:
    """
    Search your LinkedIn network by name, job title, company, or keywords.
    This searches the live database.
    
    Examples:
    - search_network("AI", limit=20)
    - search_network("Google")
    - search_network("founder")
    """
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        user_id = await get_user_id()
        
        results = await conn.fetch(
            """
            SELECT 
                full_name, email, linkedin_url, headline, about,
                current_company, skills, keywords
            FROM people
            WHERE user_id = $1
              AND (
                  full_name ILIKE $2 
                  OR headline ILIKE $2 
                  OR about ILIKE $2
                  OR current_company ILIKE $2
                  OR keywords::text ILIKE $2
                  OR skills::text ILIKE $2
              )
            LIMIT $3
            """,
            user_id, f"%{query}%", limit
        )
        
        await conn.close()
        
        if not results:
            return json.dumps({"message": f"No results found for: {query}"}, indent=2)
        
        return json.dumps([dict(r) for r in results], indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

@mcp.tool()
async def get_profile(name: str) -> str:
    """
    Get detailed profile for a specific person from your network.
    
    Example:
    - get_profile("Chen Katz")
    """
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        user_id = await get_user_id()
        
        result = await conn.fetchrow(
            """
            SELECT * FROM people 
            WHERE user_id = $1 AND full_name ILIKE $2 
            LIMIT 1
            """,
            user_id, f"%{name}%"
        )
        
        await conn.close()
        
        if not result:
            return json.dumps({"error": f"No profile found for: {name}"}, indent=2)
        
        return json.dumps(dict(result), indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

@mcp.tool()
async def filter_by_keywords(keywords: List[str], limit: int = 20) -> str:
    """
    Filter network by keywords.
    
    Example:
    - filter_by_keywords(["ai", "founder"], limit=20)
    """
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        user_id = await get_user_id()
        
        keyword_conditions = " OR ".join([f"keywords::text ILIKE '%{kw}%'" for kw in keywords])
        
        results = await conn.fetch(f"""
            SELECT 
                full_name, email, linkedin_url, headline, about,
                current_company, skills, keywords
            FROM people
            WHERE user_id = $1 AND ({keyword_conditions})
            LIMIT $2
        """, user_id, limit)
        
        await conn.close()
        
        if not results:
            return json.dumps({"message": f"No results found for keywords: {keywords}"}, indent=2)
        
        return json.dumps([dict(r) for r in results], indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

@mcp.tool()
async def analyze_network() -> str:
    """
    Get statistics and insights about your LinkedIn network.
    """
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        user_id = await get_user_id()
        
        # Basic stats
        stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) as total_connections, 
                COUNT(DISTINCT current_company) as unique_companies,
                COUNT(CASE WHEN email IS NOT NULL THEN 1 END) as has_email
            FROM people 
            WHERE user_id = $1
            """,
            user_id
        )
        
        # Top companies
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
        
        # Top keywords
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
        except:
            top_keywords = []
        
        await conn.close()
        
        analysis = {
            "overview": dict(stats),
            "top_keywords": [dict(r) for r in top_keywords],
            "top_companies": [dict(r) for r in top_companies]
        }
        
        return json.dumps(analysis, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

@mcp.tool()
async def export_network_table(limit: int = 50) -> str:
    """
    Export network as markdown table for easy viewing.
    
    Args:
        limit: Maximum number of contacts to display (default: 50)
    """
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        user_id = await get_user_id()
        
        results = await conn.fetch(
            """
            SELECT 
                full_name, email, linkedin_url, current_company, headline
            FROM people
            WHERE user_id = $1
            ORDER BY full_name
            LIMIT $2
            """,
            user_id, limit
        )
        
        await conn.close()
        
        if not results:
            return "No data found."
        
        # Convert to pandas for table formatting
        df = pd.DataFrame([dict(r) for r in results])
        
        # Truncate long fields
        df['headline'] = df['headline'].fillna('').str[:50]
        df['current_company'] = df['current_company'].fillna('').str[:40]
        df['email'] = df['email'].fillna('')
        df['linkedin_url'] = df['linkedin_url'].fillna('')
        
        return df.to_markdown(index=False)
        
    except Exception as e:
        return f"Error: {str(e)}"

# -------------------------------------------------------------------
# Deployment
# -------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT") or "8000")

    if os.getenv("PORT"):
        # Railway/HTTP mode
        print(f"🚀 Starting MCP server on port {port} (Railway mode)")

        sse_app = create_sse_app(
            mcp,
            message_path="/messages/",
            sse_path="/sse",
        )

        class HeaderToContextMiddleware:
            def __init__(self, app): 
                self.app = app
            
            async def __call__(self, scope, receive, send):
                if scope["type"] in ("http", "websocket"):
                    headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
                    api_key = (
                        headers.get("api_key") or 
                        headers.get("x-api-key") or 
                        headers.get("api-key") or 
                        headers.get("authorization")
                    )
                    if api_key and api_key.lower().startswith("bearer "):
                        api_key = api_key.split(" ", 1)[1].strip()
                    token = current_api_key.set(api_key)
                    try: 
                        await self.app(scope, receive, send)
                    finally: 
                        current_api_key.reset(token)
                else: 
                    await self.app(scope, receive, send)

        wrapped_sse_app = HeaderToContextMiddleware(sse_app)

        fastapi_root = FastAPI()
        
        @fastapi_root.get("/")
        async def health(): 
            return {"status": "ok", "service": "LinkedIn Network MCP (CSV Mode)"}
        
        fastapi_root.mount("/", wrapped_sse_app)

        uvicorn.run(fastapi_root, host="0.0.0.0", port=port)
    else:
        # STDIO mode for Cursor
        print("🔧 Starting MCP server in STDIO mode (for Cursor)")
        mcp.run()