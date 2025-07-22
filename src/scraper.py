from dataclasses import asdict
from datetime import datetime
import time
import os
import argparse
import csv
import json
import pandas as pd
import requests
import asyncio
import httpx
from tqdm import tqdm
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from model import CSVPlaceData, PlaceData, Place, Review

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
                places.append(CSVPlaceData(
                    name=row['Title'],
                    url=row['URL']
                ))
        return places


class PlaceResolver:
    def __init__(self, google_maps_api_key: str, csv_file: str, stale_days: int = 30):
        self.google_maps_api_key = google_maps_api_key
        self.csv_file = csv_file
        self.stale_days = stale_days
        self.client = None
        self.checkpoint = {}
        self.checkpoint_filename = None
        self.checkpoint_file = None
        self.checkpoint_writer = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient()
        self.checkpoint_filename = f"{self.csv_file.split('.')[0]}_data_checkpoint.csv"
        checkpoint_exists = os.path.exists(self.checkpoint_filename)
        self.checkpoint_file = open(self.checkpoint_filename, 'a')

        self.checkpoint_writer = csv.DictWriter(self.checkpoint_file, fieldnames=['name', 'url', 'place_id', 'last_scraped', 'json_data'], extrasaction='ignore')
        if not checkpoint_exists:
            self.checkpoint_writer.writeheader()
        else:
            self._load_checkpoint()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
            self.client = None
        if self.checkpoint_file:
            self.checkpoint_file.close()
            self.checkpoint_file = None
            self.checkpoint_writer = None

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
            self._save_checkpoint(place_data)
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
            print(f"Loaded {len(self.checkpoint)} places from checkpoint")
        except Exception as e:
            print(f"Error loading checkpoint: {e}")

    def _save_checkpoint(self, place: PlaceData):
        try:
            self.checkpoint_writer.writerow(asdict(place))
        except Exception as e:
            print(f"Error saving checkpoint for {place}: {e}")


class PlaceScraper:
    pass


class PlaceStore:
    pass


class ScrapingPipeline:
    def __init__(self):
        self.csv_processor = CSVProcessor()
        self.place_resolver = None
        self.place_scraper = PlaceScraper()
        self.place_store = PlaceStore()

    async def process_csv_file(self, csv_file: str):
        places = self.csv_processor.parse(csv_file)
        await self.process_places(places, csv_file)

    async def process_places(self, places: list[CSVPlaceData], csv_file: str):
        semaphore = asyncio.Semaphore(30)
        async with PlaceResolver(MAPS_API_KEY, csv_file) as resolver:
            async def process_place(place: CSVPlaceData):
                async with semaphore:
                    place_data = await resolver.resolve_place(place)
                    pass

            tasks = [process_place(place) for place in places]
            await asyncio.gather(*tasks)


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
