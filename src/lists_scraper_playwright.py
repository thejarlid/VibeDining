import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
# QA0Szd > div > div > div.w6VYqd > div.bJzME.tTVLSc > div > div.e07Vkf.kA9KIf.dS8AEf > div > div > div:nth-child(1) > div > div > button.hh2c6.G7m0Af


async def main():
    async with async_playwright() as p:

        # load page
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://maps.app.goo.gl/yE2mDzeJZvzSRv3Z6")
        await page.locator(".IFMGgb").first.wait_for()
        list_title = await page.title()
        if not list_title:
            return
        print(f"loading saved items in {list_title}")

        # identify scrolling element containing the saved items
        scrolling_element_xpath = '//*[@id = "QA0Szd"]/div/div/div[1]/div[2]/div/div[1]/div/div/div[4]'
        scroll_element = page.locator(scrolling_element_xpath)

        previous_height = 0
        current_height = 0
        stable_count = 0
        max_stable_checks = 3
        scroll_delay = 1000
        while True:
            # scroll element to the bottom
            current_height = await scroll_element.evaluate("element => element.scrollHeight")
            await scroll_element.evaluate("element => element.scrollTop = element.scrollHeight")
            await scroll_element.page.wait_for_timeout(scroll_delay)

            # Check if height has changed
            if current_height == previous_height:
                stable_count += 1
                print(f"Height stable ({current_height}px) - Check {stable_count}/{max_stable_checks}")
                if stable_count >= max_stable_checks:
                    print("No more content loading. Exiting scroll loop.")
                    break
            else:
                stable_count = 0
                print(f"Height changed: {previous_height}px → {current_height}px")
            previous_height = current_height

        # list_items = page.locator(".m6QErb")
        # print(f"loaded {await list_items.count()} items")

        page_content = await page.content()
        soup = BeautifulSoup(page_content, 'html.parser')
        items = soup.select('#QA0Szd > div > div > div.w6VYqd > div.bJzME.tTVLSc > div > div.e07Vkf.kA9KIf > div > div > div.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde.ussYcc > div')
        print(f"loaded {len(items)} items")
        # every other 'div' element in 'items' is not actually a saved location! So let's drop these.
        items_cleaned = items[::2]
        print(len(items_cleaned))
        # 66 (check that it is the same length as your saved list)

        # test one item to see what information can be extracted
        print(items_cleaned[0].prettify())

asyncio.run(main())
