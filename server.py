import os
import csv
import json
import httpx
from fastmcp import FastMCP
from dotenv import load_dotenv
from contextvars import ContextVar
from pathlib import Path

load_dotenv(override=False)
mcp = FastMCP("LinkedIn Network")

def load_mcp_config():
    mcp_json_path = Path.home() / ".cursor" / "mcp.json"
    
    if not mcp_json_path.exists():
        return None, None
    
    try:
        with open(mcp_json_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        server_config = config.get("mcpServers", {}).get("network-mcp-node", {})
        env = server_config.get("env", {})
        
        uuid = env.get("UUID")
        out_dir = env.get("OUT_DIR")
        
        return uuid, out_dir
    except Exception:
        return None, None

_mcp_uuid, _mcp_out_dir = load_mcp_config()

OUT_DIR = os.getenv("OUT_DIR") or _mcp_out_dir or os.getcwd()

current_uuid: ContextVar[str | None] = ContextVar("current_uuid", default=None)
_MCP_UUID = _mcp_uuid

BACKEND_URL = os.getenv(
    "BACKEND_URL",
    "https://web-production-e31ba.up.railway.app"
)

async def get_uuid():
    uuid = current_uuid.get()
    if not uuid:
        uuid = os.getenv("UUID")
    if not uuid:
        uuid = _MCP_UUID
    if not uuid:
        raise Exception("UUID missing. Provide via 'X-UUID' header, env var, or mcp.json.")
    return uuid

async def _download_csv_impl(
    out_dir: str = "",
    table: str = "people",
    filename: str = "",
    use_uuid_filter: bool = True
) -> str:
    uuid = None
    if use_uuid_filter:
        try:
            uuid = await get_uuid()
        except Exception:
            uuid = None
    
    if not uuid:
        return "Error: UUID is required to fetch data from backend."
    
    save_dir = out_dir or OUT_DIR
    if not os.path.isabs(save_dir):
        save_dir = os.path.join(os.getcwd(), save_dir)
    os.makedirs(save_dir, exist_ok=True)
    
    csv_filename = filename or f"{table}.csv"
    filepath = os.path.join(save_dir, csv_filename)
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BACKEND_URL}/api/network",
                headers={"X-UUID": uuid},
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
        
        if not data:
            return f"No records found. Nothing written."
        
        if not isinstance(data, list):
            return f"Error: Backend returned unexpected data format. Expected list, got {type(data).__name__}."
        
        if len(data) == 0:
            return f"No records found. Nothing written."
        
        columns = list(data[0].keys())
        
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL, lineterminator='\n')
            writer.writerow(columns)
            for row in data:
                csv_row = []
                for col in columns:
                    value = row.get(col, "")
                    if isinstance(value, (list, dict)):
                        value = json.dumps(value, ensure_ascii=False).replace('\n', ' ').replace('\r', ' ')
                    elif value is None:
                        value = ""
                    else:
                        value = str(value).replace('\n', ' ').replace('\r', ' ')
                    csv_row.append(value)
                writer.writerow(csv_row)
        
        cwd = os.getcwd()
        return (
            f"Fetched {len(data)} records from backend.\n"
            f"Working dir: {cwd}\nOUT_DIR used: {save_dir}\nSaved to: {filepath}"
        )
    except httpx.HTTPStatusError as e:
        return f"Error: Backend returned status {e.response.status_code}: {e.response.text}"
    except httpx.RequestError as e:
        return f"Error: Failed to connect to backend: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def download_csv(
    out_dir: str = "",
    table: str = "people",
    filename: str = ""
) -> str:
    return await _download_csv_impl(out_dir, table, filename, use_uuid_filter=True)

def main():
    import sys
    if _MCP_UUID:
        print(f"MCP Server: Loaded UUID from mcp.json: {_MCP_UUID}", file=sys.stderr)
    if _mcp_out_dir:
        print(f"MCP Server: Loaded OUT_DIR from mcp.json: {_mcp_out_dir}", file=sys.stderr)
    print(f"MCP Server: Using OUT_DIR: {OUT_DIR}", file=sys.stderr)
    print("MCP Server: Starting in STDIO mode...", file=sys.stderr)
    mcp.run()

if __name__ == "__main__":
    main()
