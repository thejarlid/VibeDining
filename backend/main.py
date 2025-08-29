from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class ChatRequest(BaseModel):
    query: str


@app.post("/chat")
async def chat(request: ChatRequest):
    print("Received request:", request)
    print("Content:", request.query)
    return {"response": request.query * 3}
