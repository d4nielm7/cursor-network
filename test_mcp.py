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
    # API_KEY should come from environment variable or .env file
    # Never hardcode sensitive data in source files!
    if not os.getenv("API_KEY"):
        print("❌ API_KEY not set!")
        print("   Set it as environment variable or add to .env file:")
        print("   export API_KEY=your-user-id-here")
        print("\n   Or for testing, run:")
        print("   API_KEY=your-user-id python test_mcp.py")
        exit(1)
    
    result = asyncio.run(test_connection())
    exit(0 if result else 1)
