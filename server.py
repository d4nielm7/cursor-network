import os
import csv
import json
import asyncpg
import subprocess
import hashlib
import hmac
import base64
from fastmcp import FastMCP
from fastmcp.server.http import create_sse_app
from dotenv import load_dotenv
from contextvars import ContextVar
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import FileResponse
from starlette.types import ASGIApp, Receive, Scope, Send
import uvicorn
import sys

load_dotenv(override=False)
mcp = FastMCP("LinkedIn Network")

# Default cloud database URL (can be overridden via DATABASE_URL env var)
DEFAULT_DATABASE_URL = "postgresql://neondb_owner:npg_fJD7CWt6VnTQ@ep-twilight-sun-aho2mfyf-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
DATABASE_URL = os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
API_KEY = os.getenv("API_KEY")
# Secret key for generating unique download tokens (should be set in production)
DOWNLOAD_SECRET = os.getenv("DOWNLOAD_SECRET", "default-secret-change-in-production")
# Directory where CSV files should be saved (defaults to current directory)
# Supports both OUT_DIR and SAVE_DIRECTORY (OUT_DIR takes precedence)
SAVE_DIRECTORY = os.getenv("OUT_DIR") or os.getenv("SAVE_DIRECTORY") or os.getcwd()
current_api_key: ContextVar[str | None] = ContextVar("current_api_key", default=None)

# In-memory store for token -> user_id mapping
# In production, consider using Redis or database for persistence
token_store: dict[str, str] = {}

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

def get_user_file_path(user_id: str) -> str:
    """Generate a unique filename for a user based on their user_id"""
    # Create a hash of the user_id for a unique but consistent filename
    hash_obj = hashlib.sha256(user_id.encode())
    user_hash = hash_obj.hexdigest()[:16]
    return f"network_{user_hash}.csv"

def generate_download_token(user_id: str) -> str:
    """Generate a unique, secure download token for a user"""
    # Create a deterministic token using HMAC of user_id
    # This ensures same user always gets same token (consistent)
    token = _compute_token(user_id)
    
    # Store mapping for quick lookup
    token_store[token] = user_id
    
    return token

def _compute_token(user_id: str) -> str:
    """Compute token without side effects (for verification)"""
    token_bytes = hmac.new(
        DOWNLOAD_SECRET.encode(),
        user_id.encode(),
        hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(token_bytes).decode().rstrip('=')[:32]

async def get_user_id_from_token(token: str) -> str | None:
    """Verify token and return user_id if valid, None otherwise"""
    # First check in-memory store
    if token in token_store:
        return token_store[token]
    
    # If not in store, verify token by checking database
    # We'll try to verify by checking if token matches any user_id
    pool = await get_db()
    async with pool.acquire() as conn:
        # Get all user_ids from database and verify token
        user_ids = await conn.fetch("SELECT DISTINCT user_id FROM people")
        for row in user_ids:
            user_id = row['user_id']
            expected_token = _compute_token(user_id)
            if expected_token == token:
                # Cache it for future lookups
                token_store[token] = user_id
                return user_id
    
    return None

@mcp.tool()
async def export_network_csv_to_file(filepath: str = "network.csv") -> str:
    """
    Export LinkedIn network data to a CSV file in the configured directory.
    
    Args:
        filepath: Optional filepath. Defaults to 'network.csv' in configured directory.
    
    Returns:
        Success message with file path and contact count.
    """
    user_id = await get_user_id()
    
    # Use configured save directory or current working directory
    save_dir = SAVE_DIRECTORY
    if not os.path.isabs(save_dir):
        # If relative path, make it relative to current directory
        save_dir = os.path.join(os.getcwd(), save_dir)
    
    # Ensure save directory exists
    os.makedirs(save_dir, exist_ok=True)
    
    # If default filename is used, save to configured directory
    if filepath == "network.csv":
        filepath = os.path.join(save_dir, "network.csv")
    else:
        # If relative path, make it relative to save directory
        if not os.path.isabs(filepath):
            filepath = os.path.join(save_dir, filepath)
    
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
    
    return (
        f"CSV file exported successfully to {filepath}. "
        f"Total contacts: {len(contacts)}"
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
        async def file_csv(x_api_key: str = Header(None, alias="X-API-Key")):
            """Legacy endpoint - still supports header-based auth"""
            # Require API key for authentication
            if not x_api_key:
                raise HTTPException(status_code=401, detail="X-API-Key header required")
            
            # Get user_id from API key (API key is the user_id)
            user_id = x_api_key
            
            # Generate unique file path for this user
            file_path = get_user_file_path(user_id)
            
            if not os.path.isfile(file_path):
                return {"status": "error", "message": f"File for user not found. Please export your network first."}
            
            return FileResponse(
                path=file_path,
                media_type='text/csv',
                filename='network.csv',
                headers={"Content-Disposition": "attachment; filename=network.csv"}
            )
        
        @fastapi_root.get("/download/{token}")
        async def download_csv(token: str):
            """New endpoint with unique token-based authentication - no headers needed!"""
            # Get user_id from token
            user_id = await get_user_id_from_token(token)
            
            if not user_id:
                raise HTTPException(
                    status_code=404, 
                    detail="Invalid download token. Please export your network again to get a new link."
                )
            
            # Generate unique file path for this user
            file_path = get_user_file_path(user_id)
            
            if not os.path.isfile(file_path):
                raise HTTPException(
                    status_code=404,
                    detail="File not found. Please export your network first."
                )
            
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
