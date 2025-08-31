from datetime import datetime, timedelta
from simple_conversational_agent import SimpleConversationalRestaurantAgent
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from pydantic import BaseModel
import os
import shutil
import uuid
import asyncio
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Get database paths from environment variables
DB_PATH = os.getenv("DB_PATH", "places.db")  # fallback for local development
CHROMA_PATH = os.getenv("CHROMA_PATH", "places_vector_db")  # fallback for local development

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
    session_id: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str


# Track active sessions with timestamps for cleanup
active_sessions = {}  # {session_id: last_activity_time}


def cleanup_old_sessions():
    """Clean up sessions older than 30 minutes"""
    cutoff_time = datetime.now() - timedelta(minutes=30)
    expired_sessions = [
        session_id for session_id, last_activity in active_sessions.items()
        if last_activity < cutoff_time
    ]

    for session_id in expired_sessions:
        try:
            # Clean up the agent's conversation memory
            asyncio.create_task(agent.reset_conversation(session_id))
            del active_sessions[session_id]
            print(f"Cleaned up expired session: {session_id}")
        except Exception as e:
            print(f"Error cleaning up session {session_id}: {e}")


@app.post("/chat")
async def chat(request: ChatRequest, api_key: str = Depends(verify_api_key)):
    # Auto-create session if not provided
    if not request.session_id or request.session_id not in active_sessions:
        session_id = str(uuid.uuid4())
    else:
        session_id = request.session_id

    # Update session activity timestamp
    active_sessions[session_id] = datetime.now()

    # Periodically clean up old sessions (every 50th request to avoid overhead)
    if len(active_sessions) % 50 == 0:
        cleanup_old_sessions()

    try:
        response = await agent.chat(request.query, session_id=session_id)
        return {
            "response": response,
            "session_id": session_id
        }
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return {"error": f"Failed to process request: {str(e)}"}


@app.delete("/session/{session_id}")
async def end_session(session_id: str, api_key: str = Depends(verify_api_key)):
    """Manually end a specific session (optional - for when user explicitly leaves)"""
    try:
        if session_id in active_sessions:
            await agent.reset_conversation(session_id)
            del active_sessions[session_id]
            return {"status": "ended", "session_id": session_id}
        else:
            return {"status": "not_found", "session_id": session_id}
    except Exception as e:
        return {"error": f"Failed to end session: {str(e)}"}


@app.get("/health")
async def health_check():
    """Health check endpoint - no authentication required"""
    return {"status": "healthy", "message": "API is running"}
