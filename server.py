import os
import csv
import json
import asyncpg
from fastmcp import FastMCP
from fastmcp.server.http import create_sse_app
from dotenv import load_dotenv
from contextvars import ContextVar
from fastapi import FastAPI
from fastapi.responses import FileResponse
import uvicorn

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
    """
    Export LinkedIn network to CSV file on the server filesystem.
    """
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
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL, lineterminator='\n')
        writer.writerow(columns)
        for contact in contacts:
            writer.writerow([contact.get(col, "") for col in columns])
    return f"CSV with {len(contacts)} contacts written to {os.path.abspath(filepath)}"

# ---------- FastAPI for CSV Download ----------

if __name__ == "__main__":
    port = int(os.getenv("PORT") or "8000")
    if os.getenv("PORT"):
        sse_app = create_sse_app(
            mcp,
            message_path="/messages/",
            sse_path="/sse",
        )

        fastapi_root = FastAPI()

        @fastapi_root.get("/")
        async def health():
            return {"status": "ok", "service": "LinkedIn Network MCP (smart)"}

        @fastapi_root.get("/file-csv")
        async def file_csv():
            """Download the already-generated CSV file from server."""
            file_path = "network.csv"
            if not os.path.isfile(file_path):
                return {"status": "error", "message": f"File '{file_path}' not found."}
            return FileResponse(
                path=file_path,
                media_type='text/csv',
                filename='network.csv',
                headers={"Content-Disposition": "attachment; filename=network.csv"}
            )

        fastapi_root.mount("/", sse_app)
        uvicorn.run(fastapi_root, host="0.0.0.0", port=port)
    else:
        print("🔧 Starting MCP server in STDIO mode (local)")
        mcp.run()
