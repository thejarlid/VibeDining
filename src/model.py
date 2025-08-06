# src/models.py
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class CSVPlaceData:
    name: str
    url: str


@dataclass
class PlaceBasicData:
    name: str
    place_id: str
    business_status: Optional[str] = None
    formatted_address: Optional[str] = None
    coordinates: Optional[tuple[float, float]] = None
    place_types: Optional[List[str]] = None


@dataclass
class PlaceScrapedData:
    rating: Optional[float] = None
    price_level: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    reviews: Optional[List[str]] = None
    atmosphere: Optional[List[str]] = None


@dataclass
class Place:
    name: str
    place_id: str
    url: str
    business_status: Optional[str] = None
    formatted_address: Optional[str] = None
    coordinates: Optional[tuple[float, float]] = None
    place_types: Optional[List[str]] = None
    rating: Optional[float] = None
    price_level: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    reviews: Optional[List[str]] = None
    atmosphere: Optional[List[str]] = None
    geocode_neighbourhoods: Optional[str] = None
    last_scraped: Optional[str] = None

    def __init__(self, csv_data: CSVPlaceData, basic_data: PlaceBasicData, scraped_data: PlaceScrapedData):
        self.name = csv_data.name
        self.place_id = basic_data.place_id
        self.url = csv_data.url
        self.business_status = basic_data.business_status
        self.formatted_address = basic_data.formatted_address
        self.coordinates = basic_data.coordinates
        self.place_types = basic_data.place_types
        self.rating = scraped_data.rating
        self.price_level = scraped_data.price_level
        self.category = scraped_data.category
        self.description = scraped_data.description
        self.reviews = scraped_data.reviews
        self.atmosphere = scraped_data.atmosphere
