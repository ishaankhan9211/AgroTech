import os
from pathlib import Path
from dotenv import load_dotenv
import requests
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid
import sqlite3

# Load backend/.env
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

class SupabaseClient:
    """Lightweight, resilient Supabase PostgREST client that uses standard requests."""
    def __init__(self, url: str, service_role_key: str):
        self.url = url.rstrip('/')
        self.key = service_role_key
        self.rest_url = f"{self.url}/rest/v1"
        self.session = requests.Session()
        self.session.headers.update({
            'apikey': self.key,
            'Authorization': f'Bearer {self.key}',
            'Content-Type': 'application/json'
        })

        self._last_health_check = 0.0
        self._is_healthy_cached = False

    def is_healthy(self) -> bool:
        import time
        now = time.time()
        if now - getattr(self, '_last_health_check', 0) < 30:
            return getattr(self, '_is_healthy_cached', False)
        try:
            r = self.session.get(f"{self.rest_url}/users?select=id&limit=1", timeout=3)
            self._is_healthy_cached = r.ok
            self._last_health_check = now
            return self._is_healthy_cached
        except Exception:
            self._is_healthy_cached = False
            self._last_health_check = now
            return False

    def select(self, table: str, query: str = "", params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            endpoint = f"{self.rest_url}/{table}"
            if query:
                endpoint = f"{endpoint}?{query}"
            r = self.session.get(endpoint, params=params, timeout=10)
            if r.ok:
                return r.json()
            print(f"[Supabase select] {table} failed ({r.status_code}): {r.text[:200]}")
            return []
        except Exception as ex:
            print(f"[Supabase select error] {table}: {ex}")
            return []

    def insert(self, table: str, data: Any, upsert: bool = False) -> List[Dict[str, Any]]:
        try:
            h = {'Prefer': 'resolution=merge-duplicates,return=representation' if upsert else 'return=representation'}
            r = self.session.post(f"{self.rest_url}/{table}", json=data, headers=h, timeout=10)
            if r.ok:
                return r.json() if r.text else []
            print(f"[Supabase insert] {table} failed ({r.status_code}): {r.text[:200]}")
            return []
        except Exception as ex:
            print(f"[Supabase insert error] {table}: {ex}")
            return []

    def update(self, table: str, data: Dict[str, Any], query: str) -> List[Dict[str, Any]]:
        try:
            h = {'Prefer': 'return=representation'}
            endpoint = f"{self.rest_url}/{table}?{query}"
            r = self.session.patch(endpoint, json=data, headers=h, timeout=10)
            if r.ok:
                return r.json() if r.text else []
            print(f"[Supabase update] {table} failed ({r.status_code}): {r.text[:200]}")
            return []
        except Exception as ex:
            print(f"[Supabase update error] {table}: {ex}")
            return []

    def delete(self, table: str, query: str) -> bool:
        try:
            endpoint = f"{self.rest_url}/{table}?{query}"
            r = self.session.delete(endpoint, timeout=10)
            if r.ok:
                return True
            print(f"[Supabase delete] {table} failed ({r.status_code}): {r.text[:200]}")
            return False
        except Exception as ex:
            print(f"[Supabase delete error] {table}: {ex}")
            return False

# Initialize Client if Environment Variables Exist
SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()

supabase_client: Optional[SupabaseClient] = None
if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and not SUPABASE_URL.startswith('http://localhost'):
    try:
        supabase_client = SupabaseClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        if supabase_client.is_healthy():
            print(f"[AgroTech Supabase] Connected to Cloud Database successfully! ({SUPABASE_URL})")
        else:
            print("[AgroTech Supabase] Notice: Supabase URL reachable but ping failed. Falling back to SQLite.")
    except Exception as exc:
        print(f"[AgroTech Supabase] Init error: {exc}. Using local SQLite database.")
        supabase_client = None

# --- Helper Sync Functions (Safe to run in BackgroundTasks) ---

def sync_user(user_dict: Dict[str, Any]) -> None:
    if not supabase_client: return
    try:
        data = {
            'id': str(user_dict.get('id')),
            'name': user_dict.get('name'),
            'email': user_dict.get('email', '').lower().strip(),
            'phone': user_dict.get('phone', ''),
            'password_hash': user_dict.get('password_hash', ''),
            'location': user_dict.get('location', ''),
            'role': user_dict.get('role', 'farmer'),
            'status': user_dict.get('status', 'active'),
            'created_at': user_dict.get('created_at') or datetime.now(timezone.utc).isoformat()
        }
        res = supabase_client.insert('users', data, upsert=True)
        if res:
            print(f"[AgroTech Supabase] User '{data['email']}' synced to Supabase.")
    except Exception as ex:
        print(f"[AgroTech Supabase] sync_user error: {ex}")

def sync_delete_user(user_id: str) -> None:
    if not supabase_client: return
    try:
        supabase_client.delete('users', f"id=eq.{user_id}")
    except Exception as ex:
        print(f"[AgroTech Supabase] sync_delete_user error: {ex}")

def sync_otp(otp_dict: Dict[str, Any]) -> None:
    if not supabase_client: return
    try:
        data = {
            'email': otp_dict.get('email', '').lower().strip(),
            'name': otp_dict.get('name', ''),
            'phone': otp_dict.get('phone', ''),
            'password_hash': otp_dict.get('password_hash', ''),
            'location': otp_dict.get('location', ''),
            'role': otp_dict.get('role', 'farmer'),
            'otp_code': str(otp_dict.get('otp_code', '')),
            'otp_hash': str(otp_dict.get('otp_hash', '')),
            'expires_at': otp_dict.get('expires_at'),
            'attempts': int(otp_dict.get('attempts', 0))
        }
        res = supabase_client.insert('registration_otps', data, upsert=True)
        if res:
            print(f"[AgroTech Supabase] Registration OTP for '{data['email']}' synced to Supabase.")
    except Exception as ex:
        print(f"[AgroTech Supabase] sync_otp error: {ex}")

def sync_delete_otp(email: str) -> None:
    if not supabase_client: return
    try:
        supabase_client.delete('registration_otps', f"email=eq.{email.lower().strip()}")
    except Exception as ex:
        print(f"[AgroTech Supabase] sync_delete_otp error: {ex}")

def sync_service(service_dict: Dict[str, Any], action: str = 'upsert') -> None:
    if not supabase_client: return
    try:
        s_id = service_dict.get('id')
        if action == 'delete':
            supabase_client.delete('services', f"id=eq.{s_id}")
            print(f"[AgroTech Supabase] Service {s_id} deleted in Supabase.")
            return

        p_by = service_dict.get('posted_by')
        if p_by:
            check = supabase_client.select('users', f"id=eq.{p_by}&select=id")
            if not check:
                p_by = None

        data = {
            'name': service_dict.get('name'),
            'category': service_dict.get('category'),
            'price': float(service_dict.get('price', 0)),
            'unit': service_dict.get('unit', 'per day'),
            'description': service_dict.get('description', ''),
            'location': service_dict.get('location', ''),
            'image': service_dict.get('image', ''),
            'rating': float(service_dict.get('rating', 4.5)),
            'reviews': int(service_dict.get('reviews', 0)),
            'available': bool(service_dict.get('available', True)),
            'status': service_dict.get('status', 'approved'),
            'posted_by': p_by
        }
        if s_id:
            data['id'] = int(s_id)
        res = supabase_client.insert('services', data, upsert=True)
        if res:
            print(f"[AgroTech Supabase] Service '{data['name']}' synced to Supabase.")
    except Exception as ex:
        print(f"[AgroTech Supabase] sync_service error: {ex}")

def sync_service_request(req_dict: Dict[str, Any], action: str = 'upsert') -> None:
    if not supabase_client: return
    try:
        req_id = req_dict.get('request_id')
        if action == 'update_status':
            supabase_client.update('service_requests', {'status': req_dict.get('status')}, f"request_id=eq.{req_id}")
            print(f"[AgroTech Supabase] Request {req_id} status updated in Supabase.")
            return

        f_id = req_dict.get('farmer_id')
        if f_id:
            check = supabase_client.select('users', f"id=eq.{f_id}&select=id")
            if not check: f_id = None
        p_id = req_dict.get('provider_id')
        if p_id:
            check = supabase_client.select('users', f"id=eq.{p_id}&select=id")
            if not check: p_id = None

        data = {
            'request_id': req_id,
            'farmer_id': f_id,
            'farmer_name': req_dict.get('farmer_name', ''),
            'farmer_phone': req_dict.get('farmer_phone', ''),
            'provider_id': p_id,
            'service_id': req_dict.get('service_id'),
            'service_name': req_dict.get('service_name', ''),
            'quantity': int(req_dict.get('quantity', 1)),
            'price': float(req_dict.get('price', 0)),
            'payment_method': req_dict.get('payment_method', 'cod'),
            'payment_status': req_dict.get('payment_status', 'pending'),
            'status': req_dict.get('status', 'pending'),
            'address': req_dict.get('address', ''),
            'notes': req_dict.get('notes', ''),
            'preferred_date': req_dict.get('preferred_date', '')
        }
        res = supabase_client.insert('service_requests', data, upsert=True)
        if res:
            print(f"[AgroTech Supabase] Service Request '{req_id}' synced to Supabase.")
    except Exception as ex:
        print(f"[AgroTech Supabase] sync_service_request error: {ex}")

def sync_alert(alert_dict: Dict[str, Any]) -> None:
    if not supabase_client: return
    try:
        u_id = alert_dict.get('user_id')
        if u_id:
            check = supabase_client.select('users', f"id=eq.{u_id}&select=id")
            if not check: u_id = None
        c_by = alert_dict.get('created_by')
        if c_by:
            check = supabase_client.select('users', f"id=eq.{c_by}&select=id")
            if not check: c_by = None

        data = {
            'user_id': u_id,
            'audience': alert_dict.get('audience', 'all'),
            'type': alert_dict.get('type', 'system'),
            'title': alert_dict.get('title', 'Notification'),
            'message': alert_dict.get('message', ''),
            'is_read': bool(alert_dict.get('is_read', False)),
            'created_by': c_by
        }
        res = supabase_client.insert('alerts', data)
        if res:
            print(f"[AgroTech Supabase] Alert '{data['title']}' synced to Supabase.")
    except Exception as ex:
        print(f"[AgroTech Supabase] sync_alert error: {ex}")

def sync_complaint(comp_dict: Dict[str, Any], action: str = 'insert') -> None:
    if not supabase_client: return
    try:
        c_id = comp_dict.get('id')
        if action == 'update_status':
            supabase_client.update('complaints', {'status': comp_dict.get('status')}, f"id=eq.{c_id}")
            return
        u_id = comp_dict.get('user_id')
        if u_id:
            check = supabase_client.select('users', f"id=eq.{u_id}&select=id")
            if not check: u_id = None
        data = {
            'user_id': u_id,
            'subject': comp_dict.get('subject', ''),
            'description': comp_dict.get('description', ''),
            'priority': comp_dict.get('priority', 'medium'),
            'status': comp_dict.get('status', 'open')
        }
        res = supabase_client.insert('complaints', data)
        if res:
            print(f"[AgroTech Supabase] Complaint synced to Supabase.")
    except Exception as ex:
        print(f"[AgroTech Supabase] sync_complaint error: {ex}")

def sync_all_from_supabase(sqlite_conn) -> None:
    """Bi-directional sync between Supabase Cloud DB and local SQLite DB."""
    if not supabase_client or not supabase_client.is_healthy():
        return
    try:
        cur = sqlite_conn.cursor()

        # 1. Pull users from Supabase into SQLite
        remote_users = supabase_client.select('users')
        for ru in remote_users:
            r_email = (ru.get('email') or '').strip().lower()
            if not r_email:
                continue
            cur.execute("SELECT id FROM users WHERE LOWER(email) = ?", (r_email,))
            local_u = cur.fetchone()
            if not local_u:
                cur.execute("""
                    INSERT INTO users (id, name, email, phone, password_hash, location, role, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(ru.get('id') or uuid.uuid4()),
                    ru.get('name', 'User'),
                    r_email,
                    ru.get('phone', ''),
                    ru.get('password_hash', ''),
                    ru.get('location', ''),
                    ru.get('role', 'farmer'),
                    ru.get('status', 'active'),
                    ru.get('created_at') or datetime.now(timezone.utc).isoformat()
                ))
            else:
                cur.execute("""
                    UPDATE users SET
                        name = COALESCE(?, name),
                        phone = COALESCE(?, phone),
                        location = COALESCE(?, location),
                        role = COALESCE(?, role),
                        status = COALESCE(?, status)
                    WHERE LOWER(email) = ?
                """, (ru.get('name'), ru.get('phone'), ru.get('location'), ru.get('role'), ru.get('status'), r_email))

        # 2. Push any local SQLite users to Supabase if not yet in Supabase
        cur.execute("SELECT * FROM users")
        col_names = [desc[0] for desc in cur.description]
        local_users = [dict(zip(col_names, r)) for r in cur.fetchall()]
        remote_emails = {(u.get('email') or '').strip().lower() for u in remote_users}
        for lu in local_users:
            l_email = (lu.get('email') or '').strip().lower()
            if l_email and l_email not in remote_emails:
                sync_user(lu)

        # 3. Bi-directional sync of registration_otps
        try:
            remote_otps = supabase_client.select('registration_otps')
            for ro in remote_otps:
                r_email = (ro.get('email') or '').strip().lower()
                if not r_email:
                    continue
                cur.execute("SELECT email FROM registration_otps WHERE LOWER(email) = ?", (r_email,))
                if not cur.fetchone():
                    cur.execute("""
                        INSERT INTO registration_otps (email, name, phone, password_hash, location, role, otp_code, otp_hash, expires_at, attempts)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        r_email,
                        ro.get('name', ''),
                        ro.get('phone', ''),
                        ro.get('password_hash', ''),
                        ro.get('location', ''),
                        ro.get('role', 'farmer'),
                        str(ro.get('otp_code', '')),
                        str(ro.get('otp_hash', '')),
                        ro.get('expires_at'),
                        int(ro.get('attempts', 0))
                    ))
            
            cur.execute("SELECT * FROM registration_otps")
            col_names_otp = [desc[0] for desc in cur.description]
            local_otps = [dict(zip(col_names_otp, r)) for r in cur.fetchall()]
            remote_otp_emails = {(o.get('email') or '').strip().lower() for o in remote_otps}
            for lo in local_otps:
                lo_email = (lo.get('email') or '').strip().lower()
                if lo_email and lo_email not in remote_otp_emails:
                    sync_otp(lo)
        except Exception as ex_otp:
            print(f"[AgroTech Supabase] sync registration_otps error: {ex_otp}")

        sqlite_conn.commit()
    except Exception as ex:
        print(f"[AgroTech Supabase] sync_all_from_supabase error: {ex}")

