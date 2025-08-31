# VibeDining Backend

## Overview

FastAPI-powered backend with LangGraph conversational agents for intelligent restaurant recommendations. Combines vector search, SQL databases, and multi-tool AI agents to provide personalized dining suggestions through natural language conversations.

## 🛠️ Tech Stack

- **Framework**: FastAPI with async/await support
- **AI Framework**: LangGraph for agentic workflows
- **LLM**: OpenAI GPT models (gpt-4o-mini, text-embedding-3-small)
- **Vector DB**: ChromaDB for semantic search
- **Database**: SQLite for structured data
- **Language**: Python 3.11+
- **Deployment**: Docker support

## 🏗️ Architecture

```
backend/
├── main.py                      # FastAPI server & routes
├── simple_conversational_agent.py  # LangGraph agents
├── indexer.py                   # Data indexing system
├── model.py                     # Pydantic data models
├── places.db                    # SQLite database
├── places_vector_db/            # ChromaDB vector store
├── requirements.txt             # Python dependencies
└── Dockerfile                   # Container configuration
```

## 🤖 AI Agent System

### LangGraph Architecture
The core AI system uses **LangGraph** to create intelligent, multi-tool agents:

```python
# Agent workflow with specialized tools
class RestaurantAgent:
    tools = [
        vector_search,           # Semantic similarity search
        sql_search,             # Structured constraint queries  
        validate_location_match, # Location verification
        get_restaurant_details   # Detailed place information
    ]
```

### Agent Capabilities
- **Guardrail System**: Intent classification to ensure restaurant-related queries
- **Multi-Tool Coordination**: Intelligently combines vector and SQL search
- **Quality Validation**: Cross-references results against user constraints
- **Conversation Memory**: Maintains context across chat sessions

### Tool Strategy
```python
# Example agent decision making:
TOOL_USAGE_STRATEGY = {
    "qualitative_queries": "vector_search",  # "cozy atmosphere"
    "specific_constraints": "sql_search",    # "in Williamsburg, $$ price"
    "location_verification": "validate_location_match",
    "detailed_info": "get_restaurant_details"
}
```

## 📊 Data Architecture

### Dual Storage System

#### 1. SQLite Database (places.db)
**Structured data for precise filtering:**
```sql
-- Core restaurant data
CREATE TABLE Places (
    id TEXT PRIMARY KEY,
    name TEXT,
    rating REAL,
    price_level TEXT,
    category TEXT,
    formatted_address TEXT,
    description TEXT,
    -- ... additional fields
);

-- Location hierarchies
CREATE TABLE Localities (
    id TEXT PRIMARY KEY,
    name TEXT,
    full_name TEXT,
    latitude REAL,
    longitude REAL,
    type TEXT CHECK(type IN ('neighborhood', 'city'))
);

-- Place-location relationships
CREATE TABLE PlaceLocalities (
    place_id TEXT REFERENCES Places(id),
    locality_id TEXT REFERENCES Localities(id),
    PRIMARY KEY(place_id, locality_id)
);
```

#### 2. ChromaDB Vector Store (places_vector_db/)
**Semantic search for qualitative features:**
- **Collections**: `description`, `atmosphere`, `food_drink`, `special_features`
- **Embeddings**: OpenAI `text-embedding-3-small` (1536 dimensions)
- **Reranking**: Cross-encoder models for relevance refinement
- **Metadata**: Place ID, name, document type for cross-referencing

### Data Processing Pipeline
```python
# LLM-enhanced data enrichment
def _summarize_place_with_llm(self, place: Place):
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user", 
            "content": f"Extract atmosphere and features from: {place.data}"
        }]
    )
    return {
        'atmosphere': "Cozy, intimate setting...",
        'food_drink': "Craft cocktails and small plates...", 
        'special_features': "Live jazz, outdoor seating..."
    }
```

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- OpenAI API key
- Google Maps API key (optional)

### Installation
```bash
# Clone and navigate
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Configuration
Create `.env` file:
```bash
# Required
OPENAI_API_KEY=your_openai_api_key

# Optional (for enhanced place data)
GOOGLE_MAPS_API_KEY=your_google_maps_api_key

# FastAPI settings
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

### Running the Server
```bash
# Development server with auto-reload
python main.py

# Or with uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Access Points
- **API Server**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## 📡 API Endpoints

### Chat Endpoints
```python
# Main chat endpoint
POST /chat
{
    "message": "Find cozy coffee shops in Brooklyn",
    "session_id": "optional-session-id"
}

# Response
{
    "response": "I found 3 cozy coffee shops...",
    "session_id": "session-uuid",
    "recommendations": [
        {
            "name": "Blue Bottle Coffee",
            "address": "123 Main St, Brooklyn",
            "rating": 4.5,
            "description": "Minimalist coffee shop..."
        }
    ]
}
```

### Session Management
```python
# Get conversation history
GET /session/{session_id}

# Clear session
DELETE /session/{session_id}
```

### Health & Info
```python
# Health check
GET /health

# API information
GET /info
```

## 🔧 Core Components

### 1. FastAPI Server (main.py)
```python
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    # Initialize conversational agent
    agent = ConversationalAgent()
    
    # Process user message through LangGraph
    response = await agent.process_message(
        message=request.message,
        session_id=request.session_id
    )
    
    return ChatResponse(
        response=response.content,
        session_id=response.session_id,
        recommendations=response.recommendations
    )
```

### 2. Conversational Agent (simple_conversational_agent.py)
```python
class ConversationalAgent:
    def __init__(self):
        self.graph = self._build_langgraph()
        self.tools = self._initialize_tools()
    
    def _build_langgraph(self):
        # Create LangGraph workflow
        workflow = StateGraph(State)
        workflow.add_node("guardrail", self._guardrail)
        workflow.add_node("agent", self._agent)
        workflow.add_node("respond", self._respond)
        
        # Define conditional flow
        workflow.add_conditional_edges(
            "guardrail",
            self._should_continue,
            {"continue": "agent", "end": "respond"}
        )
        
        return workflow.compile()
```

### 3. Search Tools
```python
class RestaurantSearchTools:
    def vector_search(self, query: str, n_results: int = 20):
        """Semantic search for atmosphere and vibes"""
        results = self.chroma_client.query(
            collection_name="descriptions",
            query_texts=[query],
            n_results=n_results
        )
        return self._format_vector_results(results)
    
    def sql_search(self, constraints: str):
        """SQL queries for specific filters"""
        # Parse constraints and build dynamic SQL
        query = self._build_sql_query(constraints)
        return self.db.execute(query).fetchall()
```

### 4. Data Indexer (indexer.py)
```python
class Indexer:
    def __init__(self, db_path: str, chroma_path: str):
        self.db = sqlite3.connect(db_path)
        self.chroma_client = chromadb.PersistentClient(chroma_path)
        self.openai_client = OpenAI()
    
    def index_csv(self, csv_path: str):
        """Process CSV and create dual storage"""
        places = self._load_places_csv(csv_path)
        
        for place in places:
            # Store structured data in SQLite
            self._store_place_sql(place)
            
            # Generate embeddings and store in ChromaDB
            embeddings = self._generate_embeddings(place)
            self._store_place_vectors(place, embeddings)
```

## 🧪 Testing

### Running Tests
```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest tests/

# Run with coverage
pytest --cov=. tests/
```

### Test Structure
```python
# Example test
async def test_chat_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/chat", json={
            "message": "Find Italian restaurants in SoHo"
        })
    assert response.status_code == 200
    assert "restaurant" in response.json()["response"].lower()
```

## 🐳 Docker Deployment

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "main.py"]
```

### Building and Running
```bash
# Build image
docker build -t vibedining-backend .

# Run container
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=your_key \
  vibedining-backend
```

## 📈 Performance & Monitoring

### Optimization Strategies
- **Async Operations**: All database and API calls are async
- **Connection Pooling**: Reuse database connections
- **Embedding Caching**: Cache frequently used embeddings
- **Response Streaming**: Stream LLM responses for better UX

### Monitoring Points
```python
# Health metrics to track
METRICS = {
    "response_time": "Average API response time",
    "agent_tool_usage": "Which tools are called most",
    "query_success_rate": "% of successful recommendations",
    "embedding_cache_hit_rate": "Vector search efficiency"
}
```

## 🔮 Future Enhancements

### Planned Features
- **Session Persistence**: Redis-backed conversation memory
- **Advanced Reranking**: Custom reranking models for better relevance
- **Real-time Updates**: WebSocket support for streaming responses
- **Multi-modal Search**: Image-based restaurant discovery
- **Analytics Dashboard**: Query insights and recommendation metrics

### Integration Opportunities
- **External APIs**: Yelp, OpenTable for real-time data
- **Social Media**: Instagram/Twitter sentiment analysis
- **Event Data**: Real-time crowd and special event information

## 🎯 Development Guidelines

### Code Organization
- **Single Responsibility**: Each module has a clear purpose
- **Type Hints**: All functions use proper type annotations
- **Error Handling**: Comprehensive exception handling with proper logging
- **Documentation**: Docstrings for all public functions

### Best Practices
- Use Pydantic models for request/response validation
- Implement proper logging with structured formats
- Add rate limiting for production deployments
- Use dependency injection for testable components

This backend provides a robust, scalable foundation for AI-powered restaurant recommendations with modern Python patterns and production-ready architecture.