# Garage Tracker 🚗

Monitors **999.md** and **makler.md** for new garage listings in Chișinău and sends Telegram notifications.

## Deploy to Railway (Free Tier)

1. **Create a GitHub repository:**
   ```bash
   cd /Users/andreishapa/Documents/garage-tracker
   git init
   git add .
   git commit -m "Initial commit"
   ```
   Then push to GitHub

2. **Deploy on Railway:**
   - Go to [railway.app](https://railway.app)
   - Sign in with GitHub
   - Click "New Project" → "Deploy from GitHub repo"
   - Select your repository
   - Railway will auto-detect the Dockerfile and deploy

3. **Done!** The bot runs 24/7 and checks every hour

## Local Testing

```bash
pip install -r requirements.txt
playwright install chromium
python main.py
```

## Configuration

Edit `main.py` to customize:
- `AREA_KEYWORDS` - location keywords to highlight
- Uncomment line 138 to **only** get notifications for your area
- Change `3600` (line 149) to adjust check interval

## Files

- `main.py` - Main script with Playwright scraping
- `requirements.txt` - Python dependencies  
- `Dockerfile` - Railway deployment config
- `seen_listings.json` - Auto-created, tracks seen listings
