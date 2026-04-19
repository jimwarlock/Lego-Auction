#!/usr/bin/env python3
"""Lloyd's Auctions LEGO Lot Scraper"""
import requests
from bs4 import BeautifulSoup
import json
import re
import time
from urllib.parse import urljoin
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

AUCTION_IDS = [68624, 69406, 69407, 69498, 69509, 69510]
BASE_URL = "https://www.lloydsonline.com.au"
LOTS_PAGE_URL = f"{BASE_URL}/AuctionLots.aspx?smode=0&aid="
REBRICKABLE_API = "https://rebrickable.com/api/v3/lego"
REBRICKABLE_CACHE = {}
OUTPUT_FILE = "data.json"
REQUEST_TIMEOUT = 10
REQUEST_DELAY = 0.5

def get_rebrickable_set(set_id):
    if not set_id:
        return None
    set_id = str(set_id).strip()
    if set_id in REBRICKABLE_CACHE:
        return REBRICKABLE_CACHE[set_id]
    try:
        url = f"{REBRICKABLE_API}/sets/{set_id}/"
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            result = {
                'set_id': data.get('set_num'),
                'name': data.get('name'),
                'theme_id': data.get('theme_id'),
                'image_url': data.get('set_img_url'),
                'num_parts': data.get('num_parts'),
            }
            REBRICKABLE_CACHE[set_id] = result
            logger.info(f"Resolved LEGO set {set_id}: {result['name']}")
            time.sleep(REQUEST_DELAY)
            return result
    except Exception as e:
        logger.warning(f"Failed to fetch Rebrickable set {set_id}: {e}")
    return None

def extract_set_id_from_title(title):
    if not title:
        return None
    patterns = [r'\b(\d{5})-?\d*\b', r'\b(\d{4})-?\d*\b', r'set\s+#?(\d+)']
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def parse_lot_page(html_content, auction_id, page_num):
    soup = BeautifulSoup(html_content, 'html.parser')
    lots = []
    lot_selectors = ['tr[class*="lot"]', 'div[class*="lot-item"]', 'div[class*="lot"]', 'div[data-lot]']
    lot_containers = []
    for selector in lot_selectors:
        lot_containers = soup.select(selector)
        if lot_containers:
            logger.info(f"Found {len(lot_containers)} lots using selector: {selector}")
            break
    if not lot_containers:
        lot_containers = soup.find_all('a', href=re.compile(r'LotDetail|lot', re.I))
        logger.info(f"Fallback: Found {len(lot_containers)} lot links")
    for idx, container in enumerate(lot_containers):
        try:
            lot = {}
            container_text = container.get_text(strip=True)
            lot_num_match = re.search(r'(?:Lot\s*#?)?(\d{1,5})', container_text)
            if lot_num_match:
                lot['lot_number'] = int(lot_num_match.group(1))
            bid_match = re.search(r'\$?\s*([\d,]+(?:\.\d{2})?)', container_text)
            if bid_match:
                try:
                    lot['current_bid'] = float(bid_match.group(1).replace(',', ''))
                except ValueError:
                    lot['current_bid'] = 0
            title_elem = container.find('a') or container.find(['span', 'div'])
            if title_elem:
                lot['title'] = title_elem.get_text(strip=True)
            else:
                lot['title'] = container_text[:100]
            lot_detail_url = None
            link = container if container.name == 'a' else container.find('a', href=re.compile(r'LotDetail|lot', re.I))
            if link:
                href = link.get('href', '')
                if href:
                    lot_detail_url = urljoin(BASE_URL, href)
            lot['lot_detail_url'] = lot_detail_url
            lot['auction_id'] = auction_id
            img_elem = container.find('img')
            if img_elem:
                img_src = img_elem.get('src', '')
                if img_src:
                    lot['lot_image_url'] = urljoin(BASE_URL, img_src)
            set_id = extract_set_id_from_title(lot.get('title', ''))
            lot['set_id_extracted'] = set_id
            status_patterns = ['sold', 'unsold', 'withdrawn', 'passed']
            status_match = re.search('|'.join(status_patterns), container_text, re.I)
            if status_match:
                lot['status'] = status_match.group(0).lower()
            if lot.get('lot_number') and lot.get('title'):
                lots.append(lot)
                logger.debug(f"Parsed lot #{lot['lot_number']}: {lot['title'][:50]}")
        except Exception as e:
            logger.warning(f"Error parsing lot at index {idx}: {e}")
            continue
    return lots

def scrape_auction(auction_id):
    logger.info(f"Starting scrape of auction {auction_id}")
    all_lots = []
    page = 1
    max_pages = 100
    while page <= max_pages:
        try:
            url = f"{LOTS_PAGE_URL}{auction_id}&page={page}"
            logger.info(f"Fetching auction {auction_id}, page {page}: {url}")
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            lots = parse_lot_page(resp.text, auction_id, page)
            if not lots:
                logger.info(f"No lots found on page {page}, assuming end of auction")
                break
            all_lots.extend(lots)
            logger.info(f"Scraped {len(lots)} lots from page {page}")
            page += 1
            time.sleep(REQUEST_DELAY)
        except requests.RequestException as e:
            logger.error(f"Failed to fetch page {page} of auction {auction_id}: {e}")
            break
    logger.info(f"Completed auction {auction_id}: {len(all_lots)} total lots")
    return all_lots

def deduplicate_lots(all_lots):
    deduped = {}
    for lot in all_lots:
        set_id = lot.get('set_id_extracted')
        if not set_id:
            set_id = f"unknown_{lot.get('lot_number')}_{lot.get('auction_id')}"
        if set_id not in deduped:
            deduped[set_id] = {'set_id': set_id, 'title': lot.get('title'), 'theme': None, 'set_name': None, 'image_url': None, 'rebrickable_image_url': None, 'max_bid': lot.get('current_bid', 0), 'min_bid': lot.get('current_bid', 0), 'bid_range': None, 'lot_count': 0, 'lot_numbers': [], 'lots': []}
        entry = deduped[set_id]
        entry['lots'].append(lot)
        entry['lot_numbers'].append(lot.get('lot_number'))
        entry['lot_count'] += 1
        bid = lot.get('current_bid', 0)
        entry['max_bid'] = max(entry['max_bid'], bid)
        entry['min_bid'] = min(entry['min_bid'], bid)
        if not entry['image_url'] and lot.get('lot_image_url'):
            entry['image_url'] = lot.get('lot_image_url')
    return deduped

def resolve_lego_details(deduped_lots):
    for set_id, entry in deduped_lots.items():
        if set_id.startswith('unknown_'):
            continue
        set_details = get_rebrickable_set(set_id)
        if set_details:
            entry['set_name'] = set_details.get('name')
            entry['theme_id'] = set_details.get('theme_id')
            entry['rebrickable_image_url'] = set_details.get('image_url')
            entry['num_parts'] = set_details.get('num_parts')
            if not entry['image_url']:
                entry['image_url'] = entry['rebrickable_image_url']

def finalize_output(deduped_lots):
    output = []
    for set_id, entry in deduped_lots.items():
        record = {'set_id': entry['set_id'], 'set_name': entry['set_name'], 'title': entry['title'], 'theme_id': entry.get('theme_id'), 'image_url': entry['image_url'], 'current_highest_bid': entry['max_bid'], 'min_bid': entry['min_bid'], 'bid_range': f"${entry['min_bid']:.2f} - ${entry['max_bid']:.2f}" if entry['min_bid'] != entry['max_bid'] else f"${entry['max_bid']:.2f}", 'lot_count': entry['lot_count'], 'lot_numbers': sorted(entry['lot_numbers']), 'lot_number_range': f"{min(entry['lot_numbers'])}-{max(entry['lot_numbers'])}" if entry['lot_numbers'] else None, 'num_parts': entry.get('num_parts'), 'lots': [{'auction_id': lot['auction_id'], 'lot_number': lot['lot_number'], 'lot_detail_url': lot.get('lot_detail_url'), 'current_bid': lot.get('current_bid'), 'lot_image_url': lot.get('lot_image_url'), 'status': lot.get('status')} for lot in entry['lots']]}
        output.append(record)
    return output

def main():
    logger.info("=" * 80)
    logger.info("Lloyd's Auctions LEGO Lot Scraper")
    logger.info("=" * 80)
    all_lots = []
    for auction_id in AUCTION_IDS:
        try:
            lots = scrape_auction(auction_id)
            all_lots.extend(lots)
            logger.info(f"Auction {auction_id}: {len(lots)} lots scraped")
        except Exception as e:
            logger.error(f"Critical error scraping auction {auction_id}: {e}")
    logger.info(f"Total lots scraped across all auctions: {len(all_lots)}")
    logger.info("Deduplicating lots by LEGO set ID...")
    deduped_lots = deduplicate_lots(all_lots)
    logger.info(f"After deduplication: {len(deduped_lots)} unique sets")
    logger.info("Resolving LEGO set details via Rebrickable API...")
    resolve_lego_details(deduped_lots)
    output = finalize_output(deduped_lots)
    output.sort(key=lambda x: x['current_highest_bid'], reverse=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info(f"Output written to {OUTPUT_FILE}")
    logger.info(f"Total deduped records: {len(output)}")
    logger.info("=" * 80)

if __name__ == '__main__':
    main()