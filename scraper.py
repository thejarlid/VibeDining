from dataclasses import dataclass, asdict, field
import os
import argparse
import csv
import pandas as pd
import requests
import asyncio
from tqdm import tqdm
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
MAPS_API_KEY = os.getenv('MAPS_API_KEY')
print(MAPS_API_KEY)


@dataclass
class PlaceData:
    name: str
    place_id: str
    json_data: str
    attributes: list[str] = field(default_factory=list)


async def scrape_places_for_attributes(csv_file: str, place_data: list[PlaceData]):
    print(f"Scraping {len(place_data)} places")
    # Once we have the base data and information we need to scrape the about section
    # on the site to get details about the place wrt to the atmosphere, vibe, offerings, etc.
    # we could use the places api to get this information but we would be capped at 1000 requests
    # just by testing on my small dataset (~400 places) we'll hit that with 3 runs
    url_base = "https://www.google.com/maps/place/?q=place_id:"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for placed in tqdm(place_data, desc="Scraping places"):
            tqdm.write(f"Scraping {placed.name}")
            url = url_base + placed.place_id
            page = await browser.new_page()
            try:
                await page.goto(url)
            except Exception as e:
                tqdm.write(f"Error navigating to {url}: {e}")
                await page.close()
                continue

            about_button = page.locator('button.hh2c6').filter(has=page.locator('div.Gpq6kf', has_text='About'))
            if await about_button.count() == 0:
                tqdm.write(f"No about button found for {placed.name}")
                await page.close()
                continue
            await about_button.click()
            await page.wait_for_selector("li.hpLkke span:nth-of-type(2)", state="visible", timeout=1000)
            second_spans = page.locator('li.hpLkke span:nth-of-type(2)')
            if await second_spans.count() == 0:
                tqdm.write(f"No attributes found for {placed.name}")
                await page.close()
                continue
            attributes = await second_spans.all_text_contents()
            placed.attributes = attributes
            await page.close()

        with open(f"{csv_file.split('.')[0]}_place_data_with_attributes.csv", 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'place_id', 'json_data', 'attributes'])
            writer.writeheader()
            for record in place_data:
                writer.writerow(asdict(record))  # Convert dataclass to dictionary
        print(f"Saved {len(place_data)} places to place_data_with_attributes.csv")


def process_csv_file(csv_file: str):
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
            return [PlaceData(**row) for row in place_data.to_dict(orient='records')]

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
            'attributes': []
        })
        print(f"Processed {place}")

    with open(f"{csv_file.split('.')[0]}_place_data.csv", 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'place_id', 'json_data'], extrasaction='ignore')
        writer.writeheader()
        writer.writerows(place_data)
    print(f"Saved {len(place_data)} places to place_data.csv")

    return [PlaceData(**row) for row in place_data]


def process_csv_directory(csv_directory: str):
    print(f"Processing CSV directory: {csv_directory}")
    expanded_path = os.path.expanduser(csv_directory)

    for file in os.listdir(expanded_path):
        if file.endswith('.csv'):
            process_csv_file(os.path.join(expanded_path, file))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('path', type=str, help='Path to directory containing CSV files or path to a specific CSV file')
    args = parser.parse_args()

    path = args.path

    if os.path.isdir(path):
        process_csv_directory(path)
    elif os.path.isfile(path) and path.endswith('.csv'):
        place_data = process_csv_file(path)
        await scrape_places_for_attributes(path, place_data)
    else:
        raise ValueError(f"'{path}' is neither a valid directory nor a CSV file")


if __name__ == '__main__':
    asyncio.run(main())
