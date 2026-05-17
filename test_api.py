import httpx
import json

r = httpx.get("http://127.0.0.1:8001/news?limit=10")
data = r.json()

print("=== SECTOR CLASSIFICATION RESULTS ===\n")
for s in data["top_stories"]:
    headline = s["headline"][:65]
    sectors = s["sectors"]
    print(f"  {headline}")
    print(f"    -> Sectors: {sectors}\n")

print("=== SECTOR GROUPING ===\n")
for sector_name, stories in data["sectors"].items():
    print(f"  [{sector_name}] — {len(stories)} stories")
