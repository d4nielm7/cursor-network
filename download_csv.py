# Simple LinkedIn Network CSV Downloader
# Just run: python download_csv.py

import requests
import os

API_KEY = "039d08d0-962f-45a6-a2a0-fe028c376827"
RAILWAY_URL = "https://web-production-e31ba.up.railway.app"
OUTPUT_DIR = r"C:\Users\User\Documents\1Work\GhostTeam\Work\Weekly Demo's\Cursor for your network\data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "network.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 60)
print("Downloading LinkedIn Network CSV...")
print("=" * 60)

try:
    resp = requests.get(
        f"{RAILWAY_URL}/export/network.csv",
        headers={"X-API-Key": API_KEY},
        timeout=60
    )
    
    if resp.status_code == 200:
        with open(OUTPUT_FILE, 'wb') as f:
            f.write(resp.content)
        
        file_size_kb = len(resp.content) / 1024
        
        print(f"\n✅ SUCCESS!")
        print(f"📊 File size: {file_size_kb:.2f} KB")
        print(f"📁 Saved to: {OUTPUT_FILE}\n")
        
        # Verify
        if os.path.exists(OUTPUT_FILE):
            import pandas as pd
            df = pd.read_csv(OUTPUT_FILE)
            print(f"✅ Verified: {len(df)} rows, {len(df.columns)} columns")
            print("\n" + "=" * 60)
            print("DOWNLOAD COMPLETE! 🎉")
            print("=" * 60)
    else:
        print(f"\n❌ Error: HTTP {resp.status_code}")
        print(f"Response: {resp.text[:200]}")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\nAlternative: Download manually from:")
    print(f"{RAILWAY_URL}/export/network.csv")

input("\nPress Enter to exit...")
