# Lego-Auction
# LEGO Auction Catalog

A mobile-first HTML catalog for browsing LEGO lots scraped from Lloyd's Auctions.

## 🚀 Quick Start with GitHub Actions

### One-Click Deployment

1. **Navigate to:** https://github.com/jimwarlock/Lego-Auction/actions
2. **Select:** "Build & Deploy LEGO Catalog" workflow
3. **Click:** "Run workflow" button (top right)
4. **Wait:** 10-15 minutes for scraper to complete
5. **Enable Pages:** Go to Settings → Pages, set Branch to `main` and Folder to `/docs`
6. **Visit your live site:** https://jimwarlock.github.io/Lego-Auction/

### Manual Local Testing

```bash
pip install -r requirements.txt
python scraper.py
cp data.json docs/
open docs/index.html