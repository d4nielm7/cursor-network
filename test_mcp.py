"""
Quick test script to verify the MCP server works
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables from .env file FIRST
load_dotenv()

async def test_connection():
    """Test database connection and user lookup"""
    
    # Test DATABASE_URL and API_KEY are set
    DATABASE_URL = os.getenv("DATABASE_URL")
    API_KEY = os.getenv("API_KEY")
    
    print("🔍 Testing MCP Server Configuration...\n")
    
    # Check environment variables
    if not DATABASE_URL:
        print("❌ DATABASE_URL not set")
        return False
    print("✅ DATABASE_URL is set")
    
    if not API_KEY:
        print("❌ API_KEY not set")
        return False
    print(f"✅ API_KEY is set: {API_KEY[:20]}...")
    
    # Test database connection
    try:
        print("\n🔌 Testing database connection...")
        pool = await asyncpg.create_pool(DATABASE_URL)
        print("✅ Connected to database")
        
        # Test user lookup - API_KEY is the user_id
        async with pool.acquire() as conn:
            print(f"\n👤 Checking user_id: {API_KEY}")
            
            # Check if user has data in people table
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM people WHERE user_id = $1::uuid",
                API_KEY
            )
            
            if count > 0:
                print(f"✅ User has {count} connections in database")
            else:
                print(f"⚠️  No data found for user_id: {API_KEY}")
                print("   The API_KEY might be correct but no LinkedIn data has been imported yet")
                return False
        
        await pool.close()
        print("\n✅ All tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    # Set API_KEY for testing (in real use, this comes from mcp.json)
    if not os.getenv("API_KEY"):
        # You can set it here for testing
        os.environ["API_KEY"] = "039d08d0-962f-45a6-a2a0-fe028c376827"
    
    result = asyncio.run(test_connection())
    exit(0 if result else 1)
