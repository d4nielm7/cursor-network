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
    Uses WORKING_DIR environment variable if set, otherwise uses current directory.
    """
    working_dir = os.getenv("WORKING_DIR")
    if working_dir:
        # Ensure the directory exists
        os.makedirs(working_dir, exist_ok=True)
        return os.path.abspath(working_dir)
    return os.getcwd()

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
    Export LinkedIn network to a local CSV file or provide a ready-to-run download command.
    
    The CSV data is written directly to the filesystem (not returned in the response).
    Only metadata (status, path, row count) is returned through the MCP protocol.
    
    Args:
        output_path: Relative or absolute path where CSV will be saved. 
                     Defaults to "data/network.csv".
                     If WORKING_DIR env var is set, relative paths are resolved relative to it.
                     Otherwise, paths are relative to the MCP server's current directory.
    
    Returns:
        JSON string with metadata: {"status": "success", "path": "/absolute/path/to/file.csv", "row_count": 150, "size_kb": 45.2}
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

        # Resolve the output path (handles WORKING_DIR and absolute paths)
        absolute_file_path = resolve_output_path(output_path)
        
        # Ensure the directory exists
        file_dir = os.path.dirname(absolute_file_path)
        os.makedirs(file_dir, exist_ok=True)

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
        
        # Write CSV using pandas - ensures accurate column matching and row count
        df.to_csv(
            absolute_file_path,
            index=False,  # Don't include row index
            encoding='utf-8',
            na_rep='',  # Replace NaN with empty string
            quoting=csv.QUOTE_MINIMAL  # Only quote when necessary
        )
        
        # Verify the file was written correctly by reading it back
        # This ensures accurate row/column counts
        df_verify = pd.read_csv(absolute_file_path)
        actual_row_count = len(df_verify)
        actual_column_count = len(df_verify.columns)
        
        size_kb = round(os.path.getsize(absolute_file_path) / 1024, 2)
        row_count = actual_row_count  # Use verified count from CSV file

        # Build smart response
        if os.getenv("PORT"):  # Running on Railway
            # Check if WORKING_DIR is provided in headers (SSE mode - client wants local file)
            working_dir_from_header = None
            try:
                # Try to get WORKING_DIR from context if available
                working_dir_from_header = os.getenv("WORKING_DIR")
            except:
                pass
            
            # If WORKING_DIR is set, try to download CSV to local machine
            if working_dir_from_header:
                try:
                    import requests
                    download_url = f"{APP_URL}/export/network.csv"
                    download_path = resolve_output_path(output_path)
                    download_dir = os.path.dirname(download_path)
                    os.makedirs(download_dir, exist_ok=True)
                    
                    # Download CSV from Railway to local machine
                    resp = requests.get(download_url, headers={"X-API-Key": user_id}, timeout=30)
                    if resp.status_code == 200:
                        with open(download_path, 'wb') as f:
                            f.write(resp.content)
                        
                        message = (
                            f"✅ Export completed and downloaded to your local machine!\n\n"
                            f"📁 File saved to: {download_path}\n"
                            f"📂 Working directory: {working_dir_from_header}\n"
                            f"📈 Total Contacts: {row_count}\n"
                            f"📊 Columns: {actual_column_count}\n"
                            f"💾 File Size: {size_kb} KB\n\n"
                            f"The CSV was downloaded from Railway and saved locally."
                        )
                        
                        return json.dumps({
                            "status": "success",
                            "message": message,
                            "path": download_path,
                            "row_count": row_count,
                            "column_count": actual_column_count,
                            "size_kb": size_kb,
                            "working_dir": working_dir_from_header
                        })
                except Exception as download_error:
                    # If download fails, fall through to manual download instructions
                    pass
            
            # Manual download instructions (fallback)
            curl_example = shell_cmd(
                f"curl -H 'X-API-Key: {user_id}' "
                f"-o linkedin_network.csv {APP_URL}/export/network.csv"
            )
            python_example = py_cmd(
                f"import requests\n\n"
                f"resp = requests.get('{APP_URL}/export/network.csv', headers={{'X-API-Key': '{user_id}'}})\n"
                f"open('linkedin_network.csv', 'wb').write(resp.content)\n"
                f"print('✅ Downloaded linkedin_network.csv')"
            )

            message = (
                f"✅ Export completed.\n\n"
                f"📈 Total Contacts: {row_count}\n"
                f"📊 Columns: {actual_column_count}\n"
                f"💾 Estimated Size: {size_kb} KB\n\n"
                f"Use one of the commands below to download your CSV:\n\n"
                f"**Command line (curl):**\n{curl_example}\n\n"
                f"**Python script:**\n{python_example}\n\n"
                f"🔗 Live download: {APP_URL}/export/network.csv"
            )
            
            # Return metadata only (for Railway, we don't have local file path)
            return json.dumps({
                "status": "success",
                "message": message,
                "row_count": row_count,
                "column_count": actual_column_count,
                "size_kb": size_kb
            })

        else:  # Local mode
            working_dir = os.getenv("WORKING_DIR")
            if working_dir:
                message = (
                    f"✅ Export completed locally.\n\n"
                    f"📁 File saved to: {absolute_file_path}\n"
                    f"📂 Working directory: {working_dir}\n"
                    f"📈 Total Contacts: {row_count}\n"
                    f"📊 Columns: {actual_column_count}\n"
                    f"💾 File Size: {size_kb} KB\n\n"
                    f"The CSV data was written directly to the filesystem (not sent through MCP)."
                )
            else:
                message = (
                    f"✅ Export completed locally.\n\n"
                    f"📁 File saved to: {absolute_file_path}\n"
                    f"📈 Total Contacts: {row_count}\n"
                    f"📊 Columns: {actual_column_count}\n"
                    f"💾 File Size: {size_kb} KB\n\n"
                    f"💡 Tip: Set WORKING_DIR in your .mcp.json to control where files are saved."
                )

            # Return metadata only - CSV data is already written to disk
            return json.dumps({
                "status": "success",
                "message": message,
                "path": absolute_file_path,  # Always return absolute path
                "row_count": row_count,
                "column_count": actual_column_count,
                "size_kb": size_kb,
                "working_dir": working_dir if working_dir else os.getcwd()
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
                    token = current_api_key.set(api_key)
                    try: await self.app(scope, receive, send)
                    finally: current_api_key.reset(token)
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
