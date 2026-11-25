import os, sqlite3, json, requests, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

url = os.getenv("SUPABASE_URL", "").rstrip("/")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=representation"
}

conn = sqlite3.connect(BASE_DIR / 'agrotech.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=== 1. SYNCING USERS ===")
cur.execute("SELECT * FROM users")
users = [dict(r) for r in cur.fetchall()]
for u in users:
    r = requests.post(f"{url}/rest/v1/users", headers=headers, json=u)
    print(f"User {u['email']}: {r.status_code}")

print("\n=== 2. SYNCING SERVICES ===")
cur.execute("SELECT * FROM services")
services = [dict(r) for r in cur.fetchall()]
for s in services:
    s['available'] = bool(s.get('available', 1))
    r = requests.post(f"{url}/rest/v1/services", headers=headers, json=s)
    print(f"Service {s['id']} - {s['name']}: {r.status_code}")

print("\n=== 3. SYNCING SERVICE REQUESTS ===")
cur.execute("SELECT * FROM service_requests")
reqs = [dict(r) for r in cur.fetchall()]
for req in reqs:
    r = requests.post(f"{url}/rest/v1/service_requests", headers=headers, json=req)
    print(f"Request {req['request_id']}: {r.status_code}")

print("\n=== 4. SYNCING ALERTS ===")
cur.execute("SELECT * FROM alerts")
alerts = [dict(r) for r in cur.fetchall()]
user_ids = {u['id'] for u in users}
for a in alerts:
    a['is_read'] = bool(a.get('is_read', 0))
    if a.get('created_by') not in user_ids:
        a['created_by'] = None
    if a.get('user_id') not in user_ids:
        a['user_id'] = None
    r = requests.post(f"{url}/rest/v1/alerts", headers=headers, json=a)
    print(f"Alert {a['id']}: {r.status_code}")

print("\n=== 5. SYNCING COMPLAINTS ===")
cur.execute("SELECT * FROM complaints")
comps = [dict(r) for r in cur.fetchall()]
for c in comps:
    if c.get('user_id') not in user_ids:
        c['user_id'] = None
    r = requests.post(f"{url}/rest/v1/complaints", headers=headers, json=c)
    print(f"Complaint {c['id']}: {r.status_code}")

conn.close()
print("\n=== SYNC COMPLETE ===")
