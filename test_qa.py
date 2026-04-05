import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
import json
import time

BASE_URL = 'http://127.0.0.1:5001'

def print_result(name, passed, msg=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} | {name}: {msg}")

def test_health():
    try:
        r = requests.get(f"{BASE_URL}/api/health")
        passed = r.status_code == 200
        print_result("Health Check", passed, f"Status {r.status_code}")
    except Exception as e:
        print_result("Health Check", False, str(e))

def test_chat_web_search():
    payload = {
        "prompt": "What is the current version of Python?",
        "history": [],
        "webSearch": True
    }
    try:
        r = requests.post(f"{BASE_URL}/api/chat", json=payload, stream=True)
        res_text = ""
        for line in r.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith('data: '):
                    try:
                        data = json.loads(decoded[6:])
                        if 'text' in data:
                            res_text += data['text']
                        if 'sources' in data:
                            passed = len(data['sources']) > 0
                    except:
                        pass
        passed = len(res_text) > 20
        print_result("Web Search Chat", passed, f"Response length: {len(res_text)}, text: {res_text[:50]}...")
    except Exception as e:
        print_result("Web Search Chat", False, str(e))

def test_file_upload():
    try:
        # App.py expects a .pdf file, so we give it a .pdf filename (even if text inside)
        files = {'file': ('test.pdf', b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n', 'application/pdf')}
        r = requests.post(f"{BASE_URL}/api/upload", files=files)
        passed = r.status_code == 200 and r.json().get('success')
        print_result("File Upload", passed, f"Status: {r.status_code}, JSON: {r.text}")
        
        if passed:
            payload = {
                "prompt": "What is Project Alpha?",
                "history": [],
                "webSearch": False
            }
            r2 = requests.post(f"{BASE_URL}/api/chat", json=payload, stream=True)
            passed2 = r2.status_code == 200
            print_result("File Q&A", passed2, f"Status {r2.status_code}")
    except Exception as e:
        print_result("File Upload", False, str(e))

def test_competitor_tracker():
    payload = {"brand": "nikeshoes"}
    try:
        r = requests.post(f"{BASE_URL}/api/bi/track", json=payload)
        passed = r.status_code == 200 and 'competitor' in r.json()
        print_result("Competitor Tracking", passed, f"Status: {r.status_code}")
        
        if passed:
            comp_id = r.json()['id']
            payload2 = {"competitor_id": comp_id, "question": "What is the cheapest shoe?"}
            r2 = requests.post(f"{BASE_URL}/api/bi/analyze", json=payload2)
            passed2 = r2.status_code == 200 and 'answer' in r2.json()
            print_result("Competitor Ask AI", passed2, f"Status: {r2.status_code}")
    except Exception as e:
        print_result("Competitor Tracking", False, str(e))

def test_trends():
    payload = {"topic": "skincare"}
    try:
        r = requests.post(f"{BASE_URL}/api/bi/trends/analyze", json=payload)
        passed = r.status_code == 200 and 'report_id' in r.json()
        print_result("Market Trends Search", passed, f"Status: {r.status_code}, JSON: {r.text[:200]}")
        
        if passed:
            report_id = r.json()['report_id']
            payload2 = {"report_id": report_id, "question": "Are they noisy?"}
            r2 = requests.post(f"{BASE_URL}/api/bi/trends/chat", json=payload2)
            passed2 = r2.status_code == 200 and 'answer' in r2.json()
            print_result("Market Trends Ask AI", passed2, f"Status: {r2.status_code}")
    except Exception as e:
        print_result("Market Trends Search", False, str(e))

if __name__ == "__main__":
    print("--- STARTING QA TESTS ---")
    test_health()
    test_file_upload()
    test_competitor_tracker()
    test_trends()
    test_chat_web_search()
    print("--- QA TESTS DONE ---")
