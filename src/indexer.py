import sqlite3
from model import Place
import pandas as pd
import json
from model import Place, CSVPlaceData, PlaceBasicData, PlaceScrapedData
from collections import namedtuple


Locality = namedtuple('Locality', ['id', 'name', 'full_name', 'latitude', 'longitude', 'type'])


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
        city = _extract_locality_data(geocode_neighbourhoods[-1], 'city')
        localities[city.id] = city

        for geocoded_neighbourhood in geocode_neighbourhoods[:-1]:
            neighborhood = _extract_locality_data(geocoded_neighbourhood, 'neighborhood')
            localities[neighborhood.id] = neighborhood
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
    pass


class Indexer:
    def __init__(self, db_path: str, chroma_path: str):
        self.sqlite_store = SQLiteStore(db_path)
        # self.chroma_store = ChromaStore(chroma_path)

    def index(self, place: Place):
        self.sqlite_store.save(place)
        # self.chroma_store.save(place)

    def index_csv(self, csv_path: str):
        df = pd.read_csv(csv_path)

        for _, row in df.iterrows():
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
            description=row.get('description'),
            reviews=safe_json_parse(row.get('reviews'), []),
            atmosphere=safe_json_parse(row.get('atmosphere'), [])
        )

        # Create Place object using constructor
        place = Place(csv_data, basic_data, scraped_data)
        place.last_scraped = row.get('last_scraped')
        place.geocode_neighbourhoods = safe_json_parse(safe_json_parse(row.get('geocode_neighbourhoods')))

        return place


indexer = Indexer(db_path='places.db', chroma_path='chroma.db')
# indexer.index_csv('/Users/dilraj/Downloads/Takeout-2/Saved/NY food and drinks_place_checkpoint.csv')
# indexer.index_csv('/Users/dilraj/Downloads/Takeout-2/Saved/San Francisco_place_checkpoint.csv')
