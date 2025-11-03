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
import pandas as pd
from typing import List
from dotenv import load_dotenv
from contextvars import ContextVar
from fastapi import FastAPI
import uvicorn

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
    # Find or create base directory for outputs
    working_dir = current_working_dir.get()
    if working_dir:
        os.makedirs(working_dir, exist_ok=True)
        return os.path.abspath(working_dir)
    working_dir = os.getenv("WORKING_DIR")
    if working_dir:
        os.makedirs(working_dir, exist_ok=True)
        return os.path.abspath(working_dir)
    return os.path.abspath(os.getcwd())

def resolve_output_path(relative_path: str) -> str:
    if os.path.isabs(relative_path):
        return relative_path
    base_dir = get_output_directory()
    return os.path.abspath(os.path.join(base_dir, relative_path))

# ---------- CSV Writer Utility ---------------

def write_contacts_to_csv(contacts, csv_path: str):
    import json
    import pandas as pd
    # Stringify list/dicts, None as ""
    def conv(val):
        if val is None:
            return ""
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return val
    if not contacts:
        raise ValueError("No contacts to write")
    records = [{k: conv(v) for k, v in contact.items()} for contact in contacts]
    df = pd.DataFrame(records)
    df.to_csv(csv_path, encoding='utf-8', index=False)

# ---------------------------
# Tools
# ---------------------------

@mcp.tool()
async def export_network_csv() -> str:
    """
    Export LinkedIn network to CSV file.
    Retrieves all contacts from the database and returns them as JSON.
    Also writes a CSV file to data/network.csv for download.
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

        # Convert asyncpg Row objects to plain Python dicts
        contacts = []
        for row in results:
            contact = {}
            for key in row.keys():
                value = row[key]
                if value is None:
                    contact[key] = None
                elif isinstance(value, (list, dict)):
                    contact[key] = json.dumps(value, ensure_ascii=False)
                else:
                    contact[key] = value
            contacts.append(contact)
        row_count = len(contacts)
        column_count = len(contacts[0].keys()) if contacts else 0

        # Write CSV file
        csv_path = "network.csv"
        try:
            write_contacts_to_csv(contacts, csv_path)
            csv_message = f"\nCSV created at: {csv_path}"
        except Exception as e:
            csv_message = f"\nCSV creation failed: {e}"

        return json.dumps({
            "status": "success",
            "message": f"✅ Data retrieved successfully.{csv_message}\n📈 Total Contacts: {row_count}\n📊 Columns: {column_count}",
            "data": contacts,
            "row_count": row_count,
            "column_count": column_count
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
                    working_dir = headers.get("working-dir") or headers.get("working_dir")
                    api_token = current_api_key.set(api_key)
                    working_dir_token = current_working_dir.set(working_dir) if working_dir else None
                    try: 
                        await self.app(scope, receive, send)
                    except Exception as e:
                        print(f"Error in middleware: {e}")
                    finally: 
                        if api_token:
                            try:
                                current_api_key.reset(api_token)
                            except ValueError:
                                pass
                        if working_dir_token:
                            try:
                                current_working_dir.reset(working_dir_token)
                            except ValueError:
                                pass

        fastapi_root = FastAPI()

        @fastapi_root.get("/")
        async def health():
            return {"status": "ok", "service": "LinkedIn Network MCP (smart)"}

        fastapi_root.mount("/", HeaderToContextMiddleware(sse_app))
        uvicorn.run(fastapi_root, host="0.0.0.0", port=port)
    else:
        print("🔧 Starting MCP server in STDIO mode (local)")
        mcp.run()
