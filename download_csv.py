import requests
import os

# Configuration
API_KEY = "039d08d0-962f-45a6-a2a0-fe028c376827"
RAILWAY_URL = "https://web-production-e31ba.up.railway.app"
OUTPUT_DIR = "C:/Users/User/Documents/1Work/GhostTeam/Work/Weekly Demo's/Cursor for your network/data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "network.csv")

# Create directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("📥 Downloading LinkedIn network CSV from Railway...")
print(f"🔗 URL: {RAILWAY_URL}/export/network.csv")
print(f"📁 Saving to: {OUTPUT_FILE}")

try:
    # Download CSV
    resp = requests.get(
        f"{RAILWAY_URL}/export/network.csv",
        headers={"X-API-Key": API_KEY},
        timeout=60
    )
    
    if resp.status_code == 200:
        # Write to file
        with open(OUTPUT_FILE, 'wb') as f:
            f.write(resp.content)
        
        file_size_kb = len(resp.content) / 1024
        print(f"✅ Successfully downloaded!")
        print(f"📊 File size: {file_size_kb:.2f} KB")
        print(f"📁 Location: {OUTPUT_FILE}")
        
        # Verify file
        if os.path.exists(OUTPUT_FILE):
            import pandas as pd
            df = pd.read_csv(OUTPUT_FILE)
            print(f"✅ Verified: {len(df)} rows, {len(df.columns)} columns")
    else:
        print(f"❌ Error: HTTP {resp.status_code}")
        print(f"Response: {resp.text[:200]}")
        
except requests.exceptions.RequestException as e:
    print(f"❌ Network error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
