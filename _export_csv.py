"""Create CSV from MCP export_network_csv response - flexible export path"""
import csv
import json
import asyncio
import asyncpg
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=False)

DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY")

async def get_data_and_create_csv():
    """Get data from database and create CSV at best location ('data/' or './')."""
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set")
    if not API_KEY:
        raise Exception("API_KEY not set")

    print("=" * 60)
    print("LinkedIn Network CSV Export")
    print("=" * 60)
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

        if not results:
            print("⚠️  No contacts found.")
            return

        # Convert to dicts (same as server.py)
        contacts = []
        for row in results:
            contact = {}
            for key in row.keys():
                value = row[key]
                if value is None:
                    contact[key] = None
                elif isinstance(value, (list, dict)):
                    contact[key] = json.dumps(value, ensure_ascii=False)
                else:
                    contact[key] = value
            contacts.append(contact)

        # Try writing to data/network.csv; fallback to ./network.csv on error
        columns = list(contacts[0].keys())
        csv_path = None
        try:
            data_dir = Path("data")
            data_dir.mkdir(exist_ok=True)
            csv_path = data_dir / "network.csv"
            print(f"💾 Creating CSV file: {csv_path}")
        except Exception as e:
            csv_path = Path("network.csv")
            print(f"⚠️  Could not use 'data/' directory ({e}), saving as {csv_path}")

        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(columns)
            for contact in contacts:
                writer.writerow([
                    str(contact.get(col, "")) if contact.get(col) is not None else ""
                    for col in columns
                ])

        file_size_kb = round(csv_path.stat().st_size / 1024, 2)
        print("\n" + "=" * 60)
        print("✅ CSV EXPORT COMPLETED!")
        print("=" * 60)
        print(f"💾 File: {csv_path}")
        print(f"📈 Total Contacts: {len(contacts)}")
        print(f"📊 Columns: {len(columns)}")
        print(f"💾 File Size: {file_size_kb} KB")
        print("=" * 60)
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(get_data_and_create_csv())
