"""
Competitor Product Scraper for TOPPERS AI Business Intelligence.
Two-pass extraction: BeautifulSoup for HTML parsing + Gemini AI for structured extraction.
"""
import sys
import requests
from bs4 import BeautifulSoup
import html2text
import json
import re
import time
import google.generativeai as genai

# Force UTF-8 for Windows
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

# Reuse the same headers pattern from app.py
SCRAPE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

# Configure Gemini (reuses the key from app.py — already configured globally)
model = genai.GenerativeModel('gemini-2.5-flash')


def search_brand(brand_name):
    """Search for a brand website using DuckDuckGo. Returns top URL."""
    try:
        from duckduckgo_search import DDGS
        ddgs = DDGS()
        results = list(ddgs.text(f"{brand_name} official website shop", max_results=3))
        if results:
            return results[0].get('href', None)
    except Exception as e:
        print(f"Brand search error: {e}")

    # Fallback: try common patterns
    brand_slug = brand_name.lower().replace(' ', '')
    return f"https://www.{brand_slug}.com"


def fetch_page(url):
    """Fetch a page and return (soup, raw_text, title)."""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    resp = requests.get(url, headers=SCRAPE_HEADERS, timeout=15, allow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')
    title = url
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Remove noise
    for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript', 'iframe']):
        tag.decompose()

    # Convert to text
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.ignore_emphasis = False
    converter.body_width = 0
    raw_text = converter.handle(str(soup))

    return soup, raw_text, title, url


def extract_products_bs4(soup):
    """
    Pass 1: BeautifulSoup heuristic extraction.
    Looks for common e-commerce patterns: price elements, product cards, etc.
    Returns a list of candidate product dicts.
    """
    candidates = []

    # Common price patterns
    price_patterns = [
        r'[\$£€₹]\s*\d+[\d,]*\.?\d*',
        r'\d+[\d,]*\.?\d*\s*[\$£€₹]',
        r'(?:USD|INR|EUR|GBP)\s*\d+[\d,]*\.?\d*',
        r'Rs\.?\s*\d+[\d,]*\.?\d*',
    ]
    combined_price_re = re.compile('|'.join(price_patterns))

    # Look for product-like containers
    product_selectors = [
        '[class*="product"]',
        '[class*="item"]',
        '[class*="card"]',
        '[data-product]',
        '[data-item]',
        '[itemtype*="Product"]',
    ]

    for selector in product_selectors:
        elements = soup.select(selector)
        for el in elements[:50]:  # Cap at 50 to avoid huge pages
            text = el.get_text(separator=' ', strip=True)
            if len(text) < 10 or len(text) > 500:
                continue

            price_match = combined_price_re.search(text)
            if price_match:
                # Try to extract a name (first heading or strong element in the container)
                name_el = el.find(['h1', 'h2', 'h3', 'h4', 'h5', 'a', 'strong', 'span'])
                name = name_el.get_text(strip=True) if name_el else text[:60]

                if len(name) > 3:
                    candidates.append({
                        'name': name[:100],
                        'price_text': price_match.group(0),
                        'full_text': text[:300]
                    })

    return candidates


def extract_products_gemini(raw_text, url):
    """
    Pass 2: Use Gemini AI to intelligently extract structured product data.
    This handles diverse HTML structures that BS4 heuristics miss.
    """
    # Truncate to fit context window
    truncated = raw_text[:30000]

    prompt = f"""You are a product data extraction assistant. Analyze this e-commerce website content and extract ALL products you can find.

WEBSITE: {url}

CONTENT:
{truncated}

INSTRUCTIONS:
- Extract every product mentioned with its details
- Return a JSON array of product objects
- Each product object must have these fields:
  - "name": string (product name)
  - "price": number or null (current price as a number, no currency symbols)
  - "currency": string (e.g. "USD", "INR", "EUR", "GBP")
  - "original_price": number or null (original/strike-through price if discounted)
  - "discount": string or null (e.g. "20% OFF", "SALE")
  - "in_stock": boolean or null (true if in stock, false if out of stock, null if unknown)
  - "category": string or null (product category if apparent)
  - "image_url": string or null (URL of product image if found)

- If you cannot determine a field, set it to null
- If no products are found, return an empty array []
- Return ONLY the JSON array, no markdown formatting, no explanations

JSON:"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()

        # Clean up: remove markdown code fences if present
        if text.startswith('```'):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
        text = text.strip()

        products = json.loads(text)
        if isinstance(products, list):
            # Validate and clean
            cleaned = []
            for p in products:
                if isinstance(p, dict) and p.get('name'):
                    cleaned.append({
                        'name': str(p.get('name', ''))[:150],
                        'price': p.get('price'),
                        'currency': str(p.get('currency', 'USD'))[:5],
                        'original_price': p.get('original_price'),
                        'discount': p.get('discount'),
                        'in_stock': p.get('in_stock'),
                        'category': p.get('category'),
                        'image_url': p.get('image_url'),
                    })
            return cleaned
    except json.JSONDecodeError as e:
        print(f"Gemini JSON parse error: {e}")
    except Exception as e:
        print(f"Gemini extraction error: {e}")

    return []


def scrape_competitor(url_or_brand, use_gemini=True):
    """
    Main entry point: scrape a competitor site for products.
    
    Args:
        url_or_brand: URL or brand name to scrape
        use_gemini: If True, use Gemini AI for extraction. If False, use BS4 only (for subsequent crawls).
    
    Returns:
        dict with keys: products, site_title, url, scraped_at, duration_ms, error
    """
    start_time = time.time()
    result = {
        'products': [],
        'site_title': '',
        'url': url_or_brand,
        'scraped_at': None,
        'duration_ms': 0,
        'error': None
    }

    # Detect if input is a brand name or URL
    is_url = url_or_brand.startswith(('http://', 'https://')) or '.' in url_or_brand.split('/')[0]

    actual_url = url_or_brand
    if not is_url:
        print(f"🔍 Searching for brand: {url_or_brand}")
        found_url = search_brand(url_or_brand)
        if found_url:
            actual_url = found_url
            print(f"📍 Found brand URL: {actual_url}")
        else:
            result['error'] = f"Could not find website for brand: {url_or_brand}"
            return result

    try:
        soup, raw_text, title, final_url = fetch_page(actual_url)
        result['site_title'] = title
        result['url'] = final_url

        if use_gemini:
            # Use Gemini AI for maximum accuracy (first crawl)
            print(f"🤖 Using Gemini AI to extract products from: {final_url}")
            products = extract_products_gemini(raw_text, final_url)
        else:
            # BS4 only for subsequent crawls (saves API tokens)
            print(f"🔧 Using BS4 heuristics to extract products from: {final_url}")
            candidates = extract_products_bs4(soup)
            # Convert BS4 candidates to the same format
            products = []
            for c in candidates:
                price_num = None
                price_text = c.get('price_text', '')
                nums = re.findall(r'[\d,]+\.?\d*', price_text)
                if nums:
                    try:
                        price_num = float(nums[0].replace(',', ''))
                    except ValueError:
                        pass

                currency = 'USD'
                if '₹' in price_text or 'Rs' in price_text or 'INR' in price_text:
                    currency = 'INR'
                elif '€' in price_text or 'EUR' in price_text:
                    currency = 'EUR'
                elif '£' in price_text or 'GBP' in price_text:
                    currency = 'GBP'

                products.append({
                    'name': c['name'],
                    'price': price_num,
                    'currency': currency,
                    'original_price': None,
                    'discount': None,
                    'in_stock': None,
                    'category': None,
                    'image_url': None,
                })

        # Deduplicate by name
        seen_names = set()
        unique_products = []
        for p in products:
            name_key = p['name'].lower().strip()
            if name_key not in seen_names and len(name_key) > 2:
                seen_names.add(name_key)
                unique_products.append(p)

        result['products'] = unique_products
        result['scraped_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    except requests.exceptions.Timeout:
        result['error'] = 'Request timed out. The website took too long to respond.'
    except requests.exceptions.ConnectionError:
        result['error'] = 'Could not connect to the URL. Check the address and try again.'
    except requests.exceptions.HTTPError as e:
        result['error'] = f'HTTP Error: {e.response.status_code}'
    except Exception as e:
        print(f"Scrape error: {e}")
        result['error'] = str(e)

    result['duration_ms'] = int((time.time() - start_time) * 1000)
    return result


def compare_crawls(old_products, new_products):
    """
    Compare two crawl results to detect changes.
    
    Returns a dict with:
        - price_drops: products where price decreased
        - price_increases: products where price increased  
        - new_products: products in new but not in old
        - removed_products: products in old but not in new
        - restocked: products that went from out-of-stock to in-stock
        - out_of_stock: products that went from in-stock to out-of-stock
    """
    changes = {
        'price_drops': [],
        'price_increases': [],
        'new_products': [],
        'removed_products': [],
        'restocked': [],
        'out_of_stock': [],
        'total_changes': 0
    }

    # Build lookup by normalized name
    old_map = {}
    for p in old_products:
        key = p['name'].lower().strip()
        old_map[key] = p

    new_map = {}
    for p in new_products:
        key = p['name'].lower().strip()
        new_map[key] = p

    # Detect new and removed products
    old_keys = set(old_map.keys())
    new_keys = set(new_map.keys())

    for key in new_keys - old_keys:
        changes['new_products'].append(new_map[key])

    for key in old_keys - new_keys:
        changes['removed_products'].append(old_map[key])

    # Detect price changes and stock changes for products in both
    for key in old_keys & new_keys:
        old_p = old_map[key]
        new_p = new_map[key]

        old_price = old_p.get('price')
        new_price = new_p.get('price')

        if old_price is not None and new_price is not None:
            if new_price < old_price:
                changes['price_drops'].append({
                    **new_p,
                    'old_price': old_price,
                    'change': round(old_price - new_price, 2),
                    'change_pct': round((old_price - new_price) / old_price * 100, 1)
                })
            elif new_price > old_price:
                changes['price_increases'].append({
                    **new_p,
                    'old_price': old_price,
                    'change': round(new_price - old_price, 2),
                    'change_pct': round((new_price - old_price) / old_price * 100, 1)
                })

        # Stock changes
        old_stock = old_p.get('in_stock')
        new_stock = new_p.get('in_stock')

        if old_stock == False and new_stock == True:
            changes['restocked'].append(new_p)
        elif old_stock == True and new_stock == False:
            changes['out_of_stock'].append(new_p)

    changes['total_changes'] = (
        len(changes['price_drops']) +
        len(changes['price_increases']) +
        len(changes['new_products']) +
        len(changes['removed_products']) +
        len(changes['restocked']) +
        len(changes['out_of_stock'])
    )

    return changes


def generate_change_summary(competitor_name, changes):
    """Generate a human-readable summary of changes."""
    parts = []

    if changes['price_drops']:
        n = len(changes['price_drops'])
        parts.append(f"🔻 {n} product{'s' if n > 1 else ''} dropped in price")

    if changes['price_increases']:
        n = len(changes['price_increases'])
        parts.append(f"🔺 {n} product{'s' if n > 1 else ''} increased in price")

    if changes['new_products']:
        n = len(changes['new_products'])
        parts.append(f"🆕 {n} new product{'s' if n > 1 else ''} added")

    if changes['removed_products']:
        n = len(changes['removed_products'])
        parts.append(f"❌ {n} product{'s' if n > 1 else ''} removed")

    if changes['restocked']:
        n = len(changes['restocked'])
        parts.append(f"📦 {n} product{'s' if n > 1 else ''} restocked")

    if changes['out_of_stock']:
        n = len(changes['out_of_stock'])
        parts.append(f"⚠️ {n} product{'s' if n > 1 else ''} went out of stock")

    if not parts:
        return f"No changes detected for {competitor_name}"

    return f"{competitor_name}: " + ", ".join(parts)
