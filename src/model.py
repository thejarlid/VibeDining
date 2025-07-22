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
class Review:
    author_name: str
    rating: int
    text: str


@dataclass
class Place:
    # REQUIRED fields (always present)
    name: str
    place_id: str
    last_scraped: datetime

    # CORE fields (usually present, but can be None)
    address: Optional[str] = None
    business_status: Optional[str] = None
    coordinates: Optional[tuple[float, float]] = None
    rating: Optional[float] = None
    price_level: Optional[str] = None

    opening_hours: Optional[List[str]] = None

    has_curbside_pickup: Optional[bool] = None
    has_delivery: Optional[bool] = None
    has_dine_in: Optional[bool] = None
    has_takeout: Optional[bool] = None

    reviews: List[Review] = field(default_factory=list)
    atmosphere: Optional[List[str]] = None
