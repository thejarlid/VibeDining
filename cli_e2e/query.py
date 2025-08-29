import asyncio
import json
import sqlite3
from typing import Dict, List, Optional, Tuple, TypedDict, Annotated
from dataclasses import dataclass
from enum import Enum
import re

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from dotenv import load_dotenv
import os

from indexer import ChromaStore, SQLiteStore

load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')


class QueryType(Enum):
    RESTAURANT_RECOMMENDATION = "restaurant_recommendation"
    RESTAURANT_INFO = "restaurant_info"
    OFF_TOPIC = "off_topic"


@dataclass
class SearchResults:
    vector_results: List[Tuple[float, str, str, str, str]]  # (score, name, type, id, document)
    sql_results: List[Dict]
    combined_results: List[Dict]
    web_search_results: Optional[List[Dict]] = None


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    query: str
    query_type: QueryType
    search_results: Optional[SearchResults]
    sql_query_result: Optional[str]
    final_response: Optional[str]
    enable_web_search: bool


class RestaurantRecommendationAgent:
    def __init__(self, db_path: str = 'places.db', chroma_path: str = 'places_vector_db'):
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.8,  # Higher for more variety
            api_key=OPENAI_API_KEY
        )
        self.llm_mini = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.5,  # Increased for more variety
            api_key=OPENAI_API_KEY
        )
        self.sqlite_store = SQLiteStore(db_path)
        self.chroma_store = ChromaStore(chroma_path)

        # Set up SQL database and toolkit for natural language SQL queries
        self.db = SQLDatabase.from_uri(f"sqlite:///{db_path}")
        self.sql_toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm_mini)
        self.sql_agent = create_sql_agent(
            llm=self.llm_mini,
            toolkit=self.sql_toolkit,
            verbose=True,
            agent_type="openai-tools"
        )

        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        # Add nodes
        graph.add_node("guardrail_check", self._guardrail_check)
        graph.add_node("vector_search", self._vector_search)
        graph.add_node("sql_search", self._sql_search)
        graph.add_node("rerank_and_combine", self._rerank_and_combine)
        graph.add_node("web_search", self._web_search)
        graph.add_node("generate_response", self._generate_response)
        graph.add_node("handle_off_topic", self._handle_off_topic)

        # Add edges
        graph.add_edge(START, "guardrail_check")
        graph.add_conditional_edges(
            "guardrail_check",
            self._route_after_guardrail,
            {
                "continue": "vector_search",
                "off_topic": "handle_off_topic"
            }
        )
        graph.add_edge("vector_search", "sql_search")
        graph.add_edge("sql_search", "rerank_and_combine")
        graph.add_conditional_edges(
            "rerank_and_combine",
            self._route_after_combine,
            {
                "web_search": "web_search",
                "generate": "generate_response"
            }
        )
        graph.add_edge("web_search", "generate_response")
        graph.add_edge("generate_response", END)
        graph.add_edge("handle_off_topic", END)

        return graph.compile()

    async def _guardrail_check(self, state: AgentState) -> AgentState:
        """Check if the query is restaurant/dining related"""
        query = state["query"]

        system_prompt = """You are a guardrail for a restaurant recommendation agent. Your job is to determine if a user query is related to restaurants, dining, food, or venue recommendations.

Classify queries into one of these categories:
1. RESTAURANT_RECOMMENDATION: User wants restaurant/dining recommendations or suggestions
2. RESTAURANT_INFO: User wants information about specific restaurants or dining-related questions  
3. OFF_TOPIC: Query is not related to restaurants, dining, food, or venues

Respond with only the category name (RESTAURANT_RECOMMENDATION, RESTAURANT_INFO, or OFF_TOPIC)."""

        messages = [
            ("system", system_prompt),
            ("human", f'Query: "{query}"')
        ]

        response = self.llm_mini.invoke(messages)
        classification = response.content.strip()

        try:
            query_type = QueryType(classification.lower())
        except ValueError:
            # Default to restaurant recommendation if unclear
            query_type = QueryType.RESTAURANT_RECOMMENDATION

        state["query_type"] = query_type
        return state

    def _route_after_guardrail(self, state: AgentState) -> str:
        """Route based on guardrail check result"""
        if state["query_type"] == QueryType.OFF_TOPIC:
            return "off_topic"
        return "continue"

    async def _vector_search(self, state: AgentState) -> AgentState:
        """Perform vector search using ChromaStore"""
        query = state["query"]

        # Perform vector search with reranking and diversity
        vector_results = self.chroma_store.search(query, n_results=50, rerank=True, diversify=True)

        if not hasattr(state, "search_results") or state["search_results"] is None:
            state["search_results"] = SearchResults(
                vector_results=vector_results,
                sql_results=[],
                combined_results=[]
            )
        else:
            state["search_results"].vector_results = vector_results

        return state

    async def _sql_search(self, state: AgentState) -> AgentState:
        """Use LangChain SQL agent to find restaurants matching query constraints"""
        query = state["query"]

        # Use the SQL agent to find restaurants with proper schema
        schema_context = """
Database Schema:
- Places: id, name, rating, price_level, category, formatted_address, description, business_status
- Localities: id, name, full_name, type ('neighborhood' or 'city')  
- PlaceLocalities: place_id, locality_id (join table)

Sample Data:
- Categories: 'Italian restaurant', 'Coffee shop', 'Bar', 'Japanese restaurant'
- Price levels: '$', '$$', '$$$', '$1-10', '$10-20', '$20-30', '$30-50', '$50-100', '$100+'
- Localities: 'East Village' (neighborhood), 'Williamsburg' (neighborhood), 'New York' (city)

Use JOINs to find places in specific neighborhoods/areas.
"""

        constraint_prompt = f"""
{schema_context}

Analyze this restaurant query: "{query}"

Write a SQL query to find matching restaurants. Use the 3-table schema with JOINs when location is specified.

Examples:
- For "restaurants in East Village": JOIN with Localities and PlaceLocalities
- For price filters: use price_level column  
- For cuisine: use category column
- For ratings: use rating column

Return a complete SQL SELECT statement that finds matching restaurants.
Focus on business_status = 'OPERATIONAL' for active places.
"""

        try:
            # Use the SQL agent to generate and execute the query
            constraint_result = self.sql_agent.invoke({"input": constraint_prompt})

            # Store the SQL agent's result
            where_clause = constraint_result.get("output", "business_status = 'OPERATIONAL'")

            # The SQL agent should have executed a query - let's parse its results
            # For now, we'll extract any restaurants mentioned in the output
            # In a production system, you might want to parse the actual SQL results more carefully

            if state["search_results"] is None:
                state["search_results"] = SearchResults(
                    vector_results=[],
                    sql_results=[],  # We'll populate this from the SQL agent result if needed
                    combined_results=[]
                )

        except Exception as e:
            print(f"SQL agent error: {e}")
            state["sql_query_result"] = f"SQL search failed: {str(e)}"
            if state["search_results"] is None:
                state["search_results"] = SearchResults(
                    vector_results=[],
                    sql_results=[],
                    combined_results=[]
                )

        return state

    async def _rerank_and_combine(self, state: AgentState) -> AgentState:
        """Combine and deduplicate results from vector search and SQL agent"""
        search_results = state["search_results"]
        vector_results = search_results.vector_results
        sql_query_result = state.get("sql_query_result", "")

        # For now, we'll primarily use vector search results and include SQL context
        # In a more sophisticated implementation, you could parse the SQL agent's
        # actual query results and cross-reference with vector results

        combined_places = {}

        # Add vector results (with scores)
        for score, name, doc_type, place_id, document in vector_results:
            if place_id not in combined_places:
                combined_places[place_id] = {
                    "id": place_id,
                    "name": name,
                    "vector_score": score,
                    "documents": {doc_type: document},
                    "sql_context": sql_query_result  # Include SQL agent insights
                }
            else:
                combined_places[place_id]["documents"][doc_type] = document

        # Sort by vector score with some randomization for variety
        import random
        all_results = sorted(
            combined_places.values(),
            key=lambda x: x["vector_score"],
            reverse=True
        )

        # Add randomization: keep top 5, shuffle next 10, take 7 more
        if len(all_results) >= 15:
            top_results = all_results[:5]
            middle_pool = all_results[5:15]
            random.shuffle(middle_pool)
            combined_results = top_results + middle_pool[:7]
        else:
            combined_results = all_results[:12]

        search_results.combined_results = combined_results
        return state

    def _route_after_combine(self, state: AgentState) -> str:
        """Decide whether to perform web search or generate response"""
        search_results = state["search_results"]
        combined_results = search_results.combined_results

        # Determine if we need web search enrichment
        needs_enrichment = (
            len(combined_results) < 5 or  # Too few results
            state.get("enable_web_search", False) or  # Explicitly requested
            # Check if results have low confidence/scores
            (combined_results and
             len([r for r in combined_results if r.get("vector_score", 0) > 0.7]) < 3)
        )

        if needs_enrichment:
            return "web_search"
        return "generate"

    async def _web_search(self, state: AgentState) -> AgentState:
        """Optional web search for freshness (stub implementation)"""
        # This is a stub - you can integrate with your preferred web search API
        # For now, we'll just add a placeholder

        search_results = state["search_results"]
        web_results = []

        # Example: Search for recent reviews or updates about top restaurants
        for result in search_results.combined_results[:3]:
            restaurant_name = result["name"]
            # Placeholder for web search
            web_results.append({
                "restaurant_name": restaurant_name,
                "recent_info": f"Recent web search results for {restaurant_name} would go here",
                "source": "web_search_placeholder"
            })

        search_results.web_search_results = web_results
        return state

    async def _generate_response(self, state: AgentState) -> AgentState:
        """Generate final response to user"""
        query = state["query"]
        search_results = state["search_results"]
        sql_query_result = state.get("sql_query_result", "")

        # Prepare context for response generation
        context_parts = []

        for i, result in enumerate(search_results.combined_results[:5], 1):
            place_info = []
            place_info.append(f"{i}. **{result['name']}**")

            # Add vector search documents
            for doc_type, document in result["documents"].items():
                place_info.append(f"{doc_type.title()}: {document}")

            context_parts.append("\n".join(place_info))

        context = "\n\n".join(context_parts)

        # Add web search results if available
        web_context = ""
        if search_results.web_search_results:
            web_context = "\n\nRecent web information:\n"
            for web_result in search_results.web_search_results:
                web_context += f"- {web_result['restaurant_name']}: {web_result['recent_info']}\n"

        # Include SQL agent insights
        sql_context = ""
        if sql_query_result:
            sql_context = f"\n\nSQL Database Analysis:\n{sql_query_result}\n"

        prompt = f"""
You are a knowledgeable restaurant recommendation assistant. Based on the user's query and the restaurant data provided, give a helpful, conversational response.

User Query: "{query}"

Restaurant Data:
{context}{sql_context}{web_context}

Provide a natural, helpful response that:
1. Directly addresses the user's query
2. Recommends 2-3 top restaurants from the data
3. Explains why each recommendation fits their needs
4. Mentions any important details (price, location, atmosphere, etc.)
5. Offers to help with follow-up questions

Keep the tone friendly and conversational.
"""

        llm_response = self.llm.with_config({"temperature": 0.9})

        messages = [
            ("system", "You are a helpful restaurant recommendation assistant."),
            ("human", prompt)
        ]

        response = llm_response.invoke(messages)
        final_response = response.content
        state["final_response"] = final_response
        state["messages"].append(AIMessage(content=final_response))

        return state

    async def _handle_off_topic(self, state: AgentState) -> AgentState:
        """Handle queries that are not restaurant-related"""
        off_topic_response = (
            "I'm a restaurant recommendation assistant focused on helping you find great places to dine. "
            "I can help you discover restaurants, get information about dining spots, or answer food-related questions. "
            "Is there anything about restaurants or dining I can help you with?"
        )

        state["final_response"] = off_topic_response
        state["messages"].append(AIMessage(content=off_topic_response))

        return state

    async def query(self, user_query: str, enable_web_search: bool = False) -> str:
        """Main entry point for querying the agent"""
        initial_state = {
            "messages": [HumanMessage(content=user_query)],
            "query": user_query,
            "query_type": QueryType.RESTAURANT_RECOMMENDATION,
            "search_results": None,
            "sql_query_result": None,
            "final_response": None,
            "enable_web_search": enable_web_search
        }

        final_state = await self.graph.ainvoke(initial_state)
        return final_state["final_response"]


# Example usage
if __name__ == "__main__":
    async def main():
        agent = RestaurantRecommendationAgent()

        # Test queries
        queries = [
            "I want a casual Korean restaurant that serves great cocktails and isn't too expensive",
            "What's the weather like today?",  # Off-topic
            "Tell me about the best sushi places in East Village",
            "I'm looking for a romantic dinner spot with outdoor seating",
            "Find me a coffee shop in williamsburg that might have space to work at"
        ]

        for query in queries:
            print(f"\nQuery: {query}")
            print("="*50)
            response = await agent.query(query, enable_web_search=False)
            print(response)
            print("\n")

    # Run the example
    asyncio.run(main())
