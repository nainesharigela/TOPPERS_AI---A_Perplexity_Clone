import google.generativeai as genai
import PyPDF2
from flask import Flask, request, jsonify, Response, stream_with_context, send_from_directory
from flask_cors import CORS
import os
from dotenv import load_dotenv
import time
import sys
import re
import requests
from bs4 import BeautifulSoup
import html2text
from ddgs import DDGS
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables
load_dotenv()

# Configure API key (DO THIS BEFORE importing BI modules that use genai at top-level)
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("⚠️  Warning: GEMINI_API_KEY not found in .env file.")
else:
    genai.configure(api_key=API_KEY)

# Business Intelligence modules
import db
import scraper
import trends_scraper
import scheduler as bi_scheduler

# Force UTF-8 encoding for Windows consoles to avoid 'charmap' errors
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass # Older python versions

# Get the directory where app.py lives
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Global error handlers
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify(error="API endpoint not found", path=request.path), 404
    return send_from_directory(BASE_DIR, 'index.html'), 200

@app.errorhandler(500)
def server_error(e):
    return jsonify(error="Internal server error", message=str(e)), 500

# Create models
# Note: gemini-2.5-flash is excellent for documents/vision
model = genai.GenerativeModel('gemini-2.5-flash')

# Global document store for tracking the current uploaded file
doc_store = {
    'file': None,
    'filename': None,
    'text_content': None,
    'web_content': None,
    'web_url': None,
    'web_title': None
}

# Simple in-memory rate limiting store: {ip: [timestamps]}
rate_limit_store = {}

def is_rate_limited(ip, limit=5, window=60):
    """Check if the given IP has exceeded the request limit within the time window (seconds)."""
    now = time.time()
    if ip not in rate_limit_store:
        rate_limit_store[ip] = []
    
    # Remove timestamps older than the window
    rate_limit_store[ip] = [t for t in rate_limit_store[ip] if now - t < window]
    
    if len(rate_limit_store[ip]) >= limit:
        return True
    
    # Record the timestamp of this request
    rate_limit_store[ip].append(now)
    return False

def extract_local_text(path):
    """Attempt to extract text from a PDF locally for instant indexing."""
    try:
        with open(path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text.strip()
    except Exception as e:
        print(f"Local extraction failure: {e}")
        return ""

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'ok', 'message': 'TOPPERS AI Backend (Vision-Enabled) is running'})

@app.route('/api/clear', methods=['POST'])
def clear_doc():
    doc_store['file'] = None
    doc_store['filename'] = None
    doc_store['text_content'] = None
    doc_store['web_content'] = None
    doc_store['web_url'] = None
    doc_store['web_title'] = None
    return jsonify({'status': 'cleared'})

@app.route('/api/crawl', methods=['POST'])
def crawl_url():
    """Crawl a URL and extract clean text/markdown content."""
    data = request.json
    if not data or 'url' not in data:
        return jsonify({'error': 'No URL provided.'}), 400

    url = data['url'].strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        # Fetch the page with a real browser user-agent
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Extract page title
        title = url
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Remove noise: scripts, styles, nav, footer, ads
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript', 'iframe']):
            tag.decompose()

        # Convert to clean markdown
        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.ignore_emphasis = False
        converter.body_width = 0  # Don't wrap lines
        markdown = converter.handle(str(soup))

        if not markdown or len(markdown.strip()) < 50:
            return jsonify({'error': 'Page has too little extractable content.'}), 400

        # Truncate to ~50k chars to stay within Gemini context limits
        content = markdown[:50000]

        doc_store['web_content'] = content
        doc_store['web_url'] = url
        doc_store['web_title'] = title

        print(f"[WEB CRAWL] Successfully crawled: {url} ({len(content)} chars)")

        return jsonify({
            'status': 'ready',
            'title': title,
            'url': url,
            'length': len(content)
        })

    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request timed out. The website took too long to respond.'}), 408
    except requests.exceptions.ConnectionError:
        return jsonify({'error': 'Could not connect to the URL. Check the address and try again.'}), 400
    except requests.exceptions.HTTPError as e:
        return jsonify({'error': f'HTTP Error: {e.response.status_code}'}), 400
    except Exception as e:
        print(f"Crawl Error: {e}")
        return jsonify({'error': f'Failed to crawl URL: {str(e)}'}), 500

@app.route('/api/clear-web', methods=['POST'])
def clear_web():
    """Clear only the web crawl context."""
    doc_store['web_content'] = None
    doc_store['web_url'] = None
    doc_store['web_title'] = None
    return jsonify({'status': 'cleared'})

@app.route('/api/upload', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '' or not file.filename.endswith('.pdf'):
        return jsonify({'error': 'No PDF selected'}), 400

    temp_path = os.path.join(BASE_DIR, file.filename)
    try:
        # Save file to temp path
        file.save(temp_path)
        
        # Step 1: Try Local Text Extraction (Near Instant)
        print(f"Attempting local extraction for \"{file.filename}\"...")
        extracted_text = extract_local_text(temp_path)
        
        if extracted_text and len(extracted_text) > 50: # Ensure we got more than just meta/junk
            print(f"[SUCCESS] Local indexing successful ({len(extracted_text)} chars).")
            doc_store['text_content'] = extracted_text
            doc_store['file'] = None
            doc_store['filename'] = file.filename
            
            if os.path.exists(temp_path): os.remove(temp_path)
            return jsonify({
                'message': f'Document "{file.filename}" indexed instantly.',
                'status': 'ready',
                'mode': 'local'
            })

        # Step 2: Fallback to Gemini Files API (Vision/OCR Mode)
        print(f"Local extraction failed or yielded no text. Using Gemini Vision Fallback...")
        uploaded_file = genai.upload_file(path=temp_path, display_name=file.filename)
        
        # Faster Poll Interval (1.0s instead of 2s)
        while uploaded_file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(1.0) 
            uploaded_file = genai.get_file(uploaded_file.name)
        
        if uploaded_file.state.name == "FAILED":
            raise Exception("Vision indexing failed.")

        print(f"\n[SUCCESS] Vision indexing successful: {uploaded_file.uri}")
        doc_store['file'] = uploaded_file
        doc_store['text_content'] = None
        doc_store['filename'] = file.filename
        
        if os.path.exists(temp_path): os.remove(temp_path)
        return jsonify({
            'message': f'Document "{file.filename}" processed using Vision OCR.',
            'status': 'ready',
            'mode': 'vision'
        })
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        print(f"Index Error: {e}")
        return jsonify({'error': str(e)}), 500

def scrape_url(url):
    """Helper function to fetch and markdown-ify a single URL."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        resp = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.title.string.strip() if soup.title and soup.title.string else url

        # Remove noise
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript', 'iframe']):
            tag.decompose()

        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.ignore_emphasis = False
        converter.body_width = 0
        markdown = converter.handle(str(soup))

        # We'll take up to 6000 chars per source to keep the total prompt under limits
        content = markdown.strip()[:6000]
        if len(content) < 50:
            return None
        
        return {'url': url, 'title': title, 'content': content}
    except Exception as e:
        print(f"Scrape error for {url}: {e}")
        return None

@app.route('/api/chat', methods=['POST'])
def chat():
    # Enforce rate limit: 5 messages per minute
    if is_rate_limited(request.remote_addr, limit=5, window=60):
        print(f"🚫 [RATE LIMIT] Blocking request from {request.remote_addr}")
        return jsonify({
            'error': 'Rate limit exceeded. You can only send 5 messages per minute to conserve API tokens. Please wait a moment.'
        }), 429

    data = request.json
    if not data or 'prompt' not in data:
        return jsonify({'error': 'No prompt provided.'}), 400
    
    user_prompt = data.get('prompt', '')
    history = data.get('history', []) # Expecting list of {role, parts}
    webSearch = data.get('webSearch', False) # True means Auto Web Search
    
    # Process history for Gemini format (Gemini uses 'model' instead of 'ai')
    formatted_history = []
    for h in history:
        # Avoid including the same file in every history turn to save tokens/complexity
        # The file is passed in the content_payload if it's the current context.
        formatted_history.append({
            'role': 'user' if h['role'] == 'user' else 'model',
            'parts': [h['parts']] if isinstance(h['parts'], str) else h['parts']
        })

    @stream_with_context
    def generate_events():
        try:
            # Start chat with history
            chat_session = model.start_chat(history=formatted_history)
            content_payload = [user_prompt]
            
            # --- AUTO WEB SEARCH TRIGGER ---
            if webSearch:
                print(f"🔍 Auto Web Search started for: '{user_prompt}'")
                try:
                    ddgs = DDGS()
                    # Grab top 4 results
                    search_results = list(ddgs.text(user_prompt, max_results=4))
                    
                    # Fallback to Wikipedia if DuckDuckGo blocks the scraper
                    if not search_results:
                        print("DuckDuckGo returned empty. Falling back to Wikipedia API...")
                        import urllib.parse
                        query = urllib.parse.quote(user_prompt)
                        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                        wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&utf8=&format=json&srlimit=4"
                        resp = requests.get(wiki_url, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            search_hits = data.get('query', {}).get('search', [])
                            if search_hits:
                                search_results = []
                                for hit in search_hits:
                                    title = hit['title']
                                    link = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                                    search_results.append({'href': link})
                                print(f"Fallback extracted {len(search_results)} links from Wikipedia.")
                    
                    if search_results:
                        urls = [res['href'] for res in search_results]
                        valid_sources = []
                        
                        # Concurrently scrape the URLs
                        with ThreadPoolExecutor(max_workers=4) as executor:
                            future_to_url = {executor.submit(scrape_url, url): url for url in urls}
                            for future in as_completed(future_to_url):
                                res = future.result()
                                if res:
                                    valid_sources.append(res)
                        
                        if valid_sources:
                            # 1. Yield the sources metadata down the stream FIRST so frontend can render Source Cards
                            sources_meta = [{"title": s['title'], "url": s['url']} for s in valid_sources]
                            yield f"data: {json.dumps({'sources': sources_meta})}\n\n"
                            
                            # 2. Compile the full text block for Gemini
                            web_text_block = "WEB SEARCH RESULTS to help answer the user's prompt:\n\n"
                            for i, s in enumerate(valid_sources):
                                web_text_block += f"--- Source [{i+1}]: {s['title']} ({s['url']}) ---\n"
                                web_text_block += f"{s['content']}\n\n"
                            
                            web_text_block += "INSTRUCTIONS: You must use the provided web search results to answer the user's prompt truthfully and accurately. ALWAYS cite your sources inline using [1], [2], etc.\n"
                            content_payload.insert(0, web_text_block)
                            print(f"✅ Successfully compiled {len(valid_sources)} web sources for the prompt.")
                except Exception as e:
                    print(f"Web Search Engine failed: {e}")
                    # Allow it to silently fallback to Gemini base logic
                    pass

            # 1. Text context from local indexing
            if doc_store.get('text_content'):
                content_payload.insert(0, f"DOCUMENT CONTEXT (Internal Access Only):\n{doc_store['text_content']}\n---")
                print(f"Chatting with local text context: {doc_store['filename']}")

            # 2. File context from Vision Fallback
            if doc_store.get('file'):
                content_payload.insert(0, doc_store['file'])
                print(f"Chatting with file vision context: {doc_store['filename']}")

            # 3. Handle manual web URL context (Single manual URL paste)
            if doc_store.get('web_content') and not webSearch:
                content_payload.insert(0, f"WEB PAGE CONTEXT (from {doc_store['web_url']}):\n{doc_store['web_content']}\n---")
                print(f"Chatting with manually pasted web context: {doc_store['web_url']}")

            response = chat_session.send_message(content_payload, stream=True)
            for chunk in response:
                if chunk.text:
                    yield f"data: {json.dumps({'text': chunk.text})}\n\n"
        except Exception as e:
            print(f"Chat Error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate_events(), mimetype='text/event-stream')

# ============================================================
#  BUSINESS INTELLIGENCE API ENDPOINTS
# ============================================================

@app.route('/api/bi/track', methods=['POST'])
def bi_track_competitor():
    """Add a competitor by URL or brand name and trigger first crawl."""
    data = request.json
    if not data or (not data.get('url') and not data.get('brand')):
        return jsonify({'error': 'Provide a URL or brand name.'}), 400

    url_or_brand = data.get('url', '').strip() or data.get('brand', '').strip()

    try:
        # Scrape the competitor (first crawl uses Gemini for accuracy)
        result = scraper.scrape_competitor(url_or_brand, use_gemini=True)

        if result['error']:
            return jsonify({'error': result['error']}), 400

        # Build favicon URL
        try:
            from urllib.parse import urlparse
            domain = urlparse(result['url']).hostname or ''
            favicon = f"https://www.google.com/s2/favicons?domain={domain}&sz=32"
        except:
            favicon = None

        # Save competitor to database
        comp = db.add_competitor(result['site_title'], result['url'], favicon)

        # Save crawl result
        crawl_id = db.save_crawl(comp['id'], result['products'], result['duration_ms'])

        return jsonify({
            'competitor': comp,
            'products': result['products'],
            'product_count': len(result['products']),
            'crawl_id': crawl_id,
            'duration_ms': result['duration_ms']
        })

    except Exception as e:
        print(f"Track competitor error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/bi/competitors', methods=['GET'])
def bi_list_competitors():
    """List all tracked competitors."""
    competitors = db.get_all_competitors()
    return jsonify({'competitors': competitors})


@app.route('/api/bi/competitors/<int:comp_id>', methods=['DELETE'])
def bi_delete_competitor(comp_id):
    """Remove a tracked competitor."""
    db.delete_competitor(comp_id)
    return jsonify({'status': 'deleted', 'id': comp_id})


@app.route('/api/bi/crawl/<int:comp_id>', methods=['POST'])
def bi_recrawl(comp_id):
    """Trigger a manual re-crawl of a competitor."""
    comp = db.get_competitor(comp_id)
    if not comp:
        return jsonify({'error': 'Competitor not found.'}), 404

    try:
        # Re-crawls use BS4 only to save API tokens (per user preference)
        result = scraper.scrape_competitor(comp['url'], use_gemini=False)

        if result['error']:
            db.save_crawl(comp_id, [], result['duration_ms'], 'error', result['error'])
            return jsonify({'error': result['error']}), 400

        # Get previous crawl for comparison
        prev_crawl = db.get_latest_crawl(comp_id)

        # Save new crawl
        crawl_id = db.save_crawl(comp_id, result['products'], result['duration_ms'])

        # Detect changes
        changes = None
        if prev_crawl:
            changes = scraper.compare_crawls(prev_crawl['products'], result['products'])
            if changes['total_changes'] > 0:
                summary = scraper.generate_change_summary(comp['name'], changes)
                db.save_report(comp_id, comp['name'], summary, changes)

        return jsonify({
            'products': result['products'],
            'product_count': len(result['products']),
            'crawl_id': crawl_id,
            'duration_ms': result['duration_ms'],
            'changes': changes
        })

    except Exception as e:
        print(f"Re-crawl error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/bi/products/<int:comp_id>', methods=['GET'])
def bi_get_products(comp_id):
    """Get latest products for a competitor."""
    crawl = db.get_latest_crawl(comp_id)
    if not crawl:
        return jsonify({'products': [], 'message': 'No crawl data yet.'})

    # Also get previous crawl for change indicators
    prev = db.get_previous_crawl(comp_id)
    changes = None
    if prev:
        changes = scraper.compare_crawls(prev['products'], crawl['products'])

    return jsonify({
        'products': crawl['products'],
        'product_count': crawl['product_count'],
        'crawled_at': crawl['crawled_at'],
        'changes': changes
    })


@app.route('/api/bi/history/<int:comp_id>', methods=['GET'])
def bi_crawl_history(comp_id):
    """Get crawl history for a competitor."""
    history = db.get_crawl_history(comp_id)
    return jsonify({'history': history})


@app.route('/api/bi/schedule', methods=['POST'])
def bi_create_schedule():
    """Create or update a crawl schedule."""
    data = request.json
    if not data or not data.get('competitor_id'):
        return jsonify({'error': 'competitor_id is required.'}), 400

    comp_id = data['competitor_id']
    frequency = data.get('frequency', 'daily')

    if frequency not in ('daily', 'weekly'):
        return jsonify({'error': 'Frequency must be daily or weekly.'}), 400

    db.add_schedule(comp_id, frequency)
    return jsonify({'status': 'scheduled', 'competitor_id': comp_id, 'frequency': frequency})


@app.route('/api/bi/schedule/<int:comp_id>', methods=['DELETE'])
def bi_delete_schedule(comp_id):
    """Remove a schedule."""
    db.remove_schedule(comp_id)
    return jsonify({'status': 'unscheduled', 'competitor_id': comp_id})


@app.route('/api/bi/schedules', methods=['GET'])
def bi_list_schedules():
    """List all active schedules."""
    schedules = db.get_all_schedules()
    return jsonify({'schedules': schedules})


@app.route('/api/bi/reports', methods=['GET'])
def bi_list_reports():
    """Get all change reports."""
    reports = db.get_all_reports()
    return jsonify({'reports': reports})


@app.route('/api/bi/reports/<int:report_id>', methods=['GET'])
def bi_get_report(report_id):
    """Get a specific report."""
    report = db.get_report(report_id)
    if not report:
        return jsonify({'error': 'Report not found.'}), 404
    return jsonify({'report': report})


@app.route('/api/bi/analyze', methods=['POST'])
def bi_analyze():
    """Ask an AI follow-up question about competitor data."""
    data = request.json
    if not data or not data.get('question'):
        return jsonify({'error': 'question is required.'}), 400

    comp_id = data.get('competitor_id')
    question = data['question']

    # Build context from latest crawl
    context = ""
    if comp_id:
        crawl = db.get_latest_crawl(comp_id)
        comp = db.get_competitor(comp_id)
        if crawl:
            products = crawl['products']
            context = f"COMPETITOR DATA for {comp['name']} ({comp['url']}):\n"
            context += f"Crawled at: {crawl['crawled_at']}\n"
            context += f"Products ({len(products)} items):\n"
            for i, p in enumerate(products, 1):
                line = f"  {i}. {p['name']}"
                if p.get('price') is not None:
                    line += f" - {p.get('currency', '$')}{p['price']}"
                if p.get('original_price'):
                    line += f" (was {p.get('currency', '$')}{p['original_price']})"
                if p.get('discount'):
                    line += f" [{p['discount']}]"
                if p.get('in_stock') is not None:
                    line += f" {'(In Stock)' if p['in_stock'] else '(Out of Stock)'}"
                context += line + "\n"
    else:
        # No specific competitor — gather all competitor data
        all_comps = db.get_all_competitors()
        for comp in all_comps:
            crawl = db.get_latest_crawl(comp['id'])
            if crawl:
                context += f"\n--- {comp['name']} ({comp['url']}) ---\n"
                for i, p in enumerate(crawl['products'], 1):
                    line = f"  {i}. {p['name']}"
                    if p.get('price') is not None:
                        line += f" - {p.get('currency', '$')}{p['price']}"
                    context += line + "\n"

    if not context:
        return jsonify({'error': 'No competitor data available. Track a competitor first.'}), 400

    try:
        prompt = f"{context}\n\nUSER QUESTION: {question}\n\nAnswer the question based on the competitor data above. Be specific with numbers and product names."
        response = model.generate_content(prompt)
        return jsonify({'answer': response.text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================
#  MARKET TREND INTELLIGENCE API ENDPOINTS
# ============================================================

@app.route('/api/bi/trends/analyze', methods=['POST'])
def bi_trends_analyze():
    data = request.json
    if not data or not data.get('topic'):
        return jsonify({'error': 'topic is required.'}), 400

    topic = data['topic'].strip()
    
    try:
        # Run trends
        result = trends_scraper.run_trend_analysis(topic)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
            
        # Save to DB
        report_id = db.save_trend_report(
            topic,
            result['sentiment_score'],
            result['keywords'],
            result['competitor_mentions'],
            result['summary'],
            result['raw_context']
        )
        
        return jsonify({
            'report_id': report_id,
            'topic': topic,
            'sentiment_score': result['sentiment_score'],
            'keywords': result['keywords'],
            'competitor_mentions': result['competitor_mentions'],
            'summary': result['summary']
        })
    except Exception as e:
        print(f"Trend analyze error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bi/trends/history', methods=['GET'])
def bi_trends_history():
    history = db.get_trend_history()
    return jsonify({'history': history})

@app.route('/api/bi/trends/chat', methods=['POST'])
def bi_trends_chat():
    data = request.json
    if not data or not data.get('question') or not data.get('report_id'):
        return jsonify({'error': 'question and report_id are required.'}), 400
        
    report = db.get_trend_report(data['report_id'])
    if not report:
        return jsonify({'error': 'Report not found.'}), 404
        
    question = data['question']
    context = report.get('raw_context', '')
    
    prompt = f"MARKET TREND CONTEXT FOR: {report['topic']}\n\n{context}\n\nUSER QUESTION: {question}\n\nAnswer the user's question explicitly using the context provided. If the context doesn't have the answer, say you don't know."
    
    try:
        response = model.generate_content(prompt)
        return jsonify({'answer': response.text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================
#  STATIC FILES & STARTUP
# ============================================================

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(BASE_DIR, filename)

if __name__ == '__main__':
    # Initialize the background scheduler for recurring crawls
    bi_scheduler.init_scheduler()
    print(f"TOPPERS AI Backend - Multimodal PDF Vision + BI Ready")
    app.run(host='0.0.0.0', port=5001, debug=True, threaded=True, use_reloader=False)
