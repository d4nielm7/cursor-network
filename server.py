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

load_dotenv(override=False)

mcp = FastMCP("LinkedIn Network CSV")

# Per-request API key storage
current_api_key: ContextVar[str | None] = ContextVar("current_api_key", default=None)

# Local CSV file path - store in user's home directory
CSV_FILE = Path.home() / "linkedin_network_export.csv"
DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY")

if not DATABASE_URL:
    raise Exception("DATABASE_URL must be set in .env file or Railway environment variables")

# Flag to track if we've exported
_exported = False

async def get_user_id():
    """Get user_id from context or env"""
    header_key = current_api_key.get()
    user_id = header_key or os.getenv("API_KEY") or API_KEY
    if not user_id:
        raise Exception("API_KEY not set. Provide it via 'API_KEY'/'X-API-Key' header or env.")
    return user_id

async def auto_export_to_csv():
    """Automatically export database to local CSV on first connection"""
    global _exported
    
    if _exported and CSV_FILE.exists():
        print(f"✅ CSV already exists at: {CSV_FILE}")
        return
    
    print("🔄 Downloading your LinkedIn network to CSV...")
    
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
            print("⚠️ No data found in database")
            return
        
        # Write to CSV
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=people[0].keys())
            writer.writeheader()
            
            for person in people:
                # Convert JSON fields to strings for CSV
                row = dict(person)
                for key in ['experiences', 'skills', 'education', 'keywords']:
                    if row.get(key):
                        row[key] = json.dumps(row[key], default=str)
                writer.writerow(row)
        
        _exported = True
        print(f"✅ Exported {len(people)} contacts to: {CSV_FILE}")
        
    except Exception as e:
        print(f"❌ Export failed: {e}")
        raise

def load_csv_data():
    """Load CSV data into pandas DataFrame"""
    if not CSV_FILE.exists():
        raise Exception(f"CSV not found at {CSV_FILE}. Please use the initialize() tool first.")
    
    return pd.read_csv(CSV_FILE)

# -------------------------------------------------------------------
# TOOLS - Now work with LOCAL CSV data
# -------------------------------------------------------------------

@mcp.tool()
async def initialize() -> str:
    """
    Initialize the MCP by downloading your LinkedIn network to CSV.
    This should be called first when connecting to the MCP.
    """
    await auto_export_to_csv()
    
    if CSV_FILE.exists():
        df = load_csv_data()
        return json.dumps({
            "status": "ready",
            "message": f"LinkedIn network loaded: {len(df)} contacts",
            "csv_location": str(CSV_FILE)
        }, indent=2)
    else:
        return json.dumps({
            "status": "error",
            "message": "Failed to export CSV"
        }, indent=2)

@mcp.tool()
async def search_network(query: str, limit: int = 10) -> str:
    """
    Search your LinkedIn network CSV by name, job title, company, or keywords.
    Data is loaded from your local CSV file.
    
    Examples:
    - search_network("AI", limit=20)
    - search_network("Google")
    - search_network("founder")
    """
    df = load_csv_data()
    
    # Search across multiple columns
    mask = (
        df['full_name'].str.contains(query, case=False, na=False) |
        df['headline'].str.contains(query, case=False, na=False) |
        df['about'].str.contains(query, case=False, na=False) |
        df['current_company'].str.contains(query, case=False, na=False) |
        df['keywords'].str.contains(query, case=False, na=False) |
        df['skills'].str.contains(query, case=False, na=False)
    )
    
    results = df[mask].head(limit)
    
    if results.empty:
        return json.dumps({"message": f"No results found for: {query}"}, indent=2)
    
    # Convert to dict and format
    return results.to_json(orient='records', indent=2)

@mcp.tool()
async def get_profile(name: str) -> str:
    """
    Get detailed profile for a specific person from CSV.
    
    Example:
    - get_profile("Chen Katz")
    """
    df = load_csv_data()
    
    mask = df['full_name'].str.contains(name, case=False, na=False)
    result = df[mask].head(1)
    
    if result.empty:
        return json.dumps({"error": f"No profile found for: {name}"}, indent=2)
    
    return result.to_json(orient='records', indent=2)

@mcp.tool()
async def filter_by_keywords(keywords: List[str], limit: int = 20) -> str:
    """
    Filter network by keywords from CSV.
    
    Example:
    - filter_by_keywords(["ai", "founder"], limit=20)
    """
    df = load_csv_data()
    
    # Create mask for any keyword match
    mask = pd.Series([False] * len(df))
    for keyword in keywords:
        mask |= df['keywords'].str.contains(keyword, case=False, na=False)
    
    results = df[mask].head(limit)
    
    if results.empty:
        return json.dumps({"message": f"No results found for keywords: {keywords}"}, indent=2)
    
    return results.to_json(orient='records', indent=2)

@mcp.tool()
async def analyze_network() -> str:
    """
    Get statistics and insights about your LinkedIn network from CSV.
    """
    df = load_csv_data()
    
    stats = {
        "overview": {
            "total_connections": int(len(df)),
            "unique_companies": int(df['current_company'].nunique()),
            "has_email": int(df['email'].notna().sum()),
            "has_linkedin_url": int(df['linkedin_url'].notna().sum())
        }
    }
    
    # Top companies
    top_companies = df['current_company'].value_counts().head(10)
    stats['top_companies'] = [
        {"company": company, "count": int(count)} 
        for company, count in top_companies.items()
    ]
    
    # Parse keywords if JSON
    try:
        all_keywords = []
        for kw_str in df['keywords'].dropna():
            try:
                kw_list = json.loads(kw_str)
                if isinstance(kw_list, list):
                    all_keywords.extend([k for k in kw_list if k and str(k).strip().lower() != 'null'])
            except:
                pass
        
        from collections import Counter
        keyword_counts = Counter(all_keywords)
        stats['top_keywords'] = [
            {"keyword": kw, "count": count}
            for kw, count in keyword_counts.most_common(10)
        ]
    except Exception as e:
        stats['top_keywords'] = []
    
    return json.dumps(stats, indent=2)

@mcp.tool()
async def export_network_table(limit: int = 50) -> str:
    """
    Export network as markdown table from CSV for easy viewing in Cursor.
    
    Args:
        limit: Maximum number of contacts to display (default: 50)
    """
    df = load_csv_data()
    
    # Select and format columns
    display_df = df[['full_name', 'email', 'linkedin_url', 'current_company', 'headline']].head(limit)
    
    # Clean up data for display
    display_df = display_df.fillna('')
    
    # Truncate long fields
    display_df['headline'] = display_df['headline'].str[:50]
    display_df['current_company'] = display_df['current_company'].str[:40]
    
    # Convert to markdown table
    return display_df.to_markdown(index=False)

@mcp.tool()
async def refresh_csv() -> str:
    """
    Re-download and refresh the CSV from the database.
    Use this if you want to sync latest data from LinkedIn.
    """
    global _exported
    _exported = False
    
    if CSV_FILE.exists():
        CSV_FILE.unlink()
        print(f"🗑️ Deleted old CSV at: {CSV_FILE}")
    
    await auto_export_to_csv()
    
    if CSV_FILE.exists():
        df = load_csv_data()
        return json.dumps({
            "status": "success",
            "message": f"CSV refreshed with {len(df)} contacts",
            "location": str(CSV_FILE)
        }, indent=2)
    else:
        return json.dumps({
            "status": "error",
            "message": "Failed to refresh CSV"
        }, indent=2)

@mcp.tool()
async def get_csv_location() -> str:
    """
    Get the path to your local LinkedIn network CSV file.
    """
    exists = CSV_FILE.exists()
    size_mb = round(CSV_FILE.stat().st_size / 1024 / 1024, 2) if exists else 0
    
    return json.dumps({
        "csv_path": str(CSV_FILE),
        "exists": exists,
        "size_mb": size_mb,
        "row_count": len(load_csv_data()) if exists else 0
    }, indent=2)

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
        async def health(): return {"status":"ok","service":"LinkedIn Network MCP (CSV Mode)"}
        fastapi_root.mount("/", wrapped_sse_app)

        uvicorn.run(fastapi_root, host="0.0.0.0", port=port)
    else:
        # STDIO mode for Cursor
        print("🔧 Starting MCP server in STDIO mode (for Cursor)")
        print("💡 Use the 'initialize' tool first to download your network to CSV")
        mcp.run()