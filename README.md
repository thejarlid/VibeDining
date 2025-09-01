# VibeDining

An AI-powered restaurant recommendation platform that helps you discover great dining spots through natural conversation. Ask for restaurants by vibe, location, cuisine, or mood - get personalized suggestions from your saved places.

## ✨ Features

- **Natural Language Queries**: "Find me a cozy coffee shop in Williamsburg where I can work"
- **Smart Recommendations**: Combines location, vibe, cuisine, and price preferences
- **Personalized Results**: Uses your actual saved restaurant data
- **Honest Responses**: Transparent about data limitations
- **Modern Chat Interface**: Clean, responsive conversation UI

## 🚀 Quick Start

### Prerequisites
- Node.js 18+ and npm
- Python 3.11+
- OpenAI API key

### Setup & Run
```bash
# Clone and install
git clone <repository-url>
cd vibedining

# Backend setup
cd backend
pip install -r requirements.txt
echo "OPENAI_API_KEY=your_key_here" > .env

# Frontend setup
cd ../frontend
npm install

# Run both services
cd ../backend && python main.py &    # Backend on :8000
cd ../frontend && npm run dev        # Frontend on :3000
```

Visit http://localhost:3000 to start chatting with your personal restaurant assistant!

## 🏗️ Architecture

**Frontend**: Next.js + TypeScript with React chat interface  
**Backend**: FastAPI with LangGraph AI agents  
**Data**: SQLite + ChromaDB vector search  
**AI**: OpenAI GPT models with intelligent tool selection

## 💡 How It Works

1. **Import Your Data**: Process Google Takeout saved places
2. **Smart Indexing**: Creates searchable database with semantic understanding  
3. **Conversational AI**: LangGraph agents intelligently combine multiple search strategies
4. **Quality Control**: Validates results and provides honest feedback about data limitations

## 📁 Project Structure

```
vibedining/
├── frontend/          # Next.js chat interface
├── backend/           # FastAPI server with AI agents  
├── cli_e2e/          # Data processing tools
└── README.md         # This overview
```

---

*Built for personalized restaurant discovery through intelligent conversation.*