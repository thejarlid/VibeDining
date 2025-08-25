import json
import numpy as np
from typing import Dict, List, Optional
from IPython.display import Image, display
import sqlite3

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState

from pydantic import BaseModel, Field

from dotenv import load_dotenv

import os

from indexer import ChromaStore, SQLiteStore

load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')


def safe_json_serialize(obj):
    """Safely serialize objects to JSON, handling numpy types"""
    if isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: safe_json_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [safe_json_serialize(item) for item in obj]
    else:
        return obj


class RestaurantSearchTools:
    """Tool functions that the LLM can call"""

    def __init__(self, db_path: str = 'places.db', chroma_path: str = 'places_vector_db'):
        self.sqlite_store = SQLiteStore(db_path)
        self.chroma_store = ChromaStore(chroma_path)

        # SQL agent for complex queries
        self.db = SQLDatabase.from_uri(f"sqlite:///{db_path}")
        self.llm_mini = ChatOpenAI(model="gpt-5-mini", temperature=0.3, api_key=OPENAI_API_KEY)
        self.sql_toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm_mini)
        self.sql_agent = create_sql_agent(
            llm=self.llm_mini,
            toolkit=self.sql_toolkit,
            agent_type="openai-tools"
        )

    def vector_search(self, query: str, n_results: int = 20) -> List[Dict]:
        """Search for restaurants using semantic similarity of the query. This is best for query against more qualitative
        features such as atmosphere and vibe. The vector store stores saved reviews, natural language descriptions, and a
        summary of the food options."""
        try:
            results = self.chroma_store.search(query, n_results=n_results, rerank=True)

            formatted_results = []
            for score, name, doc_type, place_id, document in results:
                formatted_results.append({
                    "name": name,
                    "id": place_id,
                    "relevance_score": round(float(score), 3),  # Convert to regular Python float
                    "content_type": doc_type,
                    "description": document
                })

            return formatted_results

        except Exception as e:
            return [{"error": f"Vector search failed: {str(e)}"}]

    def web_search(self, search_query: str, restaurant_name: str = None) -> List[Dict]:
        """Search for current restaurant information online"""
        pass

    def validate_location_match(self, place_id: str, target_location: str) -> Dict:
        """Validate if a restaurant is actually in the target location/neighborhood.

        Gets all localities connected to the place through the join table and checks if the 
        target location is contained in any locality name or full_name."""
        try:
            conn = sqlite3.connect('places.db')
            cursor = conn.cursor()

            # Get all localities for this place through the join table
            cursor.execute("""
                SELECT p.name, l.name, l.full_name, l.type
                FROM Places p
                JOIN PlaceLocalities pl ON p.id = pl.place_id
                JOIN Localities l ON pl.locality_id = l.id
                WHERE p.id = ?
            """, (place_id,))

            results = cursor.fetchall()
            conn.close()

            if not results:
                return {"error": "Restaurant not found or has no locality data"}

            restaurant_name = results[0][0]  # All rows have same restaurant name
            target_lower = target_location.lower()

            # Check if target location is contained in any locality name or full_name
            matches = []
            localities = []

            for _, locality_name, locality_full_name, locality_type in results:
                localities.append(f"{locality_name} ({locality_type})")

                # Check if target is contained in locality name or full name
                if (target_lower in locality_name.lower() or
                        target_lower in locality_full_name.lower()):
                    matches.append(locality_name)

            return {
                "restaurant_name": restaurant_name,
                "matches_location": len(matches) > 0,
                "matching_localities": matches,
                "all_localities": localities,
                "target_location": target_location
            }

        except Exception as e:
            return {"error": f"Location validation failed: {str(e)}"}

    def get_restaurant_details(self, place_id: str) -> Dict:
        """Get detailed information about a specific restaurant with locality info"""
        try:
            conn = sqlite3.connect('places.db')
            cursor = conn.cursor()

            # Get restaurant details with localities
            cursor.execute("""
                SELECT p.name, p.rating, p.price_level, p.category, p.formatted_address, 
                       p.description, p.reviews_json, p.atmosphere_json,
                       GROUP_CONCAT(l.name || ' (' || l.type || ')') as localities
                FROM Places p
                LEFT JOIN PlaceLocalities pl ON p.id = pl.place_id
                LEFT JOIN Localities l ON pl.locality_id = l.id
                WHERE p.id = ?
                GROUP BY p.id
            """, (place_id,))

            result = cursor.fetchone()
            conn.close()

            if result:
                return {
                    "name": result[0],
                    "rating": result[1],
                    "price_level": result[2],
                    "category": result[3],
                    "address": result[4],
                    "description": result[5],
                    "reviews": json.loads(result[6]) if result[6] else [],
                    "atmosphere": json.loads(result[7]) if result[7] else [],
                    "neighborhoods": result[8] if result[8] else "Location data unavailable"
                }
            else:
                return {"error": "Restaurant not found"}

        except Exception as e:
            return {"error": f"Database query failed: {str(e)}"}


class GuardrailResult(BaseModel):
    allowed: bool = Field(description="Whether the user query is related to restaurants, dining, food, or venue recommendations.")
    reason: str = Field(description="Why this query is or is not relevant to the user's request.")


# Extend the AgentState from LangGraph to add our custom fields
class State(AgentState):
    # Our additional fields
    input: str
    output: Optional[str]
    guardrail_result: Optional[GuardrailResult]


class AgenticRecommender:
    """A fully agentic approach to the restaurant recommender leveraging a set of tools"""

    def __init__(self, debug: bool = False):
        self.debug = debug

        self.llm = ChatOpenAI(
            model="gpt-5",
            temperature=0.7,
            api_key=OPENAI_API_KEY
        )
        self.llm_mini = ChatOpenAI(
            model="gpt-5-mini",
            temperature=0.3,
            api_key=OPENAI_API_KEY
        )

        self.agent_llm = self.llm.bind(system=self._get_agent_system_prompt())
        self._guardrail_llm = self.llm_mini.with_structured_output(GuardrailResult)
        self.tools = RestaurantSearchTools()
        self.graph = self._build_graph()

        if debug:
            display(Image(self.graph.get_graph().draw_mermaid_png()))

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(State)

        # Create the react agent that will work directly with our extended state
        agent_sub_graph = create_react_agent(
            model=self.agent_llm,
            tools=[self.tools.vector_search, self.tools.validate_location_match, self.tools.get_restaurant_details] + self.tools.sql_toolkit.get_tools())

        graph.add_node("guardrail", self._guardrail)
        graph.add_node("agent", agent_sub_graph)
        graph.add_node("block_request", self._block_request)

        graph.add_edge(START, "guardrail")

        graph.add_conditional_edges(
            "guardrail",
            self._guardrail_routing,
            {
                "agent": "agent",
                "block_request": "block_request"
            }
        )
        graph.add_edge("agent", END)
        graph.add_edge("block_request", END)

        return graph.compile()

    def _guardrail(self, state: State):
        """Guardrail to check if the user's query is restaurant-related and related to the conversaion"""
        system_prompt = """You are a guardrail for a restaurant recommendation agent. Your job is to determine if a user query is related to restaurants, dining, food, or venue recommendations."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=state["input"])
        ]

        guardrail_result = self._guardrail_llm.invoke(messages)

        # Initialize messages for the agent if they don't exist
        agent_messages = state.get("messages", [])
        if not agent_messages:
            agent_messages = [HumanMessage(content=state["input"])]

        return {
            "guardrail_result": guardrail_result,
            "messages": agent_messages
        }

    def _guardrail_routing(self, state: State):
        # Return the node name you want to visit next
        if state["guardrail_result"].allowed:
            return "agent"
        else:
            return "block_request"

    def _block_request(self, state: State):
        """Block request to the agent"""
        reason = state["guardrail_result"].reason if state["guardrail_result"] else "I'm unable to help with this request."
        return {"output": reason}

    def _get_agent_system_prompt(self):
        # System prompt that gives the LLM access to tools
        system_prompt = f"""
        You are an expert restaurant recommendation assistant with access to search tools.

        You are a restaurant concierge with access to indexed restaurant data. Users describe the vibe/atmosphere they want and often specify locations, price ranges, or cuisine types.

        TOOL USAGE STRATEGY:
        1. **vector_search**: Use for qualitative queries (atmosphere, vibe, "cozy", "romantic", "good for work")
        2. **sql_search**: Use for specific constraints:
           - Neighborhoods: "in East Village", "Williamsburg area", "near Union Square"
           - Price ranges: "cheap", "expensive", "$$ level", "under $20"
           - Ratings: "highly rated", "4+ stars"
           - Cuisine: "Italian", "sushi", "coffee shops"
           - Use OR to get more options unless the user really stresses that they want to have hard constraints.
           - Use CASE-INSENSITIVE matching for location names (LOWER() function)
           - For price filters, map natural language to actual price_level values
           - Categories: 'Italian restaurant', 'Coffee shop', 'Bar', 'Japanese restaurant', 'French restaurant'
           - Price levels: '$', '$$', '$$$', '$1-10', '$10-20', '$20-30', '$30-50', '$50-100', '$100+'
           - Localities: 'East Village' (neighborhood), 'Williamsburg' (neighborhood), 'Tribeca' (neighborhood), 'New York' (city)
        3. **validate_location_match**: Use to verify if places actually match the user's location constraint
        4. **get_restaurant_details**: Use to get full info about specific places from other searches

        RECOMMENDED APPROACH:
        1. Perform both sql_search and vector_search to get comprehensive results
        2. VALIDATE each result against user constraints:
           - Location: Does the address/neighborhood actually match what they asked for?
           - Category: Is it actually the type of place they want (coffee shop, restaurant, etc.)?
           - Other criteria: Price, rating, etc.
        3. FILTER OUT results that don't meet the constraints
        4. If few/no quality results remain, BE HONEST about data limitations

        QUALITY CONTROL:
        - If a result doesn't match the location constraint, EXCLUDE it
        - If you have < 3 good matches, acknowledge limited data in your saved lists
        - Be transparent about data gaps and suggest that more places could be found with web search

        RESPONSE FORMAT when you have good results:
        Present as numbered list with:
        - **Name**
        - **Rating** 
        - **Address**
        - **Price Level**
        - **Why it matches** (your reasoning)

        RESPONSE FORMAT when data is limited:
        "I found [X] places in your saved lists that match your criteria, but the selection is limited. Here's what I found:
        [list the few good matches]
        
        Your saved lists don't seem to have many [coffee shops/restaurants] in [location]. In the future, I could search the web to find additional options that match your preferences."

        ALWAYS prioritize accuracy over quantity - better to admit limited data than give irrelevant results!

        Find multiple options that match the user's query and return them in the following format. If you don't find any options, return a message that you don't have any recommendations for that query.
        Example:
        User Query: "I want to find a sushi restaurant for a romantic date night"

        1. **Sushi Noz**
        - **Address:** 181 E 78th St, New York, NY 10075
        - **Price Level:** $100+
        - **Rating:** 4.5
        - **Description:** Zen-like outlet for high-end, seasonal sushi & nigiri, served omakase-only in a wood-lined space.
        - **Atmosphere:** Cozy and upscale, perfect for intimate meals. Reservations are required.
        - **Neighborhood:** Upper East Side, New York City
        - **Summarized Description:** Zen-like outlet for high-end, seasonal sushi & nigiri, served omakase-only in a wood-lined space.

        2. **Neta Shari**
        - **Address:** 1718 86th St, Brooklyn, NY 11214
        - **Price Level:** $100+
        - **Rating:** 4.7
        - **Description:** Specializes in exquisite omakase, with highlights like king salmon and wagyu.
        - **Atmosphere:** Cozy and trendy with a quiet environment. Reservations are required.
        - **Neighborhood:** Bath Beach, New York City
        - **Summarized Description:** Specializes in exquisite omakase, with highlights like king salmon and wagyu.

        3. **BONDST**
        - **Address:** 6 Bond St, New York, NY 10012
        - **Price Level:** $100+
        - **Rating:** 4.5
        - **Description:** High-end sushi & Japanese dishes in a chic, trendy atmosphere.
        - **Atmosphere:** Romantic, upscale, and trendy, with a well-heeled crowd. Reservations are recommended.
        - **Neighborhood:** NoHo, New York City
        - **Summarized Description:** High-end sushi & Japanese dishes in a chic, trendy atmosphere. Romantic, upscale, and trendy, with a well-heeled crowd. Reservations are recommended.

        You can make multiple tool calls, analyze results, and make additional calls as needed.
        Always end with a conversational response to the user.
        """
        return system_prompt

    def query(self, user_query: str) -> str:
        """Query the agent with optional detailed tracing"""
        # Standard execution
        result = self.graph.invoke({"input": user_query})
        return self._extract_response(result)

    def _extract_response(self, result):
        """Extract the final response from the result"""
        if not result:
            return "No response generated"

        # If we have a direct output from blocked request, use that
        if result.get("output"):
            return result["output"]

        # Otherwise extract from the final message
        if result.get("messages"):
            final_message = result["messages"][-1]
            return final_message.content if hasattr(final_message, 'content') else str(final_message)

        return "No response generated"


# Example usage
if __name__ == "__main__":
    def main():
        agent = AgenticRecommender()

        test_queries = [
            "Find me a cozy coffee shop in Williamsburg where I can work",
            # "I want expensive sushi for a date night",
            # "What are some cheap eats under $15 near Union Square?",
            # "Tell me about Korean BBQ places with good atmosphere"
        ]

        for query in test_queries:
            print(f"\n{'='*60}")
            print(f"Query: {query}")
            print('='*60)
            response = agent.query(query)
            print(response)
            print("\n")

    main()
