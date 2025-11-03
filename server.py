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
from typing import List, Dict, Any
from dotenv import load_dotenv
from contextvars import ContextVar
from fastapi import FastAPI, Response, Header
from fastapi.responses import FileResponse
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

def shell_cmd(cmd: str) -> str:
    """Formats a command-line example block."""
    return f"```bash\n{cmd}\n```"

def py_cmd(code: str) -> str:
    """Formats a Python example block."""
    return f"```python\n{code}\n```"

async def discover_user_tables(pool) -> List[str]:
    """Discover all tables that have a user_id column."""
    async with pool.acquire() as conn:
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.columns 
            WHERE column_name = 'user_id' 
            AND table_schema = 'public'
            ORDER BY table_name
        """)
        return [row['table_name'] for row in tables]

async def export_table_to_csv(conn, table_name: str, user_id: str, file_path: str) -> Dict[str, Any]:
    """Export a single table to CSV."""
    # Validate table name to prevent SQL injection (only allow alphanumeric and underscore)
    if not table_name.replace('_', '').isalnum():
        return {"table": table_name, "rows": 0, "error": "Invalid table name"}
    
    # Get all columns for this table
    columns = await conn.fetch("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = $1 
        AND table_schema = 'public'
        ORDER BY ordinal_position
    """, table_name)
    
    if not columns:
        return {"table": table_name, "rows": 0, "error": "No columns found"}
    
    col_names = [col['column_name'] for col in columns]
    
    # Build query - handle user_id column
    # Table name is validated above (alphanumeric + underscore only)
    # Use PostgreSQL's quote_ident function via a query to safely quote identifiers
    if 'user_id' in col_names:
        # Use double quotes for PostgreSQL identifier quoting
        safe_table = f'"{table_name}"'
        safe_order_col = f'"{col_names[0]}"'
        query = f'SELECT * FROM {safe_table} WHERE user_id = $1 ORDER BY {safe_order_col}'
        results = await conn.fetch(query, user_id)
    else:
        # If no user_id column, export all rows (might be shared tables)
        safe_table = f'"{table_name}"'
        safe_order_col = f'"{col_names[0]}"'
        query = f'SELECT * FROM {safe_table} ORDER BY {safe_order_col}'
        results = await conn.fetch(query)
    
    if not results:
        return {"table": table_name, "rows": 0, "message": "No data"}
    
    # Write CSV
    def fmt(v):
        if v is None:
            return ""
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)
    
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(col_names)
        for row in results:
            writer.writerow([fmt(row.get(col)) for col in col_names])
    
    return {
        "table": table_name,
        "rows": len(results),
        "columns": len(col_names),
        "size_kb": round(os.path.getsize(file_path) / 1024, 2)
    }

def csv_exists(csv_path: str = "data/people.csv") -> bool:
    """Check if CSV file exists locally."""
    return os.path.exists(csv_path)

async def auto_download_csv() -> str:
    """
    Automatically export ALL tables from database to CSV files on first connection.
    This is the ONLY time we connect to the database. After this, all queries use CSV only.
    """
    csv_path = "data/people.csv"
    
    # If CSV already exists, skip export (already done before)
    if csv_exists(csv_path):
        return json.dumps({
            "status": "success",
            "message": f"CSV already exists at {csv_path} - using local CSV files only (no database connection)",
            "csv_path": csv_path
        })
    
    # Only export if we're running locally (not on Railway)
    if os.getenv("PORT"):
        return json.dumps({
            "status": "info",
            "message": "Running on Railway. Use /export/network.csv endpoint to download."
        })
    
    try:
        print("🔄 FIRST CONNECTION: Exporting ALL tables from database to CSV...")
        print("⚠️  This is the ONLY database connection. After this, all queries use CSV files only.")
        
        user_id = await get_user_id()
        pool = await get_db()

        # Discover all tables with user_id
        tables = await discover_user_tables(pool)
        
        if not tables:
            return json.dumps({
                "status": "error",
                "message": "No tables found with user_id column."
            })

        os.makedirs("data", exist_ok=True)
        export_results = []
        total_rows = 0
        total_size_kb = 0

        async with pool.acquire() as conn:
            for table in tables:
                print(f"📊 Exporting table: {table}...")
                file_path = f"data/{table}.csv"
                result = await export_table_to_csv(conn, table, user_id, file_path)
                export_results.append(result)
                if "rows" in result:
                    total_rows += result["rows"]
                if "size_kb" in result:
                    total_size_kb += result["size_kb"]
                print(f"  ✅ {table}: {result.get('rows', 0)} rows ({result.get('size_kb', 0)} KB)")

        # Close database pool - we won't need it again
        global db_pool
        if db_pool:
            await db_pool.close()
            db_pool = None
            print("🔒 Database connection closed. All future queries will use CSV files only.")

        # Create combined export info
        summary = "\n".join([
            f"  • {r['table']}: {r.get('rows', 0)} rows ({r.get('size_kb', 0)} KB)"
            for r in export_results
        ])

        message = (
            f"✅ ALL tables exported from database!\n\n"
            f"📊 Tables exported:\n{summary}\n\n"
            f"📈 Total Rows: {total_rows}\n"
            f"💾 Total Size: {round(total_size_kb, 2)} KB\n\n"
            f"📁 Files saved to: ./data/\n\n"
            f"🔒 Database connection closed. All future queries will use CSV files only (no database access)."
        )
        
        return json.dumps({
            "status": "success",
            "message": message,
            "tables": export_results,
            "total_rows": total_rows,
            "total_size_kb": round(total_size_kb, 2),
            "csv_path": csv_path,
            "auto_downloaded": True
        })
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Auto-export failed: {error_msg}")
        return json.dumps({
            "status": "error",
            "message": f"Auto-export failed: {error_msg}"
        })

def load_csv_data(csv_path: str) -> pd.DataFrame:
    """Load CSV data into pandas DataFrame."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    return pd.read_csv(csv_path, encoding='utf-8')

# ---------------------------
# Tools
# ---------------------------

@mcp.tool()
async def initialize_network_csv() -> str:
    """
    Initialize and export your LinkedIn network to CSV files.
    Call this first when connecting to MCP - it will export ALL tables from database automatically.
    
    After this completes, database connection is closed and all queries will use CSV files only.
    This is the ONLY time the database is accessed.
    """
    return await auto_download_csv()

@mcp.tool()
async def export_network_csv() -> str:
    """
    Export ALL tables from your LinkedIn network database to CSV files.
    Discovers all tables with user_id column and exports each one.
    
    When running locally → saves to ./data/ directory
    When on Railway → provides download URL and commands
    
    After downloading, you can use CSV query tools to search the local files instead of querying the database.
    """
    try:
        user_id = await get_user_id()
        pool = await get_db()

        # Discover all tables with user_id
        tables = await discover_user_tables(pool)
        
        if not tables:
            return json.dumps({
                "status": "error",
                "message": "No tables found with user_id column."
            })

        os.makedirs("data", exist_ok=True)
        export_results = []
        total_rows = 0
        total_size_kb = 0

        async with pool.acquire() as conn:
            for table in tables:
                file_path = f"data/{table}.csv"
                result = await export_table_to_csv(conn, table, user_id, file_path)
                export_results.append(result)
                if "rows" in result:
                    total_rows += result["rows"]
                if "size_kb" in result:
                    total_size_kb += result["size_kb"]

        # Create combined export info
        summary = "\n".join([
            f"  • {r['table']}: {r.get('rows', 0)} rows ({r.get('size_kb', 0)} KB)"
            for r in export_results
        ])

        # Build smart response
        if os.getenv("PORT"):  # Running on Railway
            curl_example = shell_cmd(
                f"curl -H 'X-API-Key: {user_id}' "
                f"-o linkedin_network.zip {APP_URL}/export/all.zip"
            )
            python_example = py_cmd(
                f"import requests\n\n"
                f"resp = requests.get('{APP_URL}/export/all.zip', headers={{'X-API-Key': '{user_id}'}})\n"
                f"open('linkedin_network.zip', 'wb').write(resp.content)\n"
                f"print('✅ Downloaded linkedin_network.zip')"
            )

            message = (
                f"✅ Export completed for all tables.\n\n"
                f"📊 Tables exported:\n{summary}\n\n"
                f"📈 Total Rows: {total_rows}\n"
                f"💾 Total Size: {round(total_size_kb, 2)} KB\n\n"
                f"Download your data:\n\n"
                f"**Command line (curl):**\n{curl_example}\n\n"
                f"**Python script:**\n{python_example}\n\n"
                f"🔗 Direct download: {APP_URL}/export/all.zip\n"
                f"📄 Individual CSV: {APP_URL}/export/network.csv (people table)"
            )

        else:  # Local mode
            message = (
                f"✅ Export completed locally.\n\n"
                f"📊 Tables exported:\n{summary}\n\n"
                f"📁 Files saved to: ./data/\n"
                f"📈 Total Rows: {total_rows}\n"
                f"💾 Total Size: {round(total_size_kb, 2)} KB\n\n"
                f"After downloading, use CSV query tools to search these files locally!"
            )

        return json.dumps({
            "status": "success",
            "message": message,
            "tables": export_results,
            "total_rows": total_rows,
            "total_size_kb": round(total_size_kb, 2),
            "csv_path": "data/people.csv" if "people" in tables else None
        })
    except Exception as e:
        error_msg = str(e)
        return json.dumps({
            "status": "error",
            "message": f"Error exporting CSV: {error_msg}"
        })

@mcp.tool()
async def search_network_csv(query: str, limit: int = 10, csv_path: str = "data/people.csv") -> str:
    """
    Search your LinkedIn network from the local CSV file (NO DATABASE CONNECTION).
    
    AUTO-EXPORTS all tables from database on FIRST USE ONLY. After that, uses CSV only.
    
    Args:
        query: Search term (name, title, company, skills, keywords)
        limit: Maximum results to return (default: 10)
        csv_path: Path to CSV file (default: data/people.csv)
    
    Returns:
        JSON string with matching profiles from CSV
    """
    try:
        # Auto-export from database if CSV doesn't exist (FIRST TIME ONLY)
        if not csv_exists(csv_path):
            export_result = await auto_download_csv()
            export_data = json.loads(export_result)
            if export_data.get("status") != "success":
                return export_result  # Return error message if export failed
        
        # Load CSV - NO DATABASE ACCESS
        df = load_csv_data(csv_path)
        
        # Search across multiple columns
        mask = (
            df.astype(str).apply(lambda x: x.str.contains(query, case=False, na=False)).any(axis=1)
        )
        
        results = df[mask].head(limit)
        
        if results.empty:
            return json.dumps({
                "status": "success",
                "message": f"No matches found for '{query}'",
                "results": [],
                "count": 0
            })
        
        records = results.to_dict('records')
        
        return json.dumps({
            "status": "success",
            "query": query,
            "count": len(records),
            "results": records
        }, indent=2)
    except FileNotFoundError:
        return json.dumps({
            "status": "error",
            "message": f"CSV file not found: {csv_path}. Please export your network first using export_network_csv."
        })
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error searching CSV: {str(e)}"
        })

@mcp.tool()
async def get_person_csv(name: str, csv_path: str = "data/people.csv") -> str:
    """
    Get a specific person's details from the local CSV file (NO DATABASE CONNECTION).
    
    AUTO-EXPORTS all tables from database on FIRST USE ONLY. After that, uses CSV only.
    
    Args:
        name: Person's name (partial match)
        csv_path: Path to CSV file (default: data/people.csv)
    
    Returns:
        JSON string with person's profile
    """
    try:
        # Auto-export from database if CSV doesn't exist (FIRST TIME ONLY)
        if not csv_exists(csv_path):
            export_result = await auto_download_csv()
            export_data = json.loads(export_result)
            if export_data.get("status") != "success":
                return export_result  # Return error message if export failed
        
        # Load CSV - NO DATABASE ACCESS
        df = load_csv_data(csv_path)
        
        if 'full_name' not in df.columns:
            return json.dumps({
                "status": "error",
                "message": "CSV file doesn't have 'full_name' column"
            })
        
        mask = df['full_name'].astype(str).str.contains(name, case=False, na=False)
        result = df[mask].head(1)
        
        if result.empty:
            return json.dumps({
                "status": "error",
                "message": f"Person '{name}' not found in CSV"
            })
        
        person = result.iloc[0].to_dict()
        
        return json.dumps({
            "status": "success",
            "person": person
        }, indent=2)
    except FileNotFoundError:
        return json.dumps({
            "status": "error",
            "message": f"CSV file not found: {csv_path}. Please export your network first."
        })
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error reading CSV: {str(e)}"
        })

@mcp.tool()
async def get_csv_stats(csv_path: str = "data/people.csv") -> str:
    """
    Get statistics about your LinkedIn network from the CSV file (NO DATABASE CONNECTION).
    
    AUTO-EXPORTS all tables from database on FIRST USE ONLY. After that, uses CSV only.
    
    Args:
        csv_path: Path to CSV file (default: data/people.csv)
    
    Returns:
        JSON string with statistics
    """
    try:
        # Auto-export from database if CSV doesn't exist (FIRST TIME ONLY)
        if not csv_exists(csv_path):
            export_result = await auto_download_csv()
            export_data = json.loads(export_result)
            if export_data.get("status") != "success":
                return export_result  # Return error message if export failed
        
        # Load CSV - NO DATABASE ACCESS
        df = load_csv_data(csv_path)
        
        stats = {
            "total_connections": len(df),
            "csv_path": csv_path
        }
        
        # Add column-specific stats if available
        if 'current_company' in df.columns:
            companies = df['current_company'].dropna()
            stats["unique_companies"] = companies.nunique()
            stats["top_companies"] = companies.value_counts().head(5).to_dict()
        
        if 'skills' in df.columns:
            stats["has_skills_data"] = df['skills'].notna().sum()
        
        return json.dumps({
            "status": "success",
            "stats": stats
        }, indent=2)
    except FileNotFoundError:
        return json.dumps({
            "status": "error",
            "message": f"CSV file not found: {csv_path}. Please export your network first."
        })
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Error reading CSV: {str(e)}"
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

        @fastapi_root.get("/export/network.csv")
        async def download_network_csv(x_api_key: str = Header(None, alias="X-API-Key")):
            """Download the people table as CSV."""
            try:
                user_id = x_api_key or os.getenv("API_KEY")
                if not user_id:
                    return Response("API_KEY missing", status_code=401)
                
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
                    return Response("No data found", status_code=404)
                
                # Create CSV in memory
                output = io.StringIO()
                writer = csv.writer(output)
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
                
                csv_content = output.getvalue()
                output.close()
                
                return Response(
                    content=csv_content,
                    media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=network.csv"}
                )
            except Exception as e:
                return Response(f"Error: {str(e)}", status_code=500)

        @fastapi_root.get("/export/all.zip")
        async def download_all_tables(x_api_key: str = Header(None, alias="X-API-Key")):
            """Download all tables as a ZIP file."""
            import zipfile
            import tempfile
            
            try:
                user_id = x_api_key or os.getenv("API_KEY")
                if not user_id:
                    return Response("API_KEY missing", status_code=401)
                
                pool = await get_db()
                tables = await discover_user_tables(pool)
                
                if not tables:
                    return Response("No tables found", status_code=404)
                
                # Create temporary directory and ZIP file
                with tempfile.TemporaryDirectory() as tmpdir:
                    zip_path = os.path.join(tmpdir, "linkedin_network.zip")
                    
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        async with pool.acquire() as conn:
                            for table in tables:
                                file_path = os.path.join(tmpdir, f"{table}.csv")
                                result = await export_table_to_csv(conn, table, user_id, file_path)
                                if result.get("rows", 0) > 0:
                                    zipf.write(file_path, f"{table}.csv")
                    
                    # Read ZIP file and return
                    with open(zip_path, 'rb') as f:
                        zip_content = f.read()
                    
                    return Response(
                        content=zip_content,
                        media_type="application/zip",
                        headers={"Content-Disposition": "attachment; filename=linkedin_network.zip"}
                    )
            except Exception as e:
                return Response(f"Error: {str(e)}", status_code=500)

        fastapi_root.mount("/", HeaderToContextMiddleware(sse_app))
        uvicorn.run(fastapi_root, host="0.0.0.0", port=port)
    else:
        print("🔧 Starting MCP server in STDIO mode (local)")
        mcp.run()
