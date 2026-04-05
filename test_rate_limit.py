import requests
import time

API_URL = "http://127.0.0.1:5001/api/chat"

print("--- TESTING CHAT RATE LIMIT (5/min) ---")

for i in range(1, 8):
    print(f"Request {i}...", end=" ", flush=True)
    try:
        # Use stream=True because it's an event-stream
        response = requests.post(API_URL, json={"prompt": "test", "history": []}, stream=True, timeout=5)
        
        if response.status_code == 200:
            print("OK (200)")
            # Consume a bit of the stream to properly close
            for line in response.iter_lines():
                if line: break 
        elif response.status_code == 429:
            print(f"BLOCK (429): {response.json().get('error')}")
        else:
            print(f"ERR ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"FAILED: {str(e)}")
    
    # Small delay between requests
    time.sleep(0.5)

print("\n--- TEST COMPLETE ---")
