from dataclasses import asdict
from datetime import datetime
import time
import os
import argparse
import csv
import aiofiles
import aiocsv
import re
import json
import pandas as pd
import requests
import asyncio
import httpx
from aiocsv import AsyncDictWriter
from tqdm import tqdm
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from model import CSVPlaceData, PlaceData, Place, PlaceScrapedData, PlaceBasicData

load_dotenv()
MAPS_API_KEY = os.getenv('MAPS_API_KEY')


"""
This script sequentially scraps the input csv file exported from Google Takeout.
It then makes a request for the place data
Following which it scrapes each place for the additional attributes we are interested in
Finally it writes the data to a json file

TODO: We should improve this process to be more efficient and parallelize the scraping of places
One approach is to scrape places in parallel and then write the data to a json file and have those
run asyncronously. That way we do not wait for all places to be scraped before writing to a file.
This is a later optimization and also would help us ingest data for a single place which will be useful
in the future as we don't want to generally reingest the entire dataset but rather have new additions/udpated
items.
"""


def clean_unicode_text(text):
    """Convert Unicode characters to ASCII equivalents for better readability"""
    if not text:
        return text

    # Unicode character mappings
    unicode_to_ascii = {
        '\u2009': ' ',      # Thin space -> regular space
        '\u2013': '-',      # En dash -> hyphen
        '\u2014': '--',     # Em dash -> double hyphen
        '\u202f': ' ',      # Narrow no-break space -> regular space
        '\u00a0': ' ',      # Non-breaking space -> regular space
        '\u200b': '',       # Zero-width space -> remove
        '\u200c': '',       # Zero-width non-joiner -> remove
        '\u200d': '',       # Zero-width joiner -> remove
    }

    cleaned_text = text
    for unicode_char, ascii_char in unicode_to_ascii.items():
        cleaned_text = cleaned_text.replace(unicode_char, ascii_char)

    return cleaned_text


def write_scraped_place_data(scraped_place_data: list[PlaceData], csv_file: str):
    """
    This function takes the scraped places, parses the raw json data into a Place object
    that is then serialized and written to a json file that can be used for vector db later.
    """
    enhanced_places = []
    for place in scraped_place_data:
        enhanced_place = Place(place.name, place.place_id, datetime.now().isoformat())

        json_data = json.loads(place.json_data)['result']
        enhanced_place.address = json_data.get('formatted_address')

        geometry = json_data.get('geometry')
        if geometry:
            enhanced_place.coordinates = (geometry.get('location', {}).get('lat'), geometry.get('location', {}).get('lng'))

        enhanced_place.business_status = json_data.get('business_status')
        enhanced_place.rating = json_data.get('rating')
        enhanced_place.price_level = json_data.get('price_level')

        # Clean up opening hours text, google maps uses unicode characters for special spacing the dash
        opening_hours_raw = json_data.get('current_opening_hours', {}).get('weekday_text')
        if opening_hours_raw:
            enhanced_place.opening_hours = [clean_unicode_text(day) for day in opening_hours_raw]
        else:
            enhanced_place.opening_hours = None

        enhanced_place.has_curbside_pickup = json_data.get('curbside_pickup')
        enhanced_place.has_delivery = json_data.get('delivery')
        enhanced_place.has_dine_in = json_data.get('dine_in')
        enhanced_place.has_takeout = json_data.get('takeout')
        enhanced_place.reviews = [Review(
            author_name=r.get('author_name'),
            rating=r.get('rating'),
            text=r.get('text'),
        ) for r in json_data.get('reviews', [])]
        enhanced_place.atmosphere = place.attributes
        enhanced_places.append(enhanced_place)

    with open(f"{csv_file.split('.')[0]}_parsed_data.json", 'w', encoding='utf-8') as f:
        # json.dump(enhanced_places, f, indent=4)
        json.dump(enhanced_places, f, indent=4, default=lambda obj: asdict(obj), ensure_ascii=False)
    print(f"Saved {len(enhanced_places)} places to enhanced_place_data.json")


async def scrape_places_for_attributes(places: list[PlaceData]):
    """
    Once we have the base data and information we need to scrape the about section
    on the site to get details about the place wrt to the atmosphere, vibe, offerings, etc.
    we could use the places api to get this information but we would be capped at 1000 requests
    just by testing on my small dataset (~400 places) we'll hit that with 3 runs
    """
    print(f"Scraping {len(places)} places")
    url_base = "https://www.google.com/maps/place/?q=place_id:"

    scraped_place_data = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        for place in tqdm(places, desc="Scraping places"):
            place_data = PlaceData(place)
            tqdm.write(f"Scraping {place_data.name}")
            url = url_base + place_data.place_id
            page = await browser.new_page()
            try:
                await page.goto(url)
            except Exception as e:
                tqdm.write(f"Error navigating to {url}: {e}")
                await page.close()
                continue

            about_button = page.locator('button.hh2c6').filter(has=page.locator('div.Gpq6kf', has_text='About'))
            if await about_button.count() == 0:
                tqdm.write(f"No about button found for {place_data.name}")
                await page.close()
                continue
            await about_button.click()
            await page.wait_for_selector("li.hpLkke span:nth-of-type(2)", state="visible", timeout=1000)
            second_spans = page.locator('li.hpLkke span:nth-of-type(2)')
            if await second_spans.count() == 0:
                tqdm.write(f"No attributes found for {place_data.name}")
                await page.close()
                continue
            attributes = await second_spans.all_text_contents()
            place_data.attributes = attributes
            scraped_place_data.append(place_data)
            await page.close()
    return scraped_place_data


def process_csv_file(csv_file: str):
    """
    Given a csv file from Google Takeout, makes a request for data using the cid and writes
    a csv file with the place_id, name, and json_data for each place

    if the csv file provided already has a [csv_file]_place_data.csv file, it will skip the processing
    and return the data parsed from the already existing processed file
    """

    print(f"Processing CSV file: {csv_file}")
    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"File {csv_file} does not exist")

    df = pd.read_csv(csv_file)
    place_to_url = {}
    for _, row in df.iterrows():
        if not pd.isna(row['Title']):
            place_to_url[row['Title']] = row['URL']

    if os.path.exists(f"{csv_file.split('.')[0]}_place_data.csv"):
        place_data = pd.read_csv(f"{csv_file.split('.')[0]}_place_data.csv")
        if place_data.shape[0] == len(place_to_url):
            print(f"Skipping {csv_file} because {f"{csv_file.split('.')[0]}_place_data.csv"} already exists")
            return [RawPlaceData(**row) for row in place_data.to_dict(orient='records')]

    place_to_cid = {}
    for place in place_to_url:
        url = place_to_url[place]
        url_hex = url.split('0x')[-1]
        cid = int(url_hex, 16)
        place_to_cid[place] = cid

    place_data = []
    cid_url_base = "https://maps.googleapis.com/maps/api/place/details/json?cid="
    key_arg = f"&key={MAPS_API_KEY}"
    for place in place_to_cid:
        cid = place_to_cid[place]
        url = cid_url_base + str(cid) + key_arg
        response = requests.get(url)
        data = response.json()
        place_data.append({
            'name': place,
            'place_id': data['result']['place_id'],
            'json_data': response.text,
        })
        print(f"Processed {place}")

    with open(f"{csv_file.split('.')[0]}_place_data.csv", 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'place_id', 'json_data'], extrasaction='ignore')
        writer.writeheader()
        writer.writerows(place_data)
    print(f"Saved {len(place_data)} places to place_data.csv")

    return [RawPlaceData(**row) for row in place_data]


async def process_csv_directory(csv_directory: str):
    print(f"Processing CSV directory: {csv_directory}")
    expanded_path = os.path.expanduser(csv_directory)

    for file in os.listdir(expanded_path):
        if file.endswith('.csv'):
            filename = os.path.join(expanded_path, file)
            process_csv_file(filename)
            place_data = process_csv_file(filename)
            scrape_places = await scrape_places_for_attributes(place_data)
            write_scraped_place_data(scrape_places, filename)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('path', type=str, help='Path to directory containing CSV files or path to a specific CSV file')
    args = parser.parse_args()

    path = args.path

    if os.path.isdir(path):
        process_csv_directory(path)
    elif os.path.isfile(path) and path.endswith('.csv'):
        place_data = process_csv_file(path)
        scrape_places = await scrape_places_for_attributes(place_data)
        write_scraped_place_data(scrape_places, path)
    else:
        raise ValueError(f"'{path}' is neither a valid directory nor a CSV file")


class CSVProcessor:
    def parse(self, csv_file: str) -> list[CSVPlaceData]:
        df = pd.read_csv(csv_file)
        places = []
        for _, row in df.iterrows():
            if not pd.isna(row['Title']):
                places.append(CSVPlaceData(row['Title'], row['URL']))
        return places


class PlaceResolver:
    def __init__(self, google_maps_api_key: str, csv_file: str, stale_days: int = 30):
        self.google_maps_api_key = google_maps_api_key
        self.csv_file = csv_file
        self.stale_days = stale_days
        self.client = None

        # checkpointing variables
        self.checkpoint = {}
        self.checkpoint_filename = f"{self.csv_file.split('.')[0]}_data_checkpoint.csv"
        self.checkpoint_queue = asyncio.Queue()
        self.writer_task = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient()
        self._load_checkpoint()
        self.writer_task = asyncio.create_task(self._checkpoint_writer())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.checkpoint_queue.put(None)
        if self.writer_task:
            await self.writer_task

        if self.client:
            await self.client.aclose()

    async def resolve_place(self, place: CSVPlaceData, force_refresh: bool = False) -> PlaceData:
        if place.url in self.checkpoint and not force_refresh and not self._is_stale(self.checkpoint[place.url]):
            return self.checkpoint[place.url]

        url_hex = place.url.split('0x')[-1]
        cid = int(url_hex, 16)
        api_url = f"https://maps.googleapis.com/maps/api/place/details/json?cid={cid}&key={self.google_maps_api_key}"
        response = await self.client.get(api_url)
        try:
            response.raise_for_status()
            data = response.json()
            place_data = PlaceData(
                name=place.name,
                url=place.url,
                place_id=data['result']['place_id'],
                json_data=response.text,
                last_scraped=datetime.now().isoformat(),
            )
            self.checkpoint[place.url] = place_data
            await self.checkpoint_queue.put(place_data)
            return place_data
        except Exception as e:
            print(f"Error resolving place {place.name}: {e}")
            return None

    def _is_stale(self, place_data: PlaceData) -> bool:
        """Check if the place data is stale based on last_scraped date"""
        if not place_data.last_scraped:
            return True

        try:
            last_scraped = datetime.fromisoformat(place_data.last_scraped)
            days_old = (datetime.now() - last_scraped).days
            return days_old > self.stale_days
        except ValueError:
            return True

    def _load_checkpoint(self):
        try:
            df = pd.read_csv(self.checkpoint_filename)
            self.checkpoint = {row['url']: PlaceData(**row) for row in df.to_dict(orient='records')}
        except Exception as e:
            print(f"Error loading checkpoint: {e}")

    async def _checkpoint_writer(self):
        """Single writer coroutine - no race conditions"""
        checkpoint_exists = os.path.exists(self.checkpoint_filename)

        async with aiofiles.open(self.checkpoint_filename, 'a') as f:
            writer = AsyncDictWriter(f, fieldnames=['name', 'url', 'place_id', 'last_scraped', 'json_data'],
                                     extrasaction='ignore', quoting=csv.QUOTE_ALL, restval="NULL")

            if not checkpoint_exists:
                await writer.writeheader()

            while True:
                place_data = await self.checkpoint_queue.get()
                if place_data is None:  # Shutdown signal which we add in __aexit__
                    break

                try:
                    await writer.writerow(asdict(place_data))
                    await f.flush()
                except Exception as e:
                    print(f"Error saving checkpoint for {place_data.name}: {e}")
                finally:
                    self.checkpoint_queue.task_done()


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
    async def scrape_place(self, place: CSVPlaceData) -> PlaceData:
        page = await self.browser.new_page()

        try:
            # 1. Get place_id from CID through scraping the page
            place_id = await self._get_place_id(page, place)
            print(f"place_id: {place_id}")

            # 2. Scrape the detailed data and the api data in parallel
            api_data = asyncio.create_task(self._get_api_data(place_id))
            scraped_data = asyncio.create_task(self._scrape_detailed_data(page, place_id))
            api_data, scraped_data = await asyncio.gather(api_data, scraped_data)

            # 3. Combine the data into a Place object
            return self._build_place(place, place_id, api_data, scraped_data)
        except Exception as e:
            print(f"Error scraping place {place.name}: {e}")
            return None
        finally:
            await page.close()

    # Private methods
    async def _get_place_id(self, page, place: CSVPlaceData) -> str:
        url_hex = place.url.split('0x')[-1]
        cid = int(url_hex, 16)
        print(f"cid: {cid}")
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

    async def _scrape_detailed_data(self, page, place_id: str) -> dict:

        # on the overview tab we need to scrape rating, price level, and opening hours
        # on the reviews tab we should try grab some of the most relevant reviews
        # on the about page we should grab the restaurant attributes

        scraped_data = PlaceScrapedData()
        side_panel_div = page.locator('div.w6VYqd')

        # 1. Overview tab
        top_level_info_div = side_panel_div.locator('div.skqShb')

        # 1.1. Rating
        rating_div = top_level_info_div.locator('div.F7nice')
        rating_text = await rating_div.locator('span span').nth(0).inner_text()
        scraped_data.rating = float(rating_text.strip())

        # 1.2. Price level
        price_level_div = top_level_info_div.locator('span.mgr77e span').nth(2)
        price_level_text = await price_level_div.locator('span span').inner_text()
        scraped_data.price_level = price_level_text.strip()

        # 1.3 Category
        category_button = top_level_info_div.locator('button[jsaction*="category"]')
        category_text = await category_button.inner_text()
        scraped_data.category = category_text.strip()

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
                print(f"Expanding {button_count} reviews...")

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

            return review_data if review_data else []

        except Exception as e:
            print(f"Error extracting expanded reviews: {e}")
            return []

    def _build_place(self, place: CSVPlaceData, place_id: str,
                     api_data: dict, scraped_data: dict) -> Place:
        return Place(api_data, scraped_data)


class CheckpointManager:
    pass


class PlaceStore:
    pass


class ScrapingPipeline:
    def __init__(self):
        self.csv_processor = CSVProcessor()
        # self.place_scraper = PlaceScraper()
        #   self.checkpoint_manager = CheckpointManager()
        self.place_store = PlaceStore()

    async def process_csv_file(self, csv_file: str):
        places = self.csv_processor.parse(csv_file)
        # await self.process_places(places, csv_file)
        async with PlaceScraper() as place_scraper:
            result = await place_scraper.scrape_place(places[0])
            print(result)

    async def process_places(self, places: list[CSVPlaceData], csv_file: str):
        # self.checkpoint_manager.load_checkpoint(csv_file)
        semaphore = asyncio.Semaphore(10)

        async with PlaceScraper() as place_scraper:
            async def process_single_place(place: CSVPlaceData):
                async with semaphore:
                    # # Check checkpoint first
                    # if self.checkpoint_manager.is_processed(place):
                    #     return self.checkpoint_manager.get_cached(place)

                    # # Scrape new data
                    # result = await self.place_scraper.scrape_place(place)

                    # # Save checkpoint immediately
                    # await self.checkpoint_manager.save(result)
                    # return result
                    return None

        tasks = [process_single_place(place) for place in places]
        results = await asyncio.gather(*tasks)

        print(len(results))
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
