import asyncio
import json
import os
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
    "grigore vieru", "grigorе vieru", "gr. vieru",
    "albișoara", "albisoara", "албишоара",
    "pușkin", "puskin", "пушкин",
    "română", "romana", "романэ",
    "centru", "центр", "center",
    "știrbei vodă", "stirbei voda",
    "columna", "колумна",
    "ștefan cel mare", "stefan cel mare",
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
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)  # Extra wait for dynamic content
        
        # Get all listing items
        items = await page.query_selector_all('[data-testid="ads-list-item"], .ads-list-photo-item, article[class*="item"]')
        
        if not items:
            # Try alternative selectors
            items = await page.query_selector_all('a[href*="/ru/"][href*="garages"]')
        
        for item in items:
            try:
                # Try to get the link
                link = await item.get_attribute("href")
                if not link:
                    link_elem = await item.query_selector("a")
                    if link_elem:
                        link = await link_elem.get_attribute("href")
                
                if not link or "garages" not in link:
                    continue
                
                listing_id = "999_" + link.split("/")[-1].split("?")[0]
                full_url = f"https://999.md{link}" if link.startswith("/") else link
                
                # Get title
                title_elem = await item.query_selector('[class*="title"], h3, h4')
                title = await title_elem.inner_text() if title_elem else "No title"
                
                # Get price
                price_elem = await item.query_selector('[class*="price"]')
                price = await price_elem.inner_text() if price_elem else "Price N/A"
                
                # Get location
                location_elem = await item.query_selector('[class*="region"], [class*="location"]')
                location = await location_elem.inner_text() if location_elem else ""
                
                listings.append({
                    "id": listing_id,
                    "title": title.strip(),
                    "price": price.strip(),
                    "location": location.strip(),
                    "url": full_url,
                    "source": "999.md",
                    "full_text": f"{title} {location}"
                })
            except Exception as e:
                continue
                
    except Exception as e:
        print(f"Error scraping 999.md: {e}")
    
    return listings


async def scrape_makler(page):
    """Scrape garage listings from makler.md"""
    listings = []
    url = "https://makler.md/chisinau/real-estate/real-estate-for-rent/garage-parking-for-rent"
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        
        items = await page.query_selector_all('[class*="announcement"], [class*="classified"], article, .ad-item')
        
        for item in items:
            try:
                link_elem = await item.query_selector('a[href*="/real-estate/"]')
                if not link_elem:
                    continue
                
                link = await link_elem.get_attribute("href")
                listing_id = "makler_" + link.split("/")[-1].split("?")[0]
                full_url = f"https://makler.md{link}" if link.startswith("/") else link
                
                title_elem = await item.query_selector('h2, h3, [class*="title"]')
                title = await title_elem.inner_text() if title_elem else "No title"
                
                price_elem = await item.query_selector('[class*="price"]')
                price = await price_elem.inner_text() if price_elem else "Price N/A"
                
                location_elem = await item.query_selector('[class*="location"], [class*="address"]')
                location = await location_elem.inner_text() if location_elem else ""
                
                listings.append({
                    "id": listing_id,
                    "title": title.strip(),
                    "price": price.strip(),
                    "location": location.strip(),
                    "url": full_url,
                    "source": "makler.md",
                    "full_text": f"{title} {location}"
                })
            except Exception as e:
                continue
                
    except Exception as e:
        print(f"Error scraping makler.md: {e}")
    
    return listings


async def check_for_new_listings():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for new garage listings...")
    
    seen = load_seen()
    all_listings = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        # Scrape both sources
        listings_999 = await scrape_999md(page)
        all_listings.extend(listings_999)
        print(f"Found {len(listings_999)} listings on 999.md")
        
        listings_makler = await scrape_makler(page)
        all_listings.extend(listings_makler)
        print(f"Found {len(listings_makler)} listings on makler.md")
        
        await browser.close()
    
    print(f"Total: {len(all_listings)} listings")
    
    new_count = 0
    for listing in all_listings:
        if listing["id"] in seen:
            continue
        
        seen.add(listing["id"])
        
        in_area = matches_area(listing["full_text"])
        area_tag = "📍 IN YOUR AREA!" if in_area else ""
        
        # Uncomment next line to only get notifications for your area:
        # if not in_area: continue
        
        message = f"""🚗 <b>New Garage Listing!</b> {area_tag}

<b>{listing['title']}</b>
💰 {listing['price']}
📍 {listing['location']}
🌐 {listing['source']}

{listing['url']}"""
        
        send_telegram(message)
        new_count += 1
        time.sleep(1)
    
    save_seen(seen)
    print(f"Sent {new_count} new listings to Telegram")
    
    return new_count


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
