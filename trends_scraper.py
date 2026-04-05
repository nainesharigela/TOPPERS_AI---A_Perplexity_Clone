import sys
import json
import re
import os
import requests
from bs4 import BeautifulSoup
import html2text
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import google.generativeai as genai

# Force UTF-8 for Windows console
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        os.environ["PYTHONIOENCODING"] = "utf-8"

# Try importing the new 'ddgs' package first, fallback to old 'duckduckgo_search'
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

# Reuse the configured Gemini model
model = genai.GenerativeModel('gemini-2.5-flash')

SCRAPE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

# Skip URLs that are not useful for text scraping
SKIP_DOMAINS = ['youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com', 'facebook.com', 'twitter.com', 'x.com', 'pinterest.com']

def should_skip_url(url):
    """Check if a URL should be skipped (video/social media sites with no scrapeable text)."""
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).hostname or ''
        domain = domain.replace('www.', '')
        return any(skip in domain for skip in SKIP_DOMAINS)
    except Exception:
        return False

def extract_text_from_url(url):
    """Fetch and return max 8000 chars of site text."""
    if should_skip_url(url):
        print(f"  [SKIP] Non-scrapeable URL: {url}")
        return ""
    try:
        resp = requests.get(url, headers=SCRAPE_HEADERS, timeout=10, allow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Remove noise
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript']):
            tag.decompose()

        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.body_width = 0
        text = converter.handle(str(soup)).strip()
        
        print(f"  [OK] Scraped {len(text)} chars from {url[:60]}")
        return text[:8000] if text else ""
    except Exception as e:
        print(f"  [FAIL] Scrape error for {url}: {e}")
        return ""

def search_with_ddgs(query, max_results=5):
    """Search using DDGS and return URLs."""
    try:
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=max_results))
        return [r['href'] for r in results if r.get('href')]
    except Exception as e:
        print(f"  DDGS search error for '{query}': {e}")
        return []

def search_with_wikipedia(query, max_results=3):
    """Fallback search using Wikipedia API."""
    try:
        import urllib.parse
        encoded = urllib.parse.quote(query)
        url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded}&utf8=&format=json&srlimit={max_results}"
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            hits = data.get('query', {}).get('search', [])
            urls = []
            for hit in hits:
                title = hit['title']
                link = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                urls.append(link)
            return urls
    except Exception as e:
        print(f"  Wikipedia fallback error: {e}")
    return []

def run_trend_analysis(topic):
    """Main pipeline for gathering trend intel and analyzing it."""
    queries = [
        f"{topic} reviews reddit",
        f"{topic} latest news 2024 2025",
        f"best {topic} products discussion forum",
        f"{topic} consumer opinions",
        f"{topic} market trends analysis"
    ]
    
    unique_urls = set()
    
    print(f"[TRENDS] Searching trends for: {topic}")
    
    # Run multiple searches to gather distinct URLs
    for q in queries:
        urls = search_with_ddgs(q, max_results=5)
        print(f"  Query '{q[:40]}...' -> {len(urls)} results")
        for url in urls:
            if not should_skip_url(url):
                unique_urls.add(url)
            
    # If DDG returned very few usable URLs, try Wikipedia as fallback
    if len(unique_urls) < 3:
        print(f"  [FALLBACK] Only {len(unique_urls)} URLs, trying Wikipedia...")
        wiki_urls = search_with_wikipedia(topic, max_results=3)
        unique_urls.update(wiki_urls)
    
    urls = list(unique_urls)[:10]  # max 10 URLs
    print(f"[TRENDS] {len(urls)} scrapeable URLs found for '{topic}'")
    
    if len(urls) == 0:
        return {
            "error": "Could not find any relevant web results for this topic. Please try a different search term.",
            "raw_context": ""
        }
    
    raw_context = f"MARKET TRENDS FOR TOPIC: {topic}\n\n"
    
    # Scrape URLs concurrently
    scraped_count = 0
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_url = {executor.submit(extract_text_from_url, url): url for url in urls}
        for idx, future in enumerate(as_completed(future_to_url)):
            url = future_to_url[future]
            try:
                text = future.result()
                if text and len(text) > 100:
                    raw_context += f"--- SOURCE [{idx+1}]: {url} ---\n{text}\n\n"
                    scraped_count += 1
            except Exception as e:
                print(f"  [ERROR] Future failed for {url}: {e}")
    
    print(f"[TRENDS] Successfully scraped {scraped_count} sources ({len(raw_context)} chars total)")
                
    if scraped_count == 0 or len(raw_context) < 400:
        return {
            "error": "Could not extract enough content from web sources. Try a more specific or popular topic.",
            "raw_context": raw_context
        }
        
    print(f"[TRENDS] Sending {len(raw_context)} characters to Gemini for analysis...")
    
    # Truncate context if necessary to fit within limits safely
    raw_context = raw_context[:40000]
    
    prompt = f"""You are an elite Market Research Analyst. I am providing you with fresh discussions, reviews, and news scraped from the web about: {topic}.

CONTEXT:
{raw_context}

INSTRUCTIONS:
Extract the following information and return ONLY a valid JSON object. 
1. sentiment_score: An integer from 0 (very negative) to 100 (very positive) reflecting the overall tone.
2. keywords: Array of max 6 short thematic keywords (e.g., ["lightweight", "expensive", "durable"]).
3. competitor_mentions: Array of objects. Each object should have 'brand' (name) and 'insight' (short 1-sentence note of what people are saying, e.g. "Praised for comfort but pricey"). Only include up to 5 main brands.
4. summary: A short, punchy 3-4 sentence markdown summary outlining the rising trends, general consensus, and notable shifts.

JSON STRUCTURE:
{{
  "sentiment_score": 85,
  "keywords": ["tag1", "tag2"],
  "competitor_mentions": [{{"brand": "X", "insight": "they say Y"}}],
  "summary": "**Market is shifting.**..."
}}
"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Clean markdown wrappers if returned
        if text.startswith('```'):
            text = re.sub(r'^```(json)?\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
        
        data = json.loads(text.strip())
        
        return {
            "sentiment_score": data.get("sentiment_score", 50),
            "keywords": data.get("keywords", []),
            "competitor_mentions": data.get("competitor_mentions", []),
            "summary": data.get("summary", "No clear summary could be generated."),
            "raw_context": raw_context
        }
    except json.JSONDecodeError as e:
        print(f"[TRENDS] JSON parse error: {e}")
        return {"error": "Failed to parse AI response into structured format.", "raw_context": raw_context}
    except Exception as e:
        print(f"[TRENDS] Gemini error: {e}")
        return {"error": str(e), "raw_context": raw_context}
