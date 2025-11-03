import os
import json
import csv
import io
import asyncpg
from fastmcp import FastMCP
from fastmcp.server.http import create_sse_app
from dotenv import load_dotenv
from contextvars import ContextVar

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
    # Write to disk
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL, lineterminator='\n')
        writer.writerow(columns)
        for contact in contacts:
            writer.writerow([contact.get(col, "") for col in columns])
    return f"CSV with {len(contacts)} contacts written to {os.path.abspath(filepath)}"

# MCP/HTTP server bootstrapping is the same as before...
# Add the tool call to your desired toolset or UI.
