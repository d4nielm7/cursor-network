import os
import csv
import json
import httpx
from fastmcp import FastMCP
from dotenv import load_dotenv
from contextvars import ContextVar

load_dotenv(override=False)
mcp = FastMCP("LinkedIn Network")

# Architecture: MCP Client → Backend API → Database → Backend → MCP Client
# This MCP server does NOT connect directly to the database.
# It makes HTTP requests to the backend server, which handles all database operations.

# Backend server URL (hardcoded, not configurable via env)
BACKEND_URL = "https://web-production-e31ba.up.railway.app"
# Directory where CSV files should be saved (defaults to current directory)
OUT_DIR = os.getenv("OUT_DIR") or os.getcwd()
# UUID from header (set by MCP client via mcp.json env)
current_uuid: ContextVar[str | None] = ContextVar("current_uuid", default=None)

async def get_uuid():
    """Get UUID from context or environment"""
    uuid = current_uuid.get()
    if not uuid:
        uuid = os.getenv("UUID")
    if not uuid:
        raise Exception("UUID missing. Provide via 'X-UUID' header or env.")
    return uuid

@mcp.tool()
async def export_network_csv_to_file(filepath: str = "network.csv") -> str:
    """
    Export LinkedIn network data to a CSV file.
    Fetches data from backend server using UUID header.
    
    Args:
        filepath: Optional filepath. Defaults to 'network.csv' in OUT_DIR.
    
    Returns:
        Success message with file path and contact count.
    """
    uuid = await get_uuid()
    
    # Get save directory
    save_dir = OUT_DIR
    if not os.path.isabs(save_dir):
        save_dir = os.path.join(os.getcwd(), save_dir)
    os.makedirs(save_dir, exist_ok=True)
    
    # Set filepath
    if filepath == "network.csv":
        filepath = os.path.join(save_dir, "network.csv")
    else:
        if not os.path.isabs(filepath):
            filepath = os.path.join(save_dir, filepath)
    
    # Fetch network data from backend server via HTTP API
    # Backend server handles database queries and returns JSON response
    # Flow: MCP → HTTP GET → Backend → Database → Backend → JSON → MCP → CSV
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{BACKEND_URL}/api/network",
                headers={"X-UUID": uuid},
                timeout=30.0
            )
            response.raise_for_status()
            # Backend returns JSON array of contacts (already processed from database)
            contacts = response.json()
        except httpx.HTTPError as e:
            return f"Error fetching network from backend: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    if not contacts:
        return f"No contacts found. Nothing written."
    
    # Write CSV file
    if not isinstance(contacts, list) or len(contacts) == 0:
        return f"No contacts found. Nothing written."
    
    columns = list(contacts[0].keys())
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL, lineterminator='\n')
        writer.writerow(columns)
        for contact in contacts:
            row = []
            for col in columns:
                value = contact.get(col, "")
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False).replace('\n', ' ').replace('\r', ' ')
                elif value is None:
                    value = ""
                else:
                    value = str(value).replace('\n', ' ').replace('\r', ' ')
                row.append(value)
            writer.writerow(row)
    
    return (
        f"CSV file exported successfully to {filepath}. "
        f"Total contacts: {len(contacts)}"
    )

def main():
    print("🔧 Starting MCP server in STDIO mode (local)")
    mcp.run()

if __name__ == "__main__":
    main()
