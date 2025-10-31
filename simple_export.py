import os
import json
import csv
import asyncio
import asyncpg
from dotenv import load_dotenv

load_dotenv(override=False)

DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY")

async def export_csv():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not set")
        return 1
    
    if not API_KEY:
        print("Error: API_KEY not set")
        return 1
    
    try:
        pool = await asyncpg.create_pool(DATABASE_URL)
        
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
                API_KEY
            )
        
        if not results:
            print("No contacts found in your LinkedIn network.")
            return 1
        
        # Create data directory if it doesn't exist
        os.makedirs("data", exist_ok=True)
        file_path = "data/network.csv"
        
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
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
        
        size_kb = round(os.path.getsize(file_path) / 1024, 2)
        row_count = len(results)
        
        print(f"✅ Export completed!")
        print(f"📁 File saved to: {file_path}")
        print(f"📈 Total Contacts: {row_count}")
        print(f"💾 File Size: {size_kb} KB")
        
        await pool.close()
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(asyncio.run(export_csv()))

