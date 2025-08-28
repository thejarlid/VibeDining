import json
import numpy as np
from typing import Dict, List
import sqlite3

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

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
    """Enhanced search tools for conversational restaurant recommendations"""

    def __init__(self, db_path: str = 'places.db', chroma_path: str = 'places_vector_db'):
        self.sqlite_store = SQLiteStore(db_path)
        self.chroma_store = ChromaStore(chroma_path)

        # SQL agent for complex queries
        self.db = SQLDatabase.from_uri(f"sqlite:///{db_path}")
        self.llm_mini = ChatOpenAI(model="gpt-4o-mini", temperature=0.3, api_key=OPENAI_API_KEY)
        self.sql_toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm_mini)
        self.sql_agent = create_sql_agent(
            llm=self.llm_mini,
            toolkit=self.sql_toolkit,
            agent_type="openai-tools"
        )
        self.db_conn = sqlite3.connect('places.db')

    def vector_search(self, query: str, n_results: int = 20) -> List[Dict]:
        """Search for restaurants using semantic similarity. Best for atmosphere, vibe, and qualitative features."""
        try:
            results = self.chroma_store.search(query, n_results=n_results, rerank=True)

            formatted_results = []
            for score, name, doc_type, place_id, document in results:
                formatted_results.append({
                    "name": name,
                    "id": place_id,
                    "relevance_score": round(float(score), 3),
                    "content_type": doc_type,
                    "description": document
                })

            return formatted_results

        except Exception as e:
            return [{"error": f"Vector search failed: {str(e)}"}]

    def sql_search(self, query_description: str) -> List[Dict]:
        """Search using SQL for specific constraints like location, price, cuisine, rating."""
        try:
            schema_context = """
Database Schema:
- Places: id, name, rating, price_level, category, formatted_address, description, business_status, latitude, longitude
- Localities: id, name, full_name, type ('neighborhood' or 'city'), latitude, longitude  
- PlaceLocalities: place_id, locality_id (join table connecting places to their neighborhoods/cities)

Sample Data:
- Categories: 'Italian restaurant', 'Coffee shop', 'Bar', 'Japanese restaurant', 'French restaurant'
- Price levels: '$', '$$', '$$$', '$1-10', '$10-20', '$20-30', '$30-50', '$50-100', '$100+'
- Localities: 'East Village' (neighborhood), 'Williamsburg' (neighborhood), 'Tribeca' (neighborhood), 'New York' (city)

Use JOINs to find places in specific neighborhoods or cities.
Example: SELECT p.name, p.rating, p.price_level, p.category, p.formatted_address FROM Places p 
JOIN PlaceLocalities pl ON p.id = pl.place_id 
JOIN Localities l ON pl.locality_id = l.id 
WHERE LOWER(l.name) LIKE LOWER('%East Village%')
"""

            sql_prompt = f"""
{schema_context}

User request: {query_description}

Write and EXECUTE a SQL query using the 3-table schema. Use JOINs when location is specified.
Use CASE-INSENSITIVE matching for location names (LOWER() function).
Return actual restaurant data: names, ratings, categories, addresses, price levels.

EXECUTE the query and return the actual results, not just the SQL code.
"""

            result = self.sql_agent.invoke({"input": sql_prompt})
            return [{"sql_result": result.get("output", "No results")}]

        except Exception as e:
            return [{"error": f"SQL search failed: {str(e)}"}]

    def get_restaurant_details(self, place_id: str) -> Dict:
        """Get detailed information about a specific restaurant."""
        try:
            cursor = self.db_conn.cursor()

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

    def validate_location_match(self, place_ids: List[str], target_location: str) -> Dict:
        """Validate if a restaurant matches the target location."""
        try:
            cursor = self.db_conn.cursor()
            # Build query with multiple place IDs
            place_ids_str = ','.join(['?' for _ in place_ids])
            cursor.execute(f"""
                SELECT p.id, p.name, l.name, l.full_name, l.type
                FROM Places p
                JOIN PlaceLocalities pl ON p.id = pl.place_id
                JOIN Localities l ON pl.locality_id = l.id
                WHERE p.id IN ({place_ids_str})
            """, place_ids)

            results = cursor.fetchall()

            if not results:
                return {"error": "No restaurants found or no locality data available"}

            target_lower = target_location.lower()
            restaurants_data = {}

            # Group results by restaurant
            for place_id, rest_name, locality_name, locality_full_name, locality_type in results:
                if (target_lower in locality_name.lower() or target_lower in locality_full_name.lower()):
                    if place_id not in restaurants_data:
                        restaurants_data[place_id] = {
                            "restaurant_name": rest_name,
                            "matching_localities": [],
                            "all_localities": [],
                            "target_location": target_location
                        }

                    restaurants_data[place_id]["all_localities"].append(f"{locality_name} ({locality_type})")
                    restaurants_data[place_id]["matching_localities"].append(locality_name)

            return {
                "restaurants": list(restaurants_data.values()),
                "target_location": target_location
            }

        except Exception as e:
            return {"error": f"Location validation failed: {str(e)}"}


class SimpleConversationalRestaurantAgent:
    """Simple conversational restaurant agent using LangGraph's built-in memory"""

    def __init__(self, debug: bool = False):
        self.debug = debug

        # Use LangGraph's built-in memory for conversation persistence
        self.memory = MemorySaver()

        self.llm = ChatOpenAI(
            model="gpt-5-mini",
            temperature=0.7,
            api_key=OPENAI_API_KEY
        )
        self.tools = RestaurantSearchTools()
        self.agent = self._build_agent()

    def _build_agent(self):
        """Build the conversational agent with memory"""

        # Create react agent with built-in conversation memory
        agent = create_react_agent(
            model=self.llm.with_config({"tags": ["restaurant_agent"]}),
            tools=[
                self.tools.vector_search,
                # self.tools.sql_search,
                self.tools.get_restaurant_details,
                self.tools.validate_location_match
            ] + self.tools.sql_toolkit.get_tools(),
            checkpointer=self.memory  # This enables conversation memory
        )

        return agent

    def chat(self, user_input: str, session_id: str = "default") -> str:
        """Chat with the agent, maintaining conversation history"""
        try:
            if self.debug:
                print(f"🗣️ User: {user_input}")

            # Check if this is the first message in the conversation
            current_state = self.agent.get_state(config={"configurable": {"thread_id": session_id}})
            messages = current_state.values.get("messages", [])

            # Add system message if this is the first interaction
            if not messages:
                system_prompt = """
You are an expert conversational restaurant recommendation assistant with perfect memory and access to indexed restaurant data. Users describe the vibe/atmosphere they want and often specify locations, price ranges, or cuisine types.
Users will often ask in an iterative manner over a course of multiple messages and your ability to maintain context is critical.

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
- **Description**

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
- **Description:** High-end sushi & Japanese dishes in a chic, trendy atmosphere. Romantic, upscale, and trendy, with a well-heeled crowd. Reservations are recommended.

You can make multiple tool calls, analyze results, and make additional calls as needed.
"""

                result = self.agent.invoke(
                    {"messages": [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_input)
                    ]},
                    config={"configurable": {"thread_id": session_id}}
                )
            else:
                # Use LangGraph's built-in conversation memory
                result = self.agent.invoke(
                    {"messages": [HumanMessage(content=user_input)]},
                    config={"configurable": {"thread_id": session_id}}
                )

            # Extract the final response
            final_message = result["messages"][-1]
            response = final_message.content if hasattr(final_message, 'content') else str(final_message)

            if self.debug:
                print(f"🤖 Agent: {response[:100]}...")

            return response

        except Exception as e:
            error_msg = f"Error processing your request: {str(e)}"
            if self.debug:
                print(f"❌ Error: {error_msg}")
            return error_msg

    def get_conversation_history(self, session_id: str = "default") -> List[Dict]:
        """Get the conversation history for a session"""
        try:
            # Get the conversation state from memory
            state = self.agent.get_state(config={"configurable": {"thread_id": session_id}})
            messages = state.values.get("messages", [])

            history = []
            for i, msg in enumerate(messages):
                if hasattr(msg, 'content'):
                    msg_type = "User" if isinstance(msg, HumanMessage) else "Agent"
                    history.append({
                        "turn": i // 2 + 1,
                        "type": msg_type,
                        "content": msg.content
                    })

            return history

        except Exception as e:
            if self.debug:
                print(f"❌ Error getting history: {e}")
            return []

    def reset_conversation(self, session_id: str = "default"):
        """Reset conversation for a specific session"""
        try:
            # Clear the conversation state
            self.agent.update_state(
                config={"configurable": {"thread_id": session_id}},
                values={"messages": []}
            )
            print(f"🔄 Conversation reset for session: {session_id}")
        except Exception as e:
            if self.debug:
                print(f"❌ Error resetting conversation: {e}")

    def print_conversation_history(self, session_id: str = "default"):
        """Print a readable conversation history"""
        history = self.get_conversation_history(session_id)

        if not history:
            print("No conversation history found.")
            return

        print("\n" + "="*60)
        print(f"CONVERSATION HISTORY (Session: {session_id})")
        print("="*60)

        current_turn = 0
        for entry in history:
            if entry["turn"] != current_turn:
                current_turn = entry["turn"]
                print(f"\n--- Turn {current_turn} ---")

            print(f"{entry['type']}: {entry['content']}")

        print("="*60 + "\n")


# Example usage and interactive interface
if __name__ == "__main__":
    def main():
        agent = SimpleConversationalRestaurantAgent(debug=True)
        session_id = "main_session"

        print("🍽️ Simple Conversational Restaurant Agent")
        print("=" * 50)
        print("Commands:")
        print("  'quit' or 'exit' - Exit the conversation")
        print("  'reset' - Start a new conversation")
        print("  'history' - Show conversation history")
        print("  'new session <name>' - Start a new named session")
        print("=" * 50)
        print()

        while True:
            user_input = input(f"[{session_id}] You: ").strip()

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye! 🍽️")
                break
            elif user_input.lower() == 'reset':
                agent.reset_conversation(session_id)
                continue
            elif user_input.lower() == 'history':
                agent.print_conversation_history(session_id)
                continue
            elif user_input.lower().startswith('new session'):
                parts = user_input.split(' ', 2)
                if len(parts) >= 3:
                    session_id = parts[2]
                    print(f"🔄 Switched to session: {session_id}")
                else:
                    print("Usage: new session <session_name>")
                continue
            elif not user_input:
                continue

            try:
                response = agent.chat(user_input, session_id)
                print(f"Agent: {response}\n")
            except Exception as e:
                print(f"Error: {e}\n")

    main()
