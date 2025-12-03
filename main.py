import asyncio
import json
import os
import re
import time
from datetime import datetime
import pytz
from playwright.async_api import async_playwright
import requests

# Configuration
TELEGRAM_TOKEN = "8532240457:AAHPuU0y_ajjIMs8uubysjsPJtl32Hx4E6g"
CHAT_ID = "1018766092"
SEEN_FILE = "seen_listings.json"

# Moldova timezone
MD_TZ = pytz.timezone('Europe/Chisinau')

def is_quiet_hours():
    """Check if current time in Moldova is outside 09:00-21:00"""
    md_time = datetime.now(MD_TZ)
    hour = md_time.hour
    return hour >= 21 or hour < 9

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
    
    # Filtered URL: Centru + Rîșcanovka, Garage + Underground parking, Sale + Rent
    url = "https://999.md/ru/list/real-estate/garages-and-parking?appl=1&ef=16,32,9441,46&eo=13859,12885,12900,12912&o_46_259=1043,1041&o_32_9_12900_13859=15667,15664&o_16_1=912,776"
    
    seen_ids = set()
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        
        # Get page content and find listing links using regex
        content = await page.content()
        
        # Find all listing links (format: /ru/12345678 - 8 digit IDs)
        listing_pattern = r'href="(/ru/(\d{7,9}))"'
        matches = re.findall(listing_pattern, content)
        
        print(f"999.md: Found {len(matches)} potential listing links")
        
        for href, listing_id in matches:
            if listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)
            
            full_url = f"https://999.md{href}"
            
            listings.append({
                "id": f"999_{listing_id}",
                "title": f"Listing #{listing_id}",
                "price": "See link",
                "location": "",
                "url": full_url,
                "source": "999.md",
                "full_text": ""
            })
        
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
    
    # Check if it's quiet hours (outside 10:00-22:00 Moldova time)
    quiet = is_quiet_hours()
    if quiet:
        print("Quiet hours (outside 09:00-21:00 MD) - skipping notifications")
    
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
        print(f"Found {len(listings_999)} total listings on 999.md")
        
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
        
        # Skip sending during quiet hours
        if quiet:
            continue
        
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
    
    # Send summary (skip during quiet hours)
    if not quiet:
        summary = f"""📊 <b>Hourly Check</b>

Checked {len(all_listings)} listings, {new_in_area} new in your area.

🔍 <a href="https://999.md/ru/list/real-estate/garages-and-parking?appl=1&ef=16,32,9441,46&eo=13859,12885,12900,12912&o_46_259=1043,1041&o_32_9_12900_13859=15667,15664&o_16_1=912,776">Browse all listings</a>"""
        
        send_telegram(summary)
    
    return new_in_area


async def run_scheduler():
    print("🚗 Garage Tracker started!")
    send_telegram("🚗 Garage Tracker started! Checking at 09:00, 12:00, 15:00, 18:00, 21:00 MD time")
    
    # Check times in Moldova (9, 12, 15, 18, 21)
    check_hours = [9, 12, 15, 18, 21]
    
    while True:
        try:
            await check_for_new_listings()
        except Exception as e:
            print(f"Error: {e}")
            send_telegram(f"⚠️ Error: {str(e)[:100]}")
        
        # Calculate seconds until next check time
        now = datetime.now(MD_TZ)
        current_hour = now.hour
        current_minute = now.minute
        
        # Find next check hour
        next_check = None
        for h in check_hours:
            if h > current_hour or (h == current_hour and current_minute < 1):
                next_check = h
                break
        
        # If no check left today, next is tomorrow at 10:00
        if next_check is None:
            next_check = check_hours[0]
            hours_until = (24 - current_hour) + next_check
        else:
            hours_until = next_check - current_hour
        
        minutes_until = (hours_until * 60) - current_minute
        seconds_until = (minutes_until * 60) - now.second
        
        print(f"Next check at {next_check}:00 MD time (in {hours_until}h {60-current_minute}min)")
        await asyncio.sleep(seconds_until)


if __name__ == "__main__":
    asyncio.run(run_scheduler())
