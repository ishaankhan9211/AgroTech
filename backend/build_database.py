"""
AgroTech Database Builder & Migration Script
Builds or refreshes the local SQLite database (backend/agrotech.db).
Zero external dependencies (uses standard Python library).

Usage:
    python backend/build_database.py
    python backend/build_database.py --reset
"""

import os
import sys
import sqlite3
import hashlib
import secrets
import shutil
import argparse
from pathlib import Path
from datetime import datetime

# Set output encoding to UTF-8
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / 'agrotech.db'

def hash_password(password: str) -> str:
    """Standard PBKDF2-HMAC-SHA256 password hasher with 100,000 iterations."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f"pbkdf2_sha256${salt}${dk.hex()}"

def build_database(db_path: Path, reset: bool = False):
    print("=" * 65)
    print("🌱  AgroTech — Database Builder & Schema Initializer")
    print("=" * 65)
    print(f"📁 Target Database: {db_path}")

    if reset and db_path.exists():
        backup_path = db_path.with_name(f"agrotech_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        print(f"📦 Backing up existing database to: {backup_path.name}")
        shutil.copy2(db_path, backup_path)
        try:
            db_path.unlink()
            print("🗑️  Previous database removed for clean rebuild.")
        except Exception as e:
            print(f"⚠️  Could not remove previous DB ({e}), will use DROP/REPLACE.")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("PRAGMA foreign_keys = ON;")
    cur.execute("PRAGMA journal_mode = WAL;")

    print("\n🔨 Creating Tables & Constraints...")

    # 1. Users Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            location TEXT DEFAULT '',
            role TEXT NOT NULL DEFAULT 'farmer' CHECK (role IN ('farmer', 'provider', 'seller', 'admin')),
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'blocked', 'pending', 'inactive')),
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # 2. Services Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT NOT NULL DEFAULT 'per day',
            description TEXT DEFAULT '',
            location TEXT DEFAULT '',
            image TEXT DEFAULT '',
            rating REAL DEFAULT 4.5,
            reviews INTEGER DEFAULT 0,
            available INTEGER DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'approved' CHECK (status IN ('pending', 'approved', 'rejected', 'active', 'inactive')),
            posted_by TEXT DEFAULT NULL REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # 3. Service Requests Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS service_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            farmer_id TEXT DEFAULT NULL REFERENCES users(id) ON DELETE SET NULL,
            farmer_name TEXT DEFAULT '',
            farmer_phone TEXT DEFAULT '',
            provider_id TEXT DEFAULT NULL REFERENCES users(id) ON DELETE SET NULL,
            service_id INTEGER DEFAULT NULL REFERENCES services(id) ON DELETE SET NULL,
            service_name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            price REAL NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'cod',
            payment_status TEXT NOT NULL DEFAULT 'pending' CHECK (payment_status IN ('pending', 'paid', 'success', 'completed', 'failed', 'refunded')),
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'in_progress', 'rejected', 'confirmed', 'completed', 'cancelled')),
            address TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            preferred_date TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # 4. Complaints Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT NULL REFERENCES users(id) ON DELETE SET NULL,
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'assigned', 'resolved', 'closed')),
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # 5. Alerts Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT NULL REFERENCES users(id) ON DELETE CASCADE,
            audience TEXT NOT NULL DEFAULT 'all' CHECK (audience IN ('all', 'farmer', 'provider', 'admin')),
            type TEXT NOT NULL DEFAULT 'system' CHECK (type IN ('request', 'status', 'system', 'promo', 'order', 'complaint', 'broadcast', 'alert')),
            title TEXT NOT NULL DEFAULT 'Notification',
            message TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_by TEXT DEFAULT NULL REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # 6. Legacy Notifications Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audience TEXT NOT NULL DEFAULT 'all',
            message TEXT NOT NULL,
            created_by TEXT DEFAULT NULL REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # 7. Registration OTPs Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS registration_otps (
            email TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            location TEXT DEFAULT '',
            role TEXT NOT NULL DEFAULT 'farmer' CHECK (role IN ('farmer', 'provider', 'seller', 'admin')),
            otp_code TEXT NOT NULL,
            otp_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    print("⚡ Creating Performance Indexes...")
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
        "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);",
        "CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);",
        "CREATE INDEX IF NOT EXISTS idx_services_category ON services(category);",
        "CREATE INDEX IF NOT EXISTS idx_services_posted_by ON services(posted_by);",
        "CREATE INDEX IF NOT EXISTS idx_services_available ON services(available);",
        "CREATE INDEX IF NOT EXISTS idx_services_status ON services(status);",
        "CREATE INDEX IF NOT EXISTS idx_requests_farmer ON service_requests(farmer_id);",
        "CREATE INDEX IF NOT EXISTS idx_requests_provider ON service_requests(provider_id);",
        "CREATE INDEX IF NOT EXISTS idx_requests_status ON service_requests(status);",
        "CREATE INDEX IF NOT EXISTS idx_complaints_user ON complaints(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);",
        "CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_alerts_audience ON alerts(audience);",
        "CREATE INDEX IF NOT EXISTS idx_alerts_is_read ON alerts(is_read);"
    ]
    for idx_sql in indexes:
        cur.execute(idx_sql)

    # Auto-migrations for existing databases
    for tbl, col, dtype in [
        ("services", "posted_by", "TEXT DEFAULT NULL"),
        ("services", "status", "TEXT NOT NULL DEFAULT 'approved'"),
        ("service_requests", "farmer_phone", "TEXT DEFAULT ''"),
        ("service_requests", "farmer_name", "TEXT DEFAULT ''"),
        ("service_requests", "payment_method", "TEXT NOT NULL DEFAULT 'cod'"),
        ("service_requests", "payment_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("alerts", "is_read", "INTEGER NOT NULL DEFAULT 0")
    ]:
        try:
            cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {dtype};")
        except Exception:
            pass

    print("\n🌱 Seeding Default Accounts...")
    # Admin Account
    cur.execute("SELECT id FROM users WHERE email = 'admin@agrotech.com'")
    if not cur.fetchone():
        admin_pw = hash_password('admin123')
        cur.execute("""
            INSERT INTO users (id, name, email, phone, password_hash, location, role, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ('usr-admin-01', 'System Administrator', 'admin@agrotech.com', '9876543210', admin_pw, 'National Head Office', 'admin', 'active'))
        print("  ✓ Admin:    admin@agrotech.com    (Password: admin123)")
    else:
        cur.execute("UPDATE users SET role = 'admin', status = 'active' WHERE email = 'admin@agrotech.com'")
        print("  ✓ Admin:    admin@agrotech.com    (Updated to active)")

    # Farmer Account
    cur.execute("SELECT id FROM users WHERE email = 'farmer@agrotech.com'")
    if not cur.fetchone():
        farmer_pw = hash_password('farmer123')
        cur.execute("""
            INSERT INTO users (id, name, email, phone, password_hash, location, role, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ('usr-farmer-01', 'Madhur Pratap Singh', 'farmer@agrotech.com', '8127059442', farmer_pw, 'Indore, MP', 'farmer', 'active'))
        print("  ✓ Farmer:   farmer@agrotech.com   (Password: farmer123)")
    else:
        cur.execute("UPDATE users SET role = 'farmer', status = 'active', phone = '8127059442' WHERE email = 'farmer@agrotech.com'")
        print("  ✓ Farmer:   farmer@agrotech.com   (Updated to active)")

    # Provider Account
    cur.execute("SELECT id FROM users WHERE email = 'provider@agrotech.com'")
    if not cur.fetchone():
        prov_pw = hash_password('provider123')
        cur.execute("""
            INSERT INTO users (id, name, email, phone, password_hash, location, role, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ('usr-provider-01', 'Rajesh Patel (Kisan Agro Services)', 'provider@agrotech.com', '9893012345', prov_pw, 'Indore, MP', 'provider', 'active'))
        print("  ✓ Provider: provider@agrotech.com (Password: provider123)")
    else:
        cur.execute("UPDATE users SET role = 'provider', status = 'active' WHERE email = 'provider@agrotech.com'")
        print("  ✓ Provider: provider@agrotech.com (Updated to active)")

    print("\n🚜 Seeding Agricultural Equipment & Services...")
    cur.execute("SELECT COUNT(*) FROM services")
    count_services = cur.fetchone()[0]
    if count_services == 0:
        default_services = [
            (1, "Mahindra 575 DI Tractor Rental", "machinery", 800.0, "per acre", "Powerful 45HP tractor suitable for ploughing, tilling, and heavy-duty farming tasks.", "https://5.imimg.com/data5/SELLER/Default/2021/6/CX/WL/RI/30912792/mahindra-tractor-yuvraj-bumper-1000x1000.jpg", 4.8, 128, 1, "approved", "Indore, MP", "usr-provider-01"),
            (2, "John Deere 5050 D Tractor", "machinery", 1000.0, "per acre", "High-efficiency tractor with advanced hydraulics and rotary tiller attachment.", "https://cpimg.tistatic.com/10029058/b/4/John-deere-Tractors..jpg", 4.9, 95, 1, "approved", "Bhopal, MP", "usr-provider-01"),
            (3, "Modern Combine Harvester", "machinery", 1200.0, "per acre", "Fast harvesting for wheat, soybean, and paddy. Reduces harvest loss significantly.", "https://5.imimg.com/data5/WC/IE/YH/ANDROID-86040604/prod-20200810-2031297210080910753376724-jpg-1000x1000.jpg", 4.7, 72, 1, "approved", "Ujjain, MP", "usr-provider-01"),
            (4, "Fieldking Heavy Rotavator", "machinery", 500.0, "per acre", "Heavy-duty 7-feet rotavator for complete soil preparation and fine seedbed.", "https://www.fieldking.com/blogs/wp-content/uploads/2024/09/Ploughing.jpg", 4.6, 64, 1, "approved", "Gwalior, MP", "usr-provider-01"),
            (5, "Automatic Drip Irrigation Kit", "irrigation", 3500.0, "per kit", "Complete drip system for 1 acre land. Saves up to 60% water and boosts yield.", "https://5.imimg.com/data5/SELLER/Default/2022/10/BC/MY/LI/21395960/drip-irrigation-system-1000x1000.jpg", 4.8, 89, 1, "approved", "Indore, MP", "usr-provider-01"),
            (6, "IFFCO DAP Fertilizer (50kg Bag)", "fertilizer", 1350.0, "per bag", "Original certified DAP fertilizer for strong root growth and early crop establishment.", "https://5.imimg.com/data5/SELLER/Default/2022/5/NJ/VT/MB/26553143/dap-fertilizer-500x500.jpg", 4.7, 201, 1, "approved", "Bhopal, MP", "usr-provider-01"),
            (7, "HYV Premium Wheat Seeds (GW-322)", "seeds", 450.0, "per kg", "Certified disease-resistant high yield wheat seeds with high germination rate.", "https://5.imimg.com/data5/SELLER/Default/2021/9/ZG/OS/PB/3131427/wheat-seeds-500x500.jpg", 4.9, 156, 1, "approved", "Sehore, MP", "usr-provider-01"),
            (8, "5-Ton Crop Transport Mini Truck", "transport", 2500.0, "per trip", "Reliable door-to-mandi farm transport service with GPS tracking available 24/7.", "https://5.imimg.com/data5/SELLER/Default/2022/3/QF/XN/XJ/149399990/mini-truck-500x500.jpg", 4.5, 43, 1, "approved", "Indore, MP", "usr-provider-01")
        ]
        for s in default_services:
            cur.execute("""
                INSERT OR IGNORE INTO services (id, name, category, price, unit, description, image, rating, reviews, available, status, location, posted_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, s)
        print(f"  ✓ Seeded {len(default_services)} agricultural services & equipment.")
    else:
        print(f"  ✓ Services already populated ({count_services} items).")

    print("\n📦 Seeding Sample Requests & Alerts...")
    cur.execute("SELECT COUNT(*) FROM service_requests")
    if cur.fetchone()[0] == 0:
        sample_reqs = [
            ('REQ-1001', 'usr-farmer-01', 'Madhur Pratap Singh', '8127059442', 'usr-provider-01', 1, 'Mahindra 575 DI Tractor Rental', 2, 1600.0, 'cod', 'pending', 'accepted', 'Indore Farm Sector 4', 'Need for ploughing 2 acres land.', 'Tomorrow 8:00 AM'),
            ('REQ-1002', 'usr-farmer-01', 'Madhur Pratap Singh', '8127059442', 'usr-provider-01', 5, 'Automatic Drip Irrigation Kit', 1, 3500.0, 'upi', 'paid', 'pending', 'Indore Farm Sector 4', 'Installation assistance required.', 'This weekend')
        ]
        for r in sample_reqs:
            cur.execute("""
                INSERT OR IGNORE INTO service_requests (request_id, farmer_id, farmer_name, farmer_phone, provider_id, service_id, service_name, quantity, price, payment_method, payment_status, status, address, notes, preferred_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, r)
        print(f"  ✓ Seeded {len(sample_reqs)} sample service bookings.")

    cur.execute("SELECT COUNT(*) FROM alerts")
    if cur.fetchone()[0] == 0:
        sample_alerts = [
            ('usr-farmer-01', 'farmer', 'request', 'Service Request Accepted ✅', 'Your booking for Mahindra 575 DI Tractor has been accepted by the provider.', 0),
            ('usr-farmer-01', 'farmer', 'system', '🌾 Welcome to AgroTech!', 'Explore available farm machinery, rental equipment and farm supplies in your region.', 0),
            ('usr-provider-01', 'provider', 'request', 'New Booking Received 🚜', 'Farmer Madhur Pratap Singh requested Mahindra 575 DI Tractor Rental.', 0),
            (None, 'all', 'promo', '🎉 Seasonal Harvesting Discounts', 'Special 15% discount on combine harvesters and transport services this season.', 0)
        ]
        for a in sample_alerts:
            cur.execute("""
                INSERT OR IGNORE INTO alerts (user_id, audience, type, title, message, is_read)
                VALUES (?, ?, ?, ?, ?, ?)
            """, a)
        print(f"  ✓ Seeded {len(sample_alerts)} initial notification alerts.")

    conn.commit()

    # Verification & Health Check
    cur.execute("PRAGMA integrity_check;")
    integrity = cur.fetchone()[0]

    tables = ['users', 'services', 'service_requests', 'complaints', 'alerts', 'notifications', 'registration_otps']
    stats = {}
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t};")
        stats[t] = cur.fetchone()[0]

    conn.close()

    print("\n" + "=" * 65)
    print("✅  DATABASE BUILD SUCCESSFUL!")
    print("=" * 65)
    print(f"🔍 Integrity Check: {integrity.upper()}")
    print("📊 Table Summary:")
    for t, cnt in stats.items():
        print(f"    • {t:<22} : {cnt:>4} records")
    print("=" * 65)
    print("🚀 You can now start the backend with:")
    print("    .\\start_backend.bat   OR   python -m uvicorn backend.main:app --reload")
    print("=" * 65)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="AgroTech Database Schema Builder")
    parser.add_argument('--reset', action='store_true', help="Backup and recreate the database from scratch")
    parser.add_argument('--db-path', type=str, default=str(DEFAULT_DB_PATH), help="Custom database file path")
    args = parser.parse_args()

    build_database(Path(args.db_path), reset=args.reset)
