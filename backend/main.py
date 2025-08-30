from simple_conversational_agent import SimpleConversationalRestaurantAgent
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

agent = SimpleConversationalRestaurantAgent()

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
        response = await agent.chat(request.query, session_id="default")
        return {"response": response}
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return {"error": f"Failed to process request: {str(e)}"}


@app.get("/health")
async def health_check():
    """Health check endpoint - no authentication required"""
    return {"status": "healthy", "message": "API is running"}
