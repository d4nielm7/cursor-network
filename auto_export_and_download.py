import json
import os
import requests
import time
import subprocess

# Automatically find and load .mcp.json in current directory or parent
def find_mcp_json(start_path):
    current_path = start_path
    while True:
        candidate = os.path.join(current_path, ".mcp.json")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current_path)
        if parent == current_path:
            raise FileNotFoundError(".mcp.json not found")
        current_path = parent

mcp_json_path = find_mcp_json(os.getcwd())
with open(mcp_json_path, 'r') as f:
    config = json.load(f)

server_config = config['mcpServers']['linkedin-network']
base_url = server_config['url'].replace('/sse', '')
api_key = server_config['headers']['X-API-Key']

output_filename = "linkedin_network.csv"  # Your desired local file name
download_url = f"{base_url}/file-csv"

# 1. Trigger export tool
export_resp = requests.post(
    f"{base_url}/sse",
    headers={"X-API-Key": api_key},
    json={"tool": "export_network_csv_to_file", "params": {"filepath": output_filename}}
)
print("Export triggered:", export_resp.text)

# 2. Wait for export to finish
time.sleep(2)

# 3. Download using curl to the current directory
subprocess.run([
    "curl", "-o", output_filename, download_url,
    "-H", f"X-API-Key: {api_key}"
])

print(f"Downloaded CSV saved to {os.path.join(os.getcwd(), output_filename)}")
