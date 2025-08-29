from simple_conversational_agent import SimpleConversationalRestaurantAgent
from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

agent = SimpleConversationalRestaurantAgent()


class ChatRequest(BaseModel):
    query: str


@app.post("/chat")
async def chat(request: ChatRequest):
    print("Received request:", request)
    print("Content:", request.query)

    try:
        # Use the async conversational agent
        response = await agent.chat(request.query, session_id="default")
        return {"response": response}
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return {"error": f"Failed to process request: {str(e)}"}
