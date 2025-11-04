import os
import csv
import json
import asyncpg
import subprocess
from fastmcp import FastMCP
from fastmcp.server.http import create_sse_app
from dotenv import load_dotenv
from contextvars import ContextVar
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from starlette.types import ASGIApp, Receive, Scope, Send
import uvicorn
import sys

load_dotenv(override=False)
mcp = FastMCP("LinkedIn Network")

DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY")
current_api_key: ContextVar[str | None] = ContextVar("current_api_key", default=None)

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

@mcp.tool()
async def export_network_csv_to_file(filepath: str = "network.csv") -> str:
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
        return f"No contacts found. Nothing written."

    contacts = []
    for row in results:
        contact = {}
        for key in row.keys():
            value = row[key]
            if value is None:
                contact[key] = ""
            elif isinstance(value, list):
                contact[key] = ", ".join(map(str, value)).replace('\n', ' ').replace('\r', ' ')
            elif isinstance(value, dict):
                contact[key] = json.dumps(value, ensure_ascii=False).replace('\n', ' ').replace('\r', ' ')
            else:
                contact[key] = str(value).replace('\n', ' ').replace('\r', ' ')
        contacts.append(contact)

    columns = list(contacts[0].keys())
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL, lineterminator='\n')
        writer.writerow(columns)
        for contact in contacts:
            writer.writerow([contact.get(col, "") for col in columns])

    # If running locally and want to auto-download via curl or other shell
    # Check environment variable or argument to decide if auto-run curl
    if os.getenv("RUN_CURL") == "yes":
        curl_url = "http://localhost:8000/file-csv"
        curl_output = os.path.join(os.path.dirname(filepath), "downloaded_network.csv")
        try:
            subprocess.run([
                "curl", "-o", curl_output, curl_url,
                "-H", f"X-API-Key: {API_KEY}"
            ], check=True)
            return f"CSV exported to {filepath}. Curl download successful: {curl_output}"
        except Exception as e:
            return f"CSV exported to {filepath}. Curl download failed: {e}"

    server_url = "https://web-production-e31ba.up.railway.app"
    return (
        f"CSV with {len(contacts)} contacts exported. "
        f"Download here: {server_url}/file-csv"
    )


class APIKeyMiddleware:
    """Custom middleware that doesn't interfere with streaming responses."""
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            request = Request(scope, receive)
            api_key = request.headers.get("X-API-Key")
            if api_key:
                current_api_key.set(api_key)
        await self.app(scope, receive, send)

def main():
    port = int(os.getenv("PORT") or "8000")
    if os.getenv("PORT"):
        fastapi_root = FastAPI()

        sse_app = create_sse_app(
            mcp,
            message_path="/messages/",
            sse_path="/sse",
        )

        @fastapi_root.get("/")
        async def health():
            return {"status": "ok", "service": "LinkedIn Network MCP (smart)"}

        @fastapi_root.get("/file-csv")
        async def file_csv():
            file_path = "network.csv"
            if not os.path.isfile(file_path):
                return {"status": "error", "message": f"File '{file_path}' not found."}
            return FileResponse(
                path=file_path,
                media_type='text/csv',
                filename='network.csv',
                headers={"Content-Disposition": "attachment; filename=network.csv"}
            )

        # Mount SSE app - routes defined above take precedence
        fastapi_root.mount("/", sse_app)
        
        # Wrap the entire app with custom middleware
        app_with_middleware = APIKeyMiddleware(fastapi_root)
        uvicorn.run(app_with_middleware, host="0.0.0.0", port=port)
    else:
        print("🔧 Starting MCP server in STDIO mode (local)")
        mcp.run()

if __name__ == "__main__":
    main()
