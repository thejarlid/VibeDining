# src/models.py
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class CSVPlaceData:
    name: str
    url: str


@dataclass
class PlaceData:
    name: str
    url: str
    place_id: str = field(default="")
    json_data: str = field(default="")
    last_scraped: Optional[str] = None


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

    def __init__(self, PlaceBasicData, PlaceScrapedData):
        self.name = PlaceBasicData.name
        self.place_id = PlaceBasicData.place_id
        self.business_status = PlaceBasicData.business_status
        self.formatted_address = PlaceBasicData.formatted_address
        self.coordinates = PlaceBasicData.coordinates
        self.place_types = PlaceBasicData.place_types
        self.rating = PlaceScrapedData.rating
        self.price_level = PlaceScrapedData.price_level
        self.category = PlaceScrapedData.category
        self.description = PlaceScrapedData.description
        self.reviews = PlaceScrapedData.reviews
        self.atmosphere = PlaceScrapedData.atmosphere
