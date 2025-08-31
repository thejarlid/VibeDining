from simple_conversational_agent import SimpleConversationalRestaurantAgent
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from pydantic import BaseModel
import os
import shutil
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Get database paths from environment variables
DB_PATH = os.getenv("DB_PATH", "places.db")  # fallback for local development
CHROMA_PATH = os.getenv("CHROMA_PATH", "places_vector_db")  # fallback for local development
root = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/")

print(f"DB_PATH: {DB_PATH}")
print(f"CHROMA_PATH: {CHROMA_PATH}")
print(f"root: {root}")

print(f"os.getcwd(): {os.getcwd()}")
print(f"os.listdir(): {os.listdir()}")
print(f"os.listdir(root): {os.listdir(root)}")
# Print number of rows in places table
try:
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Places")
    row_count = cursor.fetchone()[0]
    print(f"Number of rows in Places table: {row_count}")
    conn.close()
except Exception as e:
    print(f"Error getting row count: {e}")


# Copy seed databases to volume if they don't exist (Railway setup)


def setup_persistent_databases():
    if DB_PATH.startswith('/data/'):
        if os.path.exists('/app/db_seed/places.db'):
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            # Use os.remove() for single files like the SQLite database
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            shutil.copy2('/app/db_seed/places.db', DB_PATH)

    if CHROMA_PATH.startswith('/data/'):
        if os.path.exists('/app/db_seed/places_vector_db'):
            # Use shutil.rmtree() for directories since Chroma creates a folder structure
            if os.path.exists(CHROMA_PATH):
                shutil.rmtree(CHROMA_PATH)
            shutil.copytree('/app/db_seed/places_vector_db', CHROMA_PATH)


# Setup databases for Railway
setup_persistent_databases()

agent = SimpleConversationalRestaurantAgent(db_path=DB_PATH, chroma_path=CHROMA_PATH)

# Get API key from environment variable
API_KEY = os.getenv("API_KEY")

# Dependency to verify API key


async def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key is required")

    if x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return x_api_key


class ChatRequest(BaseModel):
    query: str


@app.post("/chat")
async def chat(request: ChatRequest, api_key: str = Depends(verify_api_key)):
    print("Received request:", request)
    print("Content:", request.query)

    try:
        # Use the async conversational agent
        # Print contents of current directory
        current_dir = os.listdir()
        print("Current directory contents:", current_dir)
        response = ""  # await agent.chat(request.query, session_id="default")
        return {"response": response}
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return {"error": f"Failed to process request: {str(e)}"}


@app.get("/health")
async def health_check():
    """Health check endpoint - no authentication required"""
    return {"status": "healthy", "message": "API is running"}
