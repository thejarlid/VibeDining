import sqlite3
import chromadb
from model import Place
import pandas as pd
import json
from model import Place, CSVPlaceData, PlaceBasicData, PlaceScrapedData
from collections import namedtuple
import chromadb.utils.embedding_functions as embedding_functions
from dotenv import load_dotenv
import os
from pprint import pprint
from openai import OpenAI

Locality = namedtuple('Locality', ['id', 'name', 'full_name', 'latitude', 'longitude', 'type'])
load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')


def extract_locality_data_from_geocode_neighbourhoods(geocode_neighbourhoods: list[dict]) -> dict[str, Locality]:

    def _extract_locality_data(locality: dict, type: str) -> Locality:
        return Locality(
            id=locality['place_id'],
            name=locality['address_components'][0]['long_name'],
            full_name=locality['formatted_address'],
            latitude=locality['geometry']['location']['lat'],
            longitude=locality['geometry']['location']['lng'],
            type=type
        )

    localities = {}

    if len(geocode_neighbourhoods) > 1:
        for geocoded_neighbourhood in geocode_neighbourhoods[:-1]:
            neighborhood = _extract_locality_data(geocoded_neighbourhood, 'neighborhood')
            localities[neighborhood.id] = neighborhood
        city = _extract_locality_data(geocode_neighbourhoods[-1], 'city')
        localities[city.id] = city
    elif len(geocode_neighbourhoods) == 1:
        city = _extract_locality_data(geocode_neighbourhoods[0], 'city')
        localities[city.id] = city

    return localities


class SQLiteStore:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Places (
                id TEXT PRIMARY KEY,
                name TEXT,
                url TEXT,
                business_status TEXT,
                formatted_address TEXT,
                latitude REAL,
                longitude REAL,
                place_types_json TEXT,
                rating REAL,
                price_level TEXT,
                category TEXT,
                description TEXT,
                reviews_json TEXT,
                atmosphere_json TEXT,
                geocode_neighbourhoods_json TEXT,
                last_scraped TEXT
            )
        """)

        self.cursor.execute("""

            CREATE TABLE IF NOT EXISTS Localities (
                id TEXT PRIMARY KEY,
                name TEXT,
                full_name TEXT,
                latitude REAL,
                longitude REAL,
                type TEXT CHECK(type IN ('neighborhood', 'city'))
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS PlaceLocalities(
                place_id TEXT REFERENCES places(id),
                locality_id INTEGER REFERENCES localities(id),
                PRIMARY KEY(place_id, locality_id)
            )
        """)
        self.conn.commit()

    def save(self, place: Place):
        try:
            locality_data = extract_locality_data_from_geocode_neighbourhoods(place.geocode_neighbourhoods)

            # add all the localities to the database
            for locality_id, locality in locality_data.items():
                self.cursor.execute("INSERT OR IGNORE INTO Localities (id, name, full_name, latitude, longitude, type) VALUES (?, ?, ?, ?, ?, ?)",
                                    (locality_id, locality.name, locality.full_name, locality.latitude, locality.longitude, locality.type))

            # add the place to the database
            self.cursor.execute("""INSERT INTO Places (id, name, url, business_status, formatted_address, latitude, longitude, place_types_json, rating, price_level, category, description, reviews_json, atmosphere_json, geocode_neighbourhoods_json, last_scraped) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT(id) DO UPDATE SET
                                    id=excluded.id,
                                    name=excluded.name,
                                    url=excluded.url,
                                    business_status=excluded.business_status,
                                    formatted_address=excluded.formatted_address,
                                    latitude=excluded.latitude,
                                    longitude=excluded.longitude,
                                    place_types_json=excluded.place_types_json,
                                    rating=excluded.rating,
                                    price_level=excluded.price_level,
                                    category=excluded.category,
                                    description=excluded.description,
                                    reviews_json=excluded.reviews_json,
                                    atmosphere_json=excluded.atmosphere_json,
                                    geocode_neighbourhoods_json=excluded.geocode_neighbourhoods_json,
                                    last_scraped=excluded.last_scraped
                                """,
                                (place.place_id, place.name, place.url, place.business_status, place.formatted_address, place.coordinates[0], place.coordinates[1], json.dumps(place.place_types), place.rating, place.price_level, place.category, place.description, json.dumps(place.reviews), json.dumps(place.atmosphere), json.dumps(place.geocode_neighbourhoods), place.last_scraped))

            # add the place to the localities
            for locality_id in locality_data:
                self.cursor.execute("INSERT OR IGNORE INTO PlaceLocalities (place_id, locality_id) VALUES (?, ?)",
                                    (place.place_id, locality_id))

            self.conn.commit()
        except Exception as e:
            if 'UNIQUE constraint failed' in str(e):
                return
            print('Error saving place', place.place_id, e)


class ChromaStore:

    def __init__(self, chroma_path: str):
        self.chroma_client = chromadb.PersistentClient(path=chroma_path)
        self.collection = self.chroma_client.get_or_create_collection(
            name="places",
            embedding_function=embedding_functions.OpenAIEmbeddingFunction(
                api_key=OPENAI_API_KEY,
                model_name="text-embedding-3-small"
            ))
        self.openai_client = OpenAI()

    def save(self, place: Place):
        docs_dict = self.__create_documents_from_place(place)
        ids = []
        docs = []
        metadatas = []
        for key, doc in docs_dict.items():
            ids.append(f"{place.place_id}:{key}")
            docs.append(doc)
            metadatas.append({
                'id': place.place_id,
                'name': place.name,
                'type': key,
            })
        self.collection.add(
            ids=ids,
            documents=docs,
            metadatas=metadatas
        )

    def _summarize_place_with_llm(self, place: Place):
        prompt = f"""\n
You are extracting semantic descriptions for a venue to improve search and recommendations.
\n
Given the following data for a place:
Name: {place.name}
Category: {place.category}
Atmosphere tags: {place.atmosphere}
Place types: {place.place_types}
Description: {place.description}
Reviews: {place.reviews}
\n
Produce a JSON object with the following fields:
- atmosphere: A short (1-2 sentence) natural language description of the venue's vibe, crowd, and setting.
- food_drink: A short (1-2 sentence) natural language description of the notable food and drink offerings.
- special_features: A short (1 sentence) list of distinctive features, amenities, or quirks of the venue.
\n
Focus on what would help a user choose this place for a specific mood or occasion.
\n
Return the JSON object only, no other text.
"""

        response = self.openai_client.chat.completions.create(
            model="gpt-4o-mini",  # cheaper/faster for batch processing
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a helpful assistant for summarizing venue details."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        return json.loads(response.choices[0].message.content)

    def __create_documents_from_place(self, place: Place) -> str:
        locality_data = extract_locality_data_from_geocode_neighbourhoods(place.geocode_neighbourhoods)
        neighborhood = None
        city = ''
        for locality in locality_data.values():
            if locality.type == 'neighborhood' and not neighborhood:
                neighborhood = locality.name
            elif locality.type == 'city' and not city:
                city = locality.name

        description_doc = f"""{place.name} is a {place.category} in {neighborhood if neighborhood else ''}, {city if city else ''}. {f"It's described as a {place.description}" if place.description else ""} It's rated {
            place.rating} out of 5 and has a price level of {place.price_level}."""

        summarrized_data = self._summarize_place_with_llm(place)
        return {
            'description': description_doc,
            'atmosphere': summarrized_data['atmosphere'],
            'food_drink': summarrized_data['food_drink'],
            'special_features': summarrized_data['special_features']
        }

    def search(self, query: str, n_results: int = 20):
        """Search for places"""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )

        res = []
        for metadatas, documents in zip(results['metadatas'], results['documents']):
            for metadata, document in zip(metadatas, documents):
                res.append((metadata['name'], metadata['type'], metadata['id'], document))

        return res


class Indexer:
    def __init__(self, db_path: str, chroma_path: str):
        self.sqlite_store = SQLiteStore(db_path)
        self.chroma_store = ChromaStore(chroma_path)

    def index(self, place: Place):
        self.sqlite_store.save(place)
        self.chroma_store.save(place)

    def index_csv(self, csv_path: str):
        df = pd.read_csv(csv_path)

        for i, row in df.iterrows():
            place = self._create_place_from_csv_row(row)
            self.index(place)

    def _create_place_from_csv_row(self, row: dict) -> Place:
        """Create a Place object from CSV row with proper type conversion"""

        # Parse JSON fields safely
        def safe_json_parse(value: str, default=None):
            if not value or value == 'null' or pd.isna(value):
                return default
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return default

        # Parse coordinates safely
        def safe_float(value: str, default: float = 0.0) -> float:
            if not value or pd.isna(value):
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        # Create component data objects
        csv_data = CSVPlaceData(
            name=str(row.get('name', '')),
            url=str(row.get('source_url', ''))
        )

        basic_data = PlaceBasicData(
            name=str(row.get('name', '')),
            place_id=str(row.get('place_id', '')),
            business_status=row.get('business_status'),
            formatted_address=row.get('formatted_address'),
            coordinates=(
                safe_float(row.get('lat')),
                safe_float(row.get('lng'))
            ) if row.get('lat') and row.get('lng') else None,
            place_types=safe_json_parse(row.get('place_types'), [])
        )

        scraped_data = PlaceScrapedData(
            rating=safe_float(row.get('rating')) if row.get('rating') else None,
            price_level=row.get('price_level'),
            category=row.get('category'),
            description=row.get('description') if not pd.isna(row.get('description')) else None,
            reviews=safe_json_parse(row.get('reviews'), []),
            atmosphere=safe_json_parse(row.get('atmosphere'), [])
        )

        # Create Place object using constructor
        place = Place(csv_data, basic_data, scraped_data)
        place.last_scraped = row.get('last_scraped')
        place.geocode_neighbourhoods = safe_json_parse(safe_json_parse(row.get('geocode_neighbourhoods')))

        return place


indexer = Indexer(db_path='places.db', chroma_path='places_vector_db')
indexer.index_csv('/Users/dilraj/Downloads/Takeout-2/Saved/NY food and drinks_place_checkpoint.csv')
# indexer.index_csv('/Users/dilraj/Downloads/Takeout-2/Saved/San Francisco_place_checkpoint.csv')

queries = ["Casual Korean restaurant that serve great cocktails and isn't too expensive",
           "cheap burger spots",
           "A sexy bar that's great for a first date in williamsburg",
           "I'm looking for a place to eat with friends that won't have a long wait and has a garden or patio to sit in",
           "Somewhere I can go to eat alone, that's got a good vibe and not too expensive."]

for query in queries:
    results = indexer.chroma_store.search(query)

    # Display results
    for result in results:
        print(result[0], result[1], result[2], result[3])
    print("\n\n==============================================\n\n")
