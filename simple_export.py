"""
LinkedIn Network CSV Exporter
Simple, direct export using Python's built-in csv module.
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


async def export_csv(output_path: str = None) -> int:
    """
    Export LinkedIn network to CSV using direct database connection.
    Simple approach using Python's built-in csv module.
    """
    if not DATABASE_URL:
        print("❌ Error: DATABASE_URL not set in environment")
        return 1
    
    if not API_KEY:
        print("❌ Error: API_KEY not set in environment")
        return 1
    
    try:
        print("=" * 60)
        print("LinkedIn Network CSV Exporter")
        print("=" * 60)
        print("🔄 Connecting to database...")
        
        # CONNECT TO DATABASE
        pool = await asyncpg.create_pool(DATABASE_URL)
        
        async with pool.acquire() as conn:
            print("📊 Querying contacts...")
            # SELECT ALL CONTACTS
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
        
        if not results:
            print("⚠️  No contacts found in your LinkedIn network.")
            await pool.close()
            return 1
        
        # Get output path
        file_path = get_output_path(output_path)
        print(f"💾 Saving to: {file_path}")
        
        # EXPORT ALL CONTACTS TO CSV
        with open(file_path, mode="w", encoding="utf-8", newline="") as f:
            # CSV FILE WRITER
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            
            # Write header row
            writer.writerow([
                "full_name", "email", "linkedin_url", "headline", "about",
                "current_company", "current_company_linkedin_url",
                "current_company_website_url", "experiences", "skills", 
                "education", "keywords"
            ])
            
            # WRITE ROWS TO CSV
            for row in results:
                writer.writerow([
                    format_value(row.get("full_name")),
                    format_value(row.get("email")),
                    format_value(row.get("linkedin_url")),
                    format_value(row.get("headline")),
                    format_value(row.get("about")),
                    format_value(row.get("current_company")),
                    format_value(row.get("current_company_linkedin_url")),
                    format_value(row.get("current_company_website_url")),
                    format_value(row.get("experiences")),
                    format_value(row.get("skills")),
                    format_value(row.get("education")),
                    format_value(row.get("keywords")),
                ])
        
        # Calculate stats
        size_kb = round(file_path.stat().st_size / 1024, 2)
        row_count = len(results)
        
        print("\n" + "=" * 60)
        print("✅ EXPORT COMPLETED!")
        print("=" * 60)
        print(f"📁 File: {file_path}")
        print(f"📈 Total Contacts: {row_count}")
        print(f"📊 Columns: 12")
        print(f"💾 File Size: {size_kb} KB")
        print("=" * 60)
        
        # Close connection
        await pool.close()
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

