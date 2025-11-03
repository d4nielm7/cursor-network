"""
LinkedIn Network CSV Exporter
Connects directly to database to retrieve data as JSON, then converts to CSV.
Auto-detects working directory and creates data/ folder if needed.

Usage:
    python simple_export.py
    python simple_export.py --output custom/path/network.csv
"""

import os
import json
import csv
import asyncio
import asyncpg
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=False)

DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY")


def get_output_path(output_path: str = None) -> Path:
    """Get the absolute output path, creating directories as needed."""
    if output_path:
        path = Path(output_path)
    else:
        # Auto-detect: use current working directory
        cwd = Path.cwd()
        path = cwd / "data" / "network.csv"
    
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def format_value(value):
    """Format a value for CSV (handle None, lists, dicts)."""
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


async def retrieve_data_from_database() -> list:
    """
    Retrieve data directly from database and return as list of dicts (JSON-compatible).
    """
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set in environment")
    
    if not API_KEY:
        raise Exception("API_KEY not set in environment")
    
    print("🔄 Connecting to database...")
    
    pool = await asyncpg.create_pool(DATABASE_URL)
    
    try:
        async with pool.acquire() as conn:
            print("📊 Querying contacts...")
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
                API_KEY
            )
        
        # Convert asyncpg Row objects to plain Python dicts (JSON-compatible)
        contacts = []
        for row in results:
            contact = {}
            for key in row.keys():
                value = row[key]
                # Handle None values and complex types
                if value is None:
                    contact[key] = None
                elif isinstance(value, (list, dict)):
                    contact[key] = json.dumps(value, ensure_ascii=False)
                else:
                    contact[key] = value
            contacts.append(contact)
        
        return contacts
        
    finally:
        await pool.close()


async def export_csv(output_path: str = None) -> int:
    """
    Export LinkedIn network to CSV.
    Retrieves JSON data from database and converts to CSV format.
    """
    try:
        print("=" * 60)
        print("LinkedIn Network CSV Exporter")
        print("=" * 60)
        
        # Retrieve data from database (as JSON-compatible list of dicts)
        contacts = await retrieve_data_from_database()
        
        if not contacts:
            print("⚠️  No contacts found in your LinkedIn network.")
            return 1
        
        # Get output path
        file_path = get_output_path(output_path)
        print(f"💾 Saving to: {file_path}")
        
        # EXPORT ALL CONTACTS TO CSV
        with open(file_path, mode="w", encoding="utf-8", newline="") as f:
            # CSV FILE WRITER
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            
            # Get column names from first contact (properly mapped)
            if contacts:
                columns = list(contacts[0].keys())
                
                # Write header row
                writer.writerow(columns)
                
                # WRITE ROWS TO CSV - map JSON data properly
                for contact in contacts:
                    writer.writerow([
                        format_value(contact.get(col)) for col in columns
                    ])
        
        # Calculate stats
        size_kb = round(file_path.stat().st_size / 1024, 2)
        row_count = len(contacts)
        column_count = len(contacts[0].keys()) if contacts else 0
        
        print("\n" + "=" * 60)
        print("✅ EXPORT COMPLETED!")
        print("=" * 60)
        print(f"📁 File: {file_path}")
        print(f"📈 Total Contacts: {row_count}")
        print(f"📊 Columns: {column_count}")
        print(f"💾 File Size: {size_kb} KB")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export LinkedIn network to CSV file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python simple_export.py
  python simple_export.py --output custom/path/network.csv
  python simple_export.py -o data/my_network.csv
        """
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output CSV file path (default: data/network.csv relative to current directory)",
    )
    args = parser.parse_args()
    
    return asyncio.run(export_csv(args.output))


if __name__ == "__main__":
    exit(main())
