from collections import defaultdict
import chromadb
import csv
import json
import pandas as pd
from typing import Dict, List
from model import Place, CSVPlaceData, PlaceBasicData, PlaceScrapedData


class ChromaIndexer:
    def __init__(self, collection_name: str = "places"):
        self.chroma_client = chromadb.Client()
        self.collection = self.chroma_client.create_collection(collection_name)
        self.place_store = {}  # place_id -> Place object

    @staticmethod
    def _create_place_from_csv_row(row: dict) -> Place:
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

        return place

    def _load_places_from_csv(self, csv_file_path: str) -> List[Place]:
        """Load places from CSV checkpoint file"""
        places = []

        with open(csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    place = self._create_place_from_csv_row(row)
                    places.append(place)
                except Exception as e:
                    print(f"Error processing row: {e}")
                    continue

        return places

    def _group_atmosphere_tags(self, atmosphere_tags: List[str]) -> Dict[str, List[str]]:
        feature_groups = {
            "dining_options": [
                "Dine-in", "Delivery", "Takeout", "Drive-through",
                "Solo dining", "Family-friendly", "Good for kids"
            ],
            "accessibility": [
                "Wheelchair accessible", "Gender-neutral restroom",
                "Restroom", "Transgender safespace"
            ],
            "ambiance": [
                "Casual", "Trendy", "Cozy", "Romantic", "Intimate",
                "Loud", "Quiet", "Usually a wait"
            ],
            "service_style": [
                "Fast service", "Table service", "Self-service",
                "Accepts reservations", "Dinner reservations recommended"
            ],
            "food_drink": [
                "Alcohol", "Beer", "Wine", "Coffee", "Comfort food",
                "Healthy options", "Small plates", "Lunch", "Dinner", "Dessert"
            ],
            "logistics": [
                "Paid street parking", "Parking lot", "Credit cards",
                "Debit cards", "NFC mobile payments"
            ],
            "crowd": [
                "LGBTQ+ friendly", "Locals", "Identifies as Asian-owned"
            ]
        }

        grouped_tags = {group: [] for group in feature_groups.keys()}
        ungrouped = []

        for tag in atmosphere_tags:
            placed = False
            for group_name, group_tags in feature_groups.items():
                if any(group_tag.lower() in tag.lower() for group_tag in group_tags):
                    grouped_tags[group_name].append(tag)
                    placed = True
                    break

            if not placed:
                ungrouped.append(tag)

        # Add ungrouped tags as misc
        if ungrouped:
            grouped_tags["other_features"] = ungrouped

        # Remove empty groups
        return {k: v for k, v in grouped_tags.items() if v}

    def _create_document_text(self, place: Place) -> List[str]:
        """Create searchable document text from Place object"""
        # Only include non-empty fields
        # we split the place into multiple documents to avoid dilution of the search results

        docs = []

        core_text = f"name: {place.name}{f' Type: {place.category}' if place.category else ''}{f' Address: {place.formatted_address}' if place.formatted_address else ''}{f' Price: {place.price_level}' if place.price_level else ''}{
            f' Rating: {place.rating}/5' if place.rating else ''}{f' Categories: {', '.join(place.place_types or [])}' if place.place_types else ''}{f' Description: {place.description}' if place.description else ''}"

        docs.append(core_text)

        if place.atmosphere:
            grouped_atmosphere = self._group_atmosphere_tags(place.atmosphere)
            for group, tags in grouped_atmosphere.items():
                group_text = f"name: {place.name} {group}: {', '.join(tags)}"
                docs.append(group_text)

        if place.reviews:
            reviews_text = ", ".join(place.reviews[:4])
            docs.append(f"name: {place.name} Reviews: {reviews_text}")

        return docs

    def _create_metadata(self, place: Place) -> dict:
        """Create metadata dict for ChromaDB"""
        return {
            "name": place.name,
            "place_id": place.place_id,
            "url": place.url,
            "lat": place.coordinates[0] if place.coordinates else None,
            "lng": place.coordinates[1] if place.coordinates else None,
            "formatted_address": place.formatted_address,
            "place_types": json.dumps(place.place_types) if place.place_types else None,
            "rating": place.rating,
            "price_level": place.price_level,
            "category": place.category,
            "business_status": place.business_status,
        }

    def index_places_from_csv(self, csv_file_path: str):
        """Load places from CSV and index them in ChromaDB"""
        places = self._load_places_from_csv(csv_file_path)

        documents = []
        metadatas = []
        ids = []

        for place in places:
            if not place.place_id:  # Skip places without place_id
                continue

            self.place_store[place.place_id] = place

            docs = self._create_document_text(place)
            metadata = self._create_metadata(place)

            documents.extend(docs)
            metadatas.extend([metadata] * len(docs))
            ids.extend([place.place_id + str(hash(doc)) for doc in docs])

        # Add to ChromaDB
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )

        print(f"Indexed {len(documents)} places")

    def add_place(self, place: Place) -> bool:
        """Add a single Place object to ChromaDB"""
        try:
            if not place.place_id:
                print(f"Warning: Skipping place '{place.name}' - no place_id")
                return False

            self.place_store[place.place_id] = place
            docs = self._create_document_text(place)
            metadata = self._create_metadata(place)

            # Add single place to ChromaDB
            self.collection.add(
                documents=docs,
                metadatas=[metadata] * len(docs),
                ids=[place.place_id + str(hash(doc)) for doc in docs]
            )

            return True

        except Exception as e:
            print(f"Error adding place '{place.name}' to ChromaDB: {e}")
            return False

    def upsert_place(self, place: Place) -> bool:
        """Add or update a single Place object in ChromaDB"""
        try:
            if not place.place_id:
                print(f"Warning: Skipping place '{place.name}' - no place_id")
                return False

            self.place_store[place.place_id] = place
            docs = self._create_document_text(place)
            metadata = self._create_metadata(place)

            # Upsert single place to ChromaDB (updates if exists, adds if not)
            self.collection.upsert(
                documents=docs,
                metadatas=[metadata] * len(docs),
                ids=[place.place_id + str(hash(doc)) for doc in docs]
            )

            return True

        except Exception as e:
            print(f"Error upserting place '{place.name}' to ChromaDB: {e}")
            return False

    def add_places_batch(self, places: List[Place]) -> int:
        """Add multiple Place objects to ChromaDB efficiently"""
        documents = []
        metadatas = []
        ids = []

        for place in places:
            if not place.place_id:
                continue

            self.place_store[place.place_id] = place
            documents.extend(self._create_document_text(place))
            metadatas.extend([self._create_metadata(place)] * len(documents))
            ids.extend([place.place_id + str(hash(doc)) for doc in documents])

        try:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            print(f"Added {len(documents)} places to ChromaDB")
            return len(documents)

        except Exception as e:
            print(f"Error adding batch of places: {e}")
            return 0

    def search(self, query: str, n_results: int = 10):
        """Search for places"""
        results = self.collection.query(
            query_texts=[query],
            n_results=30
        )

        id_to_documents = defaultdict(list)
        for i, metadatas in enumerate(results['metadatas']):
            for metadata in metadatas:
                id_to_documents[metadata['place_id']].append(results['documents'][i])

        places = [(self.place_store[id], documents) for id, documents in id_to_documents.items()]

        return places


# Usage
if __name__ == "__main__":
    indexer = ChromaIndexer()

    # Index places from your checkpoint CSV
    csv_path = '/Users/dilraj/Downloads/Takeout/Saved/NY food and drinks_place_checkpoint.csv'
    indexer.index_places_from_csv(csv_path)

    # results = indexer.collection.query(
    #     query_texts=["Casual Korean restaurant that serve great cocktails and isn't too expensive",
    #                  "cheap burger spots that",
    #                  "A sexy bar that's great for a first date",
    #                  "I'm looking for a place to eat with friends that won't have a long wait and has a garden or patio to sit in",
    #                  "Somewhere I can go to eat alone, that's got a good vibe and not too expensive."]
    # )

    queries = ["Casual Korean restaurant that serve great cocktails and isn't too expensive",
               "cheap burger spots that",
               "A sexy bar that's great for a first date",
               "I'm looking for a place to eat with friends that won't have a long wait and has a garden or patio to sit in",
               "Somewhere I can go to eat alone, that's got a good vibe and not too expensive."]

    for query in queries:
        results = indexer.search(query)

        # Display results
        for place, documents in results:
            print(place.name)
            print(len(documents))
        print("\n\n==============================================\n\n")
