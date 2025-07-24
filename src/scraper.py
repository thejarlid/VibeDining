from datetime import datetime
import time
import os
import argparse
import csv
import aiofiles
import re
import json
import pandas as pd
import asyncio
import httpx
from aiocsv import AsyncDictWriter
from tqdm.asyncio import tqdm as atqdm
from tqdm import tqdm
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from model import CSVPlaceData, Place, PlaceScrapedData, PlaceBasicData

load_dotenv()
MAPS_API_KEY = os.getenv('MAPS_API_KEY')


class CSVProcessor:
    def parse(self, csv_file: str) -> list[CSVPlaceData]:
        df = pd.read_csv(csv_file)
        places = []
        for _, row in df.iterrows():
            if not pd.isna(row['Title']):
                places.append(CSVPlaceData(row['Title'], row['URL']))
        return places


class PlaceScraper:
    def __init__(self):
        self.http_client = None
        self.browser = None
        self.playwright = None

    # Context manager for resource lifecycle
    async def __aenter__(self):
        self.http_client = httpx.AsyncClient()
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.http_client.aclose()
        await self.playwright.stop()
        await self.browser.close()

    # Public API
    async def scrape_place(self, place: CSVPlaceData) -> Place:
        page = await self.browser.new_page()

        try:
            # 1. Get place_id from CID through scraping the page
            place_id = await self._get_place_id(page, place)

            # 2. Scrape the detailed data and the api data in parallel
            api_data = asyncio.create_task(self._get_api_data(place_id))
            scraped_data = asyncio.create_task(self._scrape_detailed_data(page, place.name, place_id))
            api_data, scraped_data = await asyncio.gather(api_data, scraped_data)

            if not api_data or not scraped_data:
                tqdm.write(f"️{place.name} might be closed or not a restaurant/bar")
                return None

            # 3. Combine the data into a Place object
            return self._build_place(place, api_data, scraped_data)
        except Exception as e:
            tqdm.write(f"Error scraping {place.name}: {e}")
            return None
        finally:
            await page.close()

    # Private methods
    async def _get_place_id(self, page, place: CSVPlaceData) -> str:
        url_hex = place.url.split('0x')[-1]
        cid = int(url_hex, 16)
        await page.goto(f"https://maps.google.com/?cid={cid}")
        content = await page.content()

        # Place ID is a 21 character string that starts with ChI
        place_id_match = re.search(r'ChI[0-9A-Za-z_-]{21,}', content)

        if place_id_match:
            return place_id_match.group()
        else:
            raise ValueError("No place_id found")

    async def _get_api_data(self, place_id: str) -> dict:
        basic_fields = ["business_status", "formatted_address", "geometry", "name", "place_id", "type"]
        api_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields={",".join(basic_fields)}&key={MAPS_API_KEY}"
        response = await self.http_client.get(api_url)
        try:
            response.raise_for_status()
            result = response.json()['result']
            basic_fields_data = PlaceBasicData(
                name=result.get('name'),
                place_id=result.get('place_id'),
                business_status=result.get('business_status'),
                formatted_address=result.get('formatted_address'),
                coordinates=(result.get('geometry', {}).get('location', {}).get('lat'),
                             result.get('geometry', {}).get('location', {}).get('lng')),
                place_types=result.get('types')
            )
            return basic_fields_data
        except Exception as e:
            print(f"Error getting api data for {place_id}: {e}")
            return None

    async def _scrape_detailed_data(self, page, place_name: str, place_id: str) -> dict:

        # on the overview tab we need to scrape rating, price level, and opening hours
        # on the reviews tab we should try grab some of the most relevant reviews
        # on the about page we should grab the restaurant attributes

        scraped_data = PlaceScrapedData()
        side_panel_div = page.locator('div.w6VYqd')

        # 1. Overview tab
        top_level_info_div = side_panel_div.locator('div.skqShb')
        if await top_level_info_div.count() == 0:
            return None

        # 1.1. Rating
        rating_div = top_level_info_div.locator('div.F7nice')
        if await rating_div.count() > 0:
            rating_text = await rating_div.locator('span span').nth(0).inner_text()
            scraped_data.rating = float(rating_text.strip())

        # 1.2. Price level
        price_level_div = top_level_info_div.locator('span.mgr77e span').nth(2)
        if await price_level_div.count() > 0:
            price_level_text = await price_level_div.locator('span span').inner_text()
            scraped_data.price_level = price_level_text.strip()

        # 1.3 Category
        category_button = top_level_info_div.locator('button[jsaction*="category"]')
        if await category_button.count() > 0:
            category_text = await category_button.inner_text()
            scraped_data.category = category_text.strip()
        else:
            return None

        # 2. Description
        description_text_div = side_panel_div.locator('div.PYvSYb')
        if await description_text_div.count() > 0:
            description_text = await description_text_div.inner_text()
            scraped_data.description = description_text.strip()

        # 3. Reviews
        reviews = await self._extract_reviews(page)

        scraped_data.reviews = reviews

        # 3. About
        about_button = side_panel_div.locator('button.hh2c6').filter(has=page.locator('div.Gpq6kf', has_text='About'))
        if await about_button.count() > 0:
            await about_button.click()
            await page.wait_for_selector("li.hpLkke span:nth-of-type(2)", state="visible", timeout=1000)
            second_spans = page.locator('li.hpLkke span:nth-of-type(2)')
            if await second_spans.count() > 0:
                attributes = await second_spans.all_text_contents()
                scraped_data.atmosphere = attributes

        return scraped_data

    async def _extract_reviews(self, page):
        """Expand all complex reviews and extract full text + ratings"""
        try:
            # First, click all "More" buttons to expand reviews
            more_buttons = page.locator('button.w8nwRe.kyuRq[aria-label="See more"]')
            button_count = await more_buttons.count()

            if button_count > 0:

                # Click all "More" buttons
                for i in range(button_count):
                    try:
                        button = more_buttons.nth(i)
                        # Check if button is visible and clickable
                        if await button.is_visible():
                            await button.click()
                            # Small delay to allow expansion
                            await page.wait_for_timeout(100)
                    except Exception as e:
                        print(f"Failed to expand review {i}: {e}")

                # Wait a bit for all expansions to complete
                await page.wait_for_timeout(500)

            # Now extract the full review data
            review_data = await page.evaluate('''
                () => {
                    const reviews = [];
                    const containers = document.querySelectorAll('div.jftiEf.fontBodyMedium');
                    
                    containers.forEach(container => {
                        try {
                            // Extract full review text (now expanded)
                            const textElement = container.querySelector('.MyEned');
                            let text = null;
                            
                            if (textElement) {
                                // Get all text, excluding the "More" button text
                                const textNodes = [];
                                const walker = document.createTreeWalker(
                                    textElement,
                                    NodeFilter.SHOW_TEXT,
                                    {
                                        acceptNode: function(node) {
                                            // Skip text inside the "More" button
                                            const parent = node.parentElement;
                                            if (parent && parent.matches('button.w8nwRe.kyuRq')) {
                                                return NodeFilter.FILTER_REJECT;
                                            }
                                            return NodeFilter.FILTER_ACCEPT;
                                        }
                                    }
                                );
                                
                                let node;
                                while (node = walker.nextNode()) {
                                    textNodes.push(node.textContent);
                                }
                                text = textNodes.join('').trim();
                            }
                            if (text && text.length > 0) {
                                reviews.push(text);
                            }
                        } catch (e) {
                            console.log('Error processing review:', e);
                        }
                    });
                    
                    return reviews;
                }
            ''')

            cleaned_reviews = []
            for review in review_data:
                cleaned_review = review.encode('ascii', 'ignore').decode('ascii')
                cleaned_reviews.append(cleaned_review)

            return cleaned_reviews if cleaned_reviews else []

        except Exception as e:
            print(f"Error extracting expanded reviews: {e}")
            return []

    def _build_place(self, csv_data: CSVPlaceData, api_data: PlaceBasicData, scraped_data: PlaceScrapedData) -> Place:
        place = Place(csv_data, api_data, scraped_data)
        place.last_scraped = datetime.now().isoformat()
        return place


class CheckpointManager:
    def __init__(self, csv_file: str, stale_days: int = 30):
        self.csv_file = csv_file
        self.stale_days = stale_days
        self.checkpoint_filename = f"{csv_file.split('.')[0]}_place_checkpoint.csv"
        self.checkpoint = {}  # In-memory cache: {url: Place}
        self.checkpoint_queue = asyncio.Queue()
        self.writer_task = None

    async def __aenter__(self) -> 'CheckpointManager':
        self._load_checkpoint()
        self.writer_task = asyncio.create_task(self._checkpoint_writer())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Signal writer to finish and wait
        await self.checkpoint_queue.put(None)
        if self.writer_task:
            await self.writer_task

    # Public API
    def is_processed(self, place: CSVPlaceData) -> bool:
        """Check if place exists in checkpoint and isn't stale"""
        if place.url not in self.checkpoint:
            return False

        cached_place = self.checkpoint[place.url]
        return not self._is_stale(cached_place)

    def get_cached(self, place: CSVPlaceData) -> Place:
        """Return cached place data"""
        return self.checkpoint.get(place.url)

    async def save(self, place: Place, source_url: str):
        """Save place to checkpoint and update in-memory cache"""
        # Update in-memory cache immediately
        self.checkpoint[source_url] = place

        # Queue for async writing
        await self.checkpoint_queue.put((place, source_url))

    # Private methods
    def _load_checkpoint(self):
        """Load existing checkpoint data into memory"""
        try:
            if not os.path.exists(self.checkpoint_filename):
                print(f"No existing checkpoint found at {self.checkpoint_filename}")
                return

            df = pd.read_csv(self.checkpoint_filename)
            for _, row in df.iterrows():
                # Reconstruct PlaceBasicData and PlaceScrapedData objects
                csv_data = CSVPlaceData(
                    name=row.get('name'),
                    url=row.get('url')
                )

                basic_data = PlaceBasicData(
                    name=row.get('name'),
                    place_id=row.get('place_id'),
                    business_status=row.get('business_status'),
                    formatted_address=row.get('formatted_address'),
                    coordinates=(row.get('lat'), row.get('lng')) if pd.notna(row.get('lat')) else None,
                    place_types=json.loads(row.get('place_types', '[]')) if pd.notna(row.get('place_types')) else None
                )

                scraped_data = PlaceScrapedData(
                    rating=row.get('rating') if pd.notna(row.get('rating')) else None,
                    price_level=row.get('price_level') if pd.notna(row.get('price_level')) else None,
                    category=row.get('category') if pd.notna(row.get('category')) else None,
                    description=row.get('description') if pd.notna(row.get('description')) else None,
                    reviews=json.loads(row.get('reviews', '[]')) if pd.notna(row.get('reviews')) else None,
                    atmosphere=json.loads(row.get('atmosphere', '[]')) if pd.notna(row.get('atmosphere')) else None
                )

                # Create Place object
                place = Place(csv_data, basic_data, scraped_data)
                place.last_scraped = row.get('last_scraped')

                self.checkpoint[row['source_url']] = place

            print(f"Loaded {len(self.checkpoint)} places from checkpoint")
        except Exception as e:
            print(f"Error loading checkpoint: {e}")
            self.checkpoint = {}

    def _is_stale(self, place: Place) -> bool:
        """Check if place data is stale based on last_scraped date"""
        if not hasattr(place, 'last_scraped') or not place.last_scraped:
            return True

        try:
            last_scraped = datetime.fromisoformat(place.last_scraped)
            days_old = (datetime.now() - last_scraped).days
            return days_old > self.stale_days
        except ValueError:
            return True

    async def _checkpoint_writer(self):
        """Single writer coroutine - no race conditions"""
        checkpoint_exists = os.path.exists(self.checkpoint_filename)

        async with aiofiles.open(self.checkpoint_filename, 'a') as f:
            fieldnames = [
                'source_url', 'name', 'place_id', 'business_status', 'formatted_address',
                'lat', 'lng', 'place_types', 'rating', 'price_level', 'category',
                'description', 'reviews', 'atmosphere', 'last_scraped'
            ]
            writer = AsyncDictWriter(f, fieldnames=fieldnames, extrasaction='ignore',
                                     quoting=csv.QUOTE_ALL, restval="")

            # Write header if new file
            if not checkpoint_exists:
                await writer.writeheader()

            while True:
                item = await self.checkpoint_queue.get()
                if item is None:  # Shutdown signal
                    break

                place, source_url = item

                try:
                    # Flatten Place object for CSV
                    row_data = {
                        'source_url': source_url,
                        'name': place.name,
                        'url': place.url,
                        'place_id': place.place_id,
                        'business_status': place.business_status,
                        'formatted_address': place.formatted_address,
                        'lat': place.coordinates[0] if place.coordinates else None,
                        'lng': place.coordinates[1] if place.coordinates else None,
                        'place_types': json.dumps(place.place_types) if place.place_types else None,
                        'rating': place.rating,
                        'price_level': place.price_level,
                        'category': place.category,
                        'description': place.description,
                        'reviews': json.dumps(place.reviews) if place.reviews else None,
                        'atmosphere': json.dumps(place.atmosphere) if place.atmosphere else None,
                        'last_scraped': place.last_scraped
                    }

                    await writer.writerow(row_data)
                    await f.flush()

                except Exception as e:
                    print(f"Error saving checkpoint for {place.name}: {e}")
                finally:
                    self.checkpoint_queue.task_done()


class PlaceStore:
    pass


class ScrapingPipeline:
    def __init__(self):
        self.csv_processor = CSVProcessor()
        self.place_store = PlaceStore()

    async def process_csv_file(self, csv_file: str):
        places = self.csv_processor.parse(csv_file)
        await self.process_places(places, csv_file)

    async def process_places(self, places: list[CSVPlaceData], csv_file: str):
        semaphore = asyncio.Semaphore(5)

        async with PlaceScraper() as place_scraper, CheckpointManager(csv_file=csv_file) as checkpoint_manager:
            async def process_single_place(place: CSVPlaceData):
                async with semaphore:
                    # Check checkpoint first
                    if checkpoint_manager.is_processed(place):
                        return checkpoint_manager.get_cached(place)

                    # Scrape new data
                    result = await place_scraper.scrape_place(place)

                    # Save checkpoint immediately
                    if result:
                        await checkpoint_manager.save(result, place.url)
                    return result

            tasks = [process_single_place(place) for place in places]

            results = await atqdm.gather(*tasks, desc="Processing places")

            print(f"Successfully processed {len([r for r in results if r is not None])} places")
            # Final storage
            # for result in results:
            #     await self.place_store.save(result)


async def main():
    start = time.time()
    parser = argparse.ArgumentParser()
    parser.add_argument('path', type=str, help='Path to directory containing CSV files or path to a specific CSV file')
    args = parser.parse_args()

    path = args.path

    pipeline = ScrapingPipeline()

    if os.path.isdir(path):
        for file in os.listdir(path):
            if file.endswith('.csv'):
                await pipeline.process_csv_file(os.path.join(path, file))
    elif os.path.isfile(path) and path.endswith('.csv'):
        await pipeline.process_csv_file(path)
    else:
        raise ValueError(f"'{path}' is neither a valid directory nor a CSV file")

    end = time.time()
    print(f"Time taken: {end - start} seconds")


if __name__ == '__main__':
    asyncio.run(main())
