"""
Manual test script to verify the MCP server works
This simulates what Cursor does when connecting to the server
"""
import subprocess
import json
import sys

def test_mcp_server():
    """Test the MCP server manually"""
    print("Testing MCP Server...\n")
    
    # Start the server process
    process = subprocess.Popen(
        [sys.executable, "server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **dict(os.environ),
            "API_KEY": "039d08d0-962f-45a6-a2a0-fe028c376827",
            "DATABASE_URL": os.getenv("DATABASE_URL")
        }
    )
    
    # Send an MCP initialize request
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0"
            }
        }
    }
    
    print("Sending initialize request...")
    process.stdin.write(json.dumps(init_request) + "\n")
    process.stdin.flush()
    
    # Wait for response
    response = process.stdout.readline()
    print(f"Response: {response}")
    
    # Clean up
    process.terminate()
    process.wait()
    print("\n✅ Server responded!")

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    if not os.getenv("DATABASE_URL"):
        print("❌ DATABASE_URL not set. Please create .env file")
        exit(1)
    
    test_mcp_server()

