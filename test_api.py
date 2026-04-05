import google.generativeai as genai
import os
import time
import sys
from dotenv import load_dotenv
load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

print("=== TIMED GEMINI 2.5 FLASH TEST ===")
start = time.time()
print(f"[{0:.2f}s] Sending request...")

response = model.generate_content("Say hello in one sentence.", stream=True)

first_chunk = True
for chunk in response:
    now = time.time() - start
    if chunk.text:
        if first_chunk:
            print(f"[{now:.2f}s] FIRST TOKEN arrived! (Time to first token: {now:.2f}s)")
            first_chunk = False
        print(f"[{now:.2f}s] CHUNK: {chunk.text[:60]}")
        sys.stdout.flush()

elapsed = time.time() - start
print(f"\n=== TOTAL TIME: {elapsed:.2f}s ===")
