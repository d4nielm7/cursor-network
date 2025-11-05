import os
import asyncio
import asyncpg
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import logging

load_dotenv(override=False)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="LinkedIn Network API")

# Database connection pool
_db_pool = None

async def get_db_pool():
    """Get or create database connection pool"""
    global _db_pool
    if _db_pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is required")
        
        # Parse DATABASE_URL and create connection pool
        _db_pool = await asyncpg.create_pool(
            database_url,
            min_size=1,
            max_size=10,
            command_timeout=60
        )
        logger.info("Database connection pool created")
    return _db_pool

@app.on_event("startup")
async def startup():
    """Initialize database connection on startup"""
    try:
        await get_db_pool()
        logger.info("API server started successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

@app.on_event("shutdown")
async def shutdown():
    """Close database connections on shutdown"""
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        logger.info("Database connection pool closed")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "LinkedIn Network API"}

@app.get("/api/network")
async def get_network(x_uuid: str = Header(..., alias="X-UUID")):
    """
    Get network data for a specific user UUID
    
    Args:
        x_uuid: User UUID from X-UUID header
    
    Returns:
        JSON array of network contacts
    """
    if not x_uuid:
        raise HTTPException(status_code=400, detail="X-UUID header is required")
    
    try:
        pool = await get_db_pool()
        
        # Query database for contacts associated with this UUID
        # Set a timeout for the database query (10 seconds to avoid Railway's 15s timeout)
        # Use timeout to prevent Railway's 15s proxy timeout
        try:
            rows = await asyncio.wait_for(
                _fetch_network_data(pool, x_uuid),
                timeout=10.0  # 10 second timeout to stay under Railway's 15s limit
            )
        except asyncio.TimeoutError:
            logger.error(f"Database query timed out for UUID: {x_uuid}")
            raise HTTPException(
                status_code=504,
                detail="Database query timed out. Please try again."
            )
        
        # Convert rows to list of dicts
        if rows:
            columns = list(rows[0].keys())
            result = []
            for row in rows:
                row_dict = {}
                for col in columns:
                    value = row[col]
                    # Handle various data types
                    if value is None:
                        row_dict[col] = None
                    elif isinstance(value, (dict, list)):
                        row_dict[col] = value
                    else:
                        row_dict[col] = str(value)
                result.append(row_dict)
            
            logger.info(f"Returning {len(result)} records for UUID: {x_uuid}")
            return result
        else:
            logger.info(f"No records found for UUID: {x_uuid}")
            return []
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching network data: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

async def _fetch_network_data(pool, x_uuid: str):
    """Helper function to fetch network data from database"""
    async with pool.acquire() as conn:
        rows = None
        query_attempts = [
            # Try with user_id column
            ("SELECT * FROM people WHERE user_id = $1 ORDER BY created_at DESC", [x_uuid]),
            # Try with uuid column
            ("SELECT * FROM people WHERE uuid = $1 ORDER BY created_at DESC", [x_uuid]),
            # Try with user_uuid column
            ("SELECT * FROM people WHERE user_uuid = $1 ORDER BY created_at DESC", [x_uuid]),
            # Try getting all records (fallback - less secure but works)
            ("SELECT * FROM people ORDER BY created_at DESC LIMIT 1000", []),
        ]
        
        for query, params in query_attempts:
            try:
                if params:
                    rows = await conn.fetch(query, *params)
                else:
                    rows = await conn.fetch(query)
                
                # If we got a result (even if empty), use this query
                if rows is not None:
                    # If this was the fallback query (no WHERE clause), filter in Python
                    if not params:
                        logger.warning("Using fallback query without WHERE clause - filtering in Python")
                        filtered_rows = []
                        for row in rows:
                            # Check multiple possible UUID columns
                            row_uuid = str(row.get('user_id', '') or row.get('uuid', '') or row.get('user_uuid', ''))
                            if row_uuid == x_uuid:
                                filtered_rows.append(row)
                        rows = filtered_rows
                    break
            except Exception as query_error:
                logger.debug(f"Query attempt failed: {query_error}")
                continue
        
        if rows is None:
            logger.error("All database query attempts failed")
            raise HTTPException(
                status_code=500,
                detail="Failed to query database. Please check database connection and schema."
            )
        
        return rows

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)

