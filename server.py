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
async def export_network_csv() -> str:
    """
    Export LinkedIn network to a local CSV file or provide a ready-to-run download command.

    When running locally → saves to ./data/network.csv  
    When on Railway → gives a curl command and a Python snippet to download the CSV.
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

        # Local export (for dev or Cursor STDIO mode)
        os.makedirs("data", exist_ok=True)
        file_path = "data/network.csv"

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Full Name","Email","LinkedIn URL","Headline","About",
                "Current Company","Current Company LinkedIn URL","Current Company Website URL",
                "Experiences","Skills","Education","Keywords"
            ])

            def fmt(v):
                if v is None:
                    return ""
                if isinstance(v, (list, dict)):
                    return json.dumps(v, ensure_ascii=False)
                return str(v)

            for row in results:
                writer.writerow([
                    fmt(row.get("full_name")),
                    fmt(row.get("email")),
                    fmt(row.get("linkedin_url")),
                    fmt(row.get("headline")),
                    fmt(row.get("about")),
                    fmt(row.get("current_company")),
                    fmt(row.get("current_company_linkedin_url")),
                    fmt(row.get("current_company_website_url")),
                    fmt(row.get("experiences")),
                    fmt(row.get("skills")),
                    fmt(row.get("education")),
                    fmt(row.get("keywords")),
                ])

        size_kb = round(os.path.getsize(file_path) / 1024, 2)
        row_count = len(results)

        # Build smart response
        if os.getenv("PORT"):  # Running on Railway
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
                f"💾 Estimated Size: {size_kb} KB\n\n"
                f"Use one of the commands below to download your CSV:\n\n"
                f"**Command line (curl):**\n{curl_example}\n\n"
                f"**Python script:**\n{python_example}\n\n"
                f"🔗 Live download: {APP_URL}/export/network.csv"
            )

        else:  # Local mode
            message = (
                f"✅ Export completed locally.\n\n"
                f"📁 File saved to: {file_path}\n"
                f"📈 Total Contacts: {row_count}\n"
                f"💾 File Size: {size_kb} KB\n\n"
                f"Run this command to open it:\n{shell_cmd('open data/network.csv')}"
            )

        return json.dumps({
            "status": "success",
            "message": message,
            "path": file_path,
            "row_count": row_count,
            "size_kb": size_kb
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
