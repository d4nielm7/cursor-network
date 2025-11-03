import requests
import os

# Create data directory if it doesn't exist
os.makedirs('data', exist_ok=True)

# Download CSV
url = 'https://web-production-e31ba.up.railway.app/export/network.csv'
headers = {'X-API-Key': '039d08d0-962f-45a6-a2a0-fe028c376827'}

print('📥 Downloading CSV from Railway...')
resp = requests.get(url, headers=headers)

if resp.status_code == 200:
    with open('data/network.csv', 'wb') as f:
        f.write(resp.content)
    print(f'✅ Downloaded network.csv ({len(resp.content) / 1024:.2f} KB)')
    print(f'📁 File saved to: {os.path.abspath("data/network.csv")}')
else:
    print(f'❌ Error: HTTP {resp.status_code}')

