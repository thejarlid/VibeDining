# VibeDining - Google Maps Data Scraper

## Scraper Architecture

### Overview
The VibeDining scraper is designed as a cost-optimized, async-first pipeline that extracts place data from Google Takeout CSV files. The architecture prioritizes web scraping over expensive API calls, using Google Maps API only for basic fields that are difficult to scrape reliably.

### High-Level Architecture

```
                    ┌─────────────────────────────────────────┐
                    │          ScrapingPipeline               │
                    │                                         │
                    │  • Orchestrates entire flow            │
                    │  • Manages checkpointing                │
                    │  • Controls concurrency (semaphore)    │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────────┐
                    │         Processing Flow                 │
                    └─────────────────────────────────────────┘

┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│CSVProcessor │    │ PlaceScraper│    │CheckpointMgr│    │ PlaceStore  │
│             │    │             │    │             │    │             │
│• parse_csv()│───▶│• scrape()   │───▶│• save()     │───▶│• persist()  │
│             │    │• get_id()   │    │• load()     │    │             │
└─────────────┘    │• scrape_data│    │• is_cached()│    └─────────────┘
                   │• api_call() │    └─────────────┘              
                   │• browser    │                                
                   └─────────────┘                               
```

### Component Responsibilities

#### 1. ScrapingPipeline (Orchestrator)
**Purpose**: Central coordinator that manages the entire scraping process

**Responsibilities**:
- Load CSV files and coordinate processing
- Control concurrency with semaphore limits
- Handle checkpointing strategy
- Error handling and retry logic
- Final data persistence

**Key Methods**:
- `process_csv_file(csv_file: str)` - Main entry point
- `process_places(places: List[CSVPlaceData])` - Async place processing

#### 2. CSVProcessor (Input Handler)
**Purpose**: Parse Google Takeout CSV exports

**Responsibilities**:
- Read and validate CSV files
- Extract place names and URLs
- Convert to internal data structures

**Key Methods**:
- `parse(csv_file: str) -> List[CSVPlaceData]`

#### 3. PlaceScraper (Core Scraper)
**Purpose**: Extract place data using web scraping + minimal API calls

**Responsibilities**:
- Manage browser lifecycle (Playwright)  
- Navigate to Google Maps pages using CID
- Extract place_id from page content
- Scrape atmospheric attributes and place details
- Make minimal API calls for basic fields only
- Run scraping and API calls concurrently
- Handle API configuration and error handling

**Key Methods**:
- `scrape_place(place: CSVPlaceData) -> Place` - Main scraping workflow
- `_get_place_id(page, place) -> str` - Extract place_id from maps page
- `_scrape_detailed_data(page, place_id) -> dict` - Scrape DOM data
- `_get_api_data(place_id) -> dict` - Make basic API call
- `_build_place(place, place_id, api_data, scraped_data) -> Place` - Combine data
- Context manager methods for browser lifecycle

**Internal Async Flow**:
```python
async def scrape_place(self, place: CSVPlaceData) -> Place:
    # 1. Get place_id from CID (web scraping)
    place_id = await self._get_place_id(page, place)
    
    # 2. Run in parallel:
    api_task = asyncio.create_task(self._get_api_data(place_id))        # API call
    scraping_task = asyncio.create_task(self._scrape_detailed_data(page, place_id))  # DOM scraping
    
    # 3. Combine results
    api_data, scraped_data = await asyncio.gather(api_task, scraping_task)
    return self._build_place(place, place_id, api_data, scraped_data)
```

#### 4. CheckpointManager (Persistence Layer)
**Purpose**: Handle incremental processing and crash recovery

**Responsibilities**:
- Load existing checkpoint data on startup
- Save processed places immediately to CSV
- Check if places are already processed
- Handle staleness detection

**Key Methods**:
- `load_checkpoint(csv_file: str)` - Load existing progress
- `save(place: Place)` - Save checkpoint entry
- `is_processed(place: CSVPlaceData) -> bool` - Check if cached
- `get_cached(place: CSVPlaceData) -> Place` - Retrieve cached data

#### 5. PlaceStore (Output Handler)
**Purpose**: Final data persistence

**Responsibilities**:
- Save enriched place data to JSON files
- Future: Integration with vector databases
- Handle output formatting and serialization

**Key Methods**:
- `save(place: Place)` - Persist final place data

### Data Models

```python
@dataclass
class CSVPlaceData:
    name: str
    url: str

@dataclass
class Place:
    # Core fields
    name: str
    place_id: str
    url: str
    
    # API fields (basic/free only)
    address: Optional[str]
    coordinates: Optional[tuple[float, float]]
    
    # Scraped fields
    attributes: List[str]  # Atmospheric attributes
    opening_hours: Optional[List[str]]
    rating: Optional[float]
    
    # Metadata
    last_scraped: str
```

### Processing Flow

1. **CSV Loading**: Parse Google Takeout CSV files
2. **Checkpoint Check**: Skip already processed places
3. **Concurrent Scraping**: Process multiple places simultaneously
   - Navigate to Google Maps via CID
   - Extract place_id from page content
   - Fork into parallel operations:
     - Scrape detailed data from DOM
     - Make minimal API call for basic fields
   - Combine results into Place object
4. **Immediate Checkpointing**: Save progress after each place
5. **Final Storage**: Persist all data to JSON

### Key Design Principles

#### Cost Optimization
- **Scraping First**: Extract maximum data from free web scraping
- **Minimal API Usage**: Only request basic fields that are hard to scrape
- **No Expensive CID Calls**: Avoid costly place details API endpoints

#### Async Efficiency
- **Concurrent Processing**: Multiple places processed simultaneously
- **Internal Parallelization**: API calls don't block DOM scraping
- **Resource Sharing**: Single browser instance with multiple pages

#### Reliability
- **Immediate Checkpointing**: Progress saved after each successful scrape
- **Graceful Error Handling**: Individual place failures don't crash pipeline
- **Resume Capability**: Restart from last checkpoint on crashes

#### Extensibility
- **Modular Components**: Easy to swap implementations
- **Clean Interfaces**: Components communicate through well-defined APIs
- **Future-Ready**: Architecture supports database integration

### Configuration

#### Concurrency Control
```python
semaphore = asyncio.Semaphore(10)  # Max concurrent scrapers
```

#### API Field Selection
```python
fields = "place_id,name,formatted_address,geometry"  # Free fields only
```

#### Staleness Detection
```python
stale_days = 30  # Re-scrape places older than 30 days
```

## Architecture Summary

### Simplified 4-Component Design

The VibeDining scraper uses a streamlined architecture with **4 core components**:

1. **CSVProcessor** - Parses Google Takeout CSV files
2. **PlaceScraper** - Handles all data extraction (scraping + API calls)  
3. **CheckpointManager** - Manages incremental processing and crash recovery
4. **PlaceStore** - Persists final enriched data

### How It Works

**Sequential Flow:**
```
CSV File → Parse Places → Process Concurrently → Checkpoint → Final Storage
```

**Per-Place Processing (Concurrent):**
```
1. Navigate to Google Maps via CID
2. Extract place_id from page content  
3. PARALLEL: Scrape DOM data + Make API call
4. Combine results into Place object
5. Save checkpoint immediately
```

**Key Benefits:**
- **Cost Optimized** - Minimal API usage, scraping-first approach
- **Concurrent Processing** - Multiple places + parallel scraping/API per place
- **Crash Resilient** - Immediate checkpointing with resume capability
- **Simple Architecture** - Only 4 components, clear responsibilities

**Concurrency Model:**
- **Pipeline Level** - N places processed simultaneously (semaphore controlled)
- **Place Level** - Each place runs DOM scraping + API call in parallel
- **Resource Efficient** - Single browser with multiple pages, shared HTTP client

This architecture balances cost efficiency, performance, and reliability while maintaining clean separation of concerns across all components.