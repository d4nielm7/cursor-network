"""
LinkedIn Network MCP Server (Smarter Version)
Hosted on Railway - connects to Neon Postgres
Users only need their API_KEY; DATABASE_URL is configured on Railway
"""

from fastmcp import FastMCP
from fastmcp.server.http import create_sse_app
import asyncpg
import os
import json
import csv
import io
from typing import List
from dotenv import load_dotenv
from contextvars import ContextVar
from fastapi import FastAPI
import uvicorn
import pandas as pd

# ---------------------------
# Environment and setup
# ---------------------------
load_dotenv(override=False)
mcp = FastMCP("LinkedIn Network")

current_api_key: ContextVar[str | None] = ContextVar("current_api_key", default=None)
current_working_dir: ContextVar[str | None] = ContextVar("current_working_dir", default=None)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL must be set (Railway or .env)")

API_KEY = os.getenv("API_KEY")
APP_URL = os.getenv("APP_URL") or "https://web-production-e31ba.up.railway.app"

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
        raise Exception("API_KEY missing. Provide via 'X-API-Key' header or env.")
    return user_id

# ---------------------------
# Helper utilities
# ---------------------------

def get_output_directory() -> str:
    """
    Get the base directory for file outputs.
    Automatically detects where Cursor/MCP is running from.
    Uses WORKING_DIR from context (SSE headers) or environment variable, otherwise uses current working directory.
    """
    # First check if WORKING_DIR is in context (from SSE headers)
    working_dir = current_working_dir.get()
    if working_dir:
        os.makedirs(working_dir, exist_ok=True)
        return os.path.abspath(working_dir)
    
    # Then check environment variable
    working_dir = os.getenv("WORKING_DIR")
    if working_dir:
        os.makedirs(working_dir, exist_ok=True)
        return os.path.abspath(working_dir)
    
    # Otherwise, use current working directory (where Cursor/MCP is running)
    # This automatically detects the user's current workspace
    current_dir = os.getcwd()
    return os.path.abspath(current_dir)

def resolve_output_path(relative_path: str) -> str:
    """
    Resolve a relative path to an absolute path using the output directory.
    
    Args:
        relative_path: Relative path like "data/network.csv" or absolute path
        
    Returns:
        Absolute path to the file
    """
    # If already absolute, return as-is
    if os.path.isabs(relative_path):
        return relative_path
    
    # Otherwise, resolve relative to output directory
    base_dir = get_output_directory()
    return os.path.abspath(os.path.join(base_dir, relative_path))

def shell_cmd(cmd: str) -> str:
    """Formats a command-line example block."""
    return f"```bash\n{cmd}\n```"

def py_cmd(code: str) -> str:
    """Formats a Python example block."""
    return f"```python\n{code}\n```"

# ---------------------------
# Tools
# ---------------------------

@mcp.tool()
async def export_network_csv(output_path: str = "data/network.csv") -> str:
    """
    Export LinkedIn network to a CSV file.
    
    The CSV data is returned in the response for Cursor to save locally.
    The server NEVER writes files to disk - all file operations happen client-side.
    
    Args:
        output_path: Relative path where CSV should be saved (for reference only).
                     Defaults to "data/network.csv".
                     Cursor will save relative to its current working directory.
    
    Returns:
        JSON string with CSV data and metadata:
        {"status": "success", "csv_data": "...", "download_path": "data/network.csv", "save_locally": true, ...}
    """
    try:
        user_id = await get_user_id()
        pool = await get_db()

        async with pool.acquire() as conn:
            results = await conn.fetch(
                """
                SELECT 
                    full_name, email, linkedin_url, headline, about,
                    current_company, current_company_linkedin_url,
                    current_company_website_url, experiences, skills, education, keywords
                FROM people
                WHERE user_id = $1
                ORDER BY full_name
                """,
                user_id
            )

        if not results:
            return json.dumps({
                "status": "error",
                "message": "No contacts found in your LinkedIn network."
            })

        # Convert asyncpg results to pandas DataFrame
        # This ensures exact column matching and proper data handling
        df = pd.DataFrame([dict(row) for row in results])
        
        # Verify we have data
        if df.empty:
            return json.dumps({
                "status": "error",
                "message": "No contacts found in your LinkedIn network."
            })
        
        # Convert complex types (list/dict) to JSON strings for CSV compatibility
        # pandas handles None/NaN automatically
        for col in df.columns:
            if df[col].dtype == 'object':
                # Check if column contains lists or dicts
                mask = df[col].apply(lambda x: isinstance(x, (list, dict)) if pd.notna(x) else False)
                if mask.any():
                    df.loc[mask, col] = df.loc[mask, col].apply(lambda x: json.dumps(x, ensure_ascii=False) if pd.notna(x) else '')
        
        # Get counts from DataFrame (before converting to CSV)
        row_count = len(df)
        actual_column_count = len(df.columns)
        
        # Convert to CSV string (for client-side saving)
        csv_content = df.to_csv(index=False, encoding='utf-8', na_rep='', quoting=csv.QUOTE_MINIMAL)
        
        # Calculate size from CSV content
        size_kb = round(len(csv_content.encode('utf-8')) / 1024, 2)
        
        # Always return CSV data in response - never write to disk
        # Cursor will handle saving the file locally
        download_path = output_path  # e.g., "data/network.csv"
        
        message = (
            f"✅ Export completed.\n\n"
            f"📈 Total Contacts: {row_count}\n"
            f"📊 Columns: {actual_column_count}\n"
            f"💾 File Size: {size_kb} KB\n\n"
            f"📁 CSV data returned - will be saved to: {download_path}\n"
            f"📂 Relative to Cursor's current working directory.\n\n"
            f"The CSV content is included in this response for Cursor to save locally."
        )
        
        return json.dumps({
            "status": "success",
            "message": message,
            "csv_data": csv_content,  # CSV content for Cursor to save locally
            "download_path": download_path,  # Relative path like "data/network.csv"
            "row_count": row_count,
            "column_count": actual_column_count,
            "size_kb": size_kb,
            "save_locally": True  # Flag to indicate Cursor should save locally
        })
    except Exception as e:
        error_msg = str(e)
        return json.dumps({
            "status": "error",
            "message": f"Error exporting CSV: {error_msg}"
        })

# ---------------------------
# Deployment
# ---------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT") or "8000")

    if os.getenv("PORT"):
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
                    api_key = headers.get("x-api-key") or headers.get("authorization")
                    if api_key and api_key.lower().startswith("bearer "):
                        api_key = api_key.split(" ",1)[1].strip()
                    
                    # Extract WORKING_DIR from headers (for SSE mode)
                    working_dir = headers.get("working-dir") or headers.get("working_dir")
                    
                    # Set context variables
                    api_token = current_api_key.set(api_key)
                    working_dir_token = current_working_dir.set(working_dir) if working_dir else None
                    
                    try: 
                        await self.app(scope, receive, send)
                    finally: 
                        current_api_key.reset(api_token)
                        if working_dir_token:
                            current_working_dir.reset(working_dir_token)
                else: await self.app(scope, receive, send)

        fastapi_root = FastAPI()

        @fastapi_root.get("/")
        async def health():
            return {"status": "ok", "service": "LinkedIn Network MCP (smart)"}

        fastapi_root.mount("/", HeaderToContextMiddleware(sse_app))
        uvicorn.run(fastapi_root, host="0.0.0.0", port=port)
    else:
        print("🔧 Starting MCP server in STDIO mode (local)")
        mcp.run()
