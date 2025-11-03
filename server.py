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
from typing import List
from dotenv import load_dotenv
from contextvars import ContextVar
from fastapi import FastAPI
import uvicorn

from fastapi.responses import StreamingResponse
import io
import csv

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
# Download CSV Endpoint (NEW)
# ---------------------------
# Insert into your FastAPI app part:

# This section replaces separate CSV writers and doesn't need file/directory checks.

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

        # ------- NEW CSV DOWNLOAD ENDPOINT -------
        @fastapi_root.get("/download-csv")
        async def download_csv():
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
                return {"status": "error", "message": "No contacts found."}

            # Convert results to dict
            contacts = []
            for row in results:
                contact = {}
                for key in row.keys():
                    value = row[key]
                    if value is None:
                        contact[key] = ""
                    elif isinstance(value, (list, dict)):
                        contact[key] = json.dumps(value, ensure_ascii=False)
                    else:
                        contact[key] = value
                contacts.append(contact)

            output = io.StringIO()
            columns = list(contacts[0].keys())
            writer = csv.writer(output)
            writer.writerow(columns)
            for contact in contacts:
                writer.writerow([
                    str(contact.get(col, "")) if contact.get(col) is not None else ""
                    for col in columns
                ])
            output.seek(0)
            headers = {"Content-Disposition": "attachment; filename=network.csv"}
            return StreamingResponse(output, media_type='text/csv', headers=headers)
        # ----------------------------------------

        fastapi_root.mount("/", HeaderToContextMiddleware(sse_app))
        uvicorn.run(fastapi_root, host="0.0.0.0", port=port)
    else:
        print("🔧 Starting MCP server in STDIO mode (local)")
        mcp.run()
