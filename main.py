import asyncio
import json
import os
import re
import time
from datetime import datetime
from playwright.async_api import async_playwright
import requests

# Configuration
TELEGRAM_TOKEN = "8532240457:AAHPuU0y_ajjIMs8uubysjsPJtl32Hx4E6g"
CHAT_ID = "1018766092"
SEEN_FILE = "seen_listings.json"

# Area keywords from your map (near bd. Grigore Vieru)
AREA_KEYWORDS = [
    # Main streets
    "grigore vieru", "grigorе vieru", "gr. vieru", "григоре виеру",
    "albișoara", "albisoara", "албишоара", "албишoara",
    "pușkin", "puskin", "пушкин", "pushkin",
    "română", "romana", "романэ", "романа",
    # Nearby streets from map
    "petru rareș", "petru rares", "петру рареш",
    "arhanghel mihail", "архангел михаил",
    "piața veche", "piata veche", "пяца веке",
    "fantalului", "фанталулуй",
    "ierusalim", "иерусалим",
    "andrei botezatu", "андрей ботезату",
    "bănulescu-bodoni", "banulescu-bodoni", "бэнулеску-бодони", "митрополит гавриил",
    # Landmarks
    "ionesco", "ионеско",
    "turist hotel", "турист",
]


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")


def matches_area(text):
    if not text:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in AREA_KEYWORDS)


async def scrape_999md(page):
    """Scrape garage listings from 999.md using Playwright"""
    listings = []
    url = "https://999.md/ru/list/real-estate/garages-and-parking"
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        
        # Get page content and find listing links using regex
        content = await page.content()
        
        # Find all listing links (format: /ru/12345678 - 8 digit IDs)
        listing_pattern = r'href="(/ru/(\d{7,9}))"'
        matches = re.findall(listing_pattern, content)
        
        print(f"999.md: Found {len(matches)} potential listing links")
        
        # Get unique listing IDs
        seen_ids = set()
        for href, listing_id in matches:
            if listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)
            
            full_url = f"https://999.md{href}"
            
            # Try to find title and price near this link in the HTML
            # For now, we'll visit each listing page to get details
            listings.append({
                "id": f"999_{listing_id}",
                "title": f"Listing #{listing_id}",
                "price": "See link",
                "location": "",
                "url": full_url,
                "source": "999.md",
                "full_text": ""
            })
        
        # If we found listings, try to get more details from the page
        if listings:
            # Try to extract titles from the listing cards
            cards = await page.query_selector_all('a[href*="/ru/"]')
            for card in cards:
                try:
                    href = await card.get_attribute("href")
                    if not href or not re.match(r'/ru/\d{7,9}', href):
                        continue
                    
                    listing_id = href.split("/")[-1]
                    
                    # Get text content of the card
                    text = await card.inner_text()
                    if text and len(text) > 5:
                        # Update the listing with actual title
                        for lst in listings:
                            if lst["id"] == f"999_{listing_id}":
                                lst["title"] = text.split("\n")[0][:100]
                                lst["full_text"] = text
                                break
                except:
                    continue
                    
    except Exception as e:
        print(f"Error scraping 999.md: {e}")
    
    return listings


async def check_for_new_listings():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for new garage listings...")
    
    seen = load_seen()
    all_listings = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        
        # Scrape 999.md
        listings_999 = await scrape_999md(page)
        all_listings.extend(listings_999)
        print(f"Found {len(listings_999)} listings on 999.md")
        
        await browser.close()
    
    print(f"Total: {len(all_listings)} listings")
    
    new_count = 0
    new_in_area = 0
    
    for listing in all_listings:
        if listing["id"] in seen:
            continue
        
        seen.add(listing["id"])
        new_count += 1
        
        in_area = matches_area(listing["full_text"])
        
        # Only notify for listings in your area
        if not in_area:
            continue
        
        new_in_area += 1
        
        title = listing['title'] if listing['title'] != f"Listing #{listing['id'].split('_')[1]}" else "New listing"
        
        message = f"""🚗 <b>New Garage Listing!</b> 📍 IN YOUR AREA!

<b>{title}</b>
💰 {listing['price']}
📍 {listing['location']}
🌐 {listing['source']}

{listing['url']}"""
        
        send_telegram(message)
        new_count += 1
        time.sleep(0.5)
    
    save_seen(seen)
    print(f"Sent {new_in_area} new listings to Telegram")
    
    # Send summary (always, so user knows bot is running)
    summary = f"""📊 <b>Hourly Check</b>

Checked {len(all_listings)} listings, {new_in_area} new in your area.

🔍 <a href="https://999.md/ru/list/real-estate/garages-and-parking">Browse all listings</a>"""
    
    send_telegram(summary)
    
    return new_in_area


async def run_scheduler():
    print("🚗 Garage Tracker started!")
    send_telegram("🚗 Garage Tracker started! Checking every hour...")
    
    while True:
        try:
            await check_for_new_listings()
        except Exception as e:
            print(f"Error: {e}")
            send_telegram(f"⚠️ Error: {str(e)[:100]}")
        
        print("Waiting 1 hour until next check...")
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(run_scheduler())
