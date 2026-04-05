"""
Database layer for TOPPERS AI Business Intelligence features.
Uses SQLite for lightweight, zero-config storage.
"""
import sys
import sqlite3
import json
import os
import time
from datetime import datetime, timedelta

# Force UTF-8 for Windows
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'toppers_bi.db')


def get_db():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize database tables if they don't exist."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS competitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            favicon_url TEXT,
            product_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            last_crawled_at TEXT
        );

        CREATE TABLE IF NOT EXISTS crawl_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_id INTEGER NOT NULL,
            products_json TEXT NOT NULL DEFAULT '[]',
            product_count INTEGER DEFAULT 0,
            crawl_duration_ms INTEGER DEFAULT 0,
            status TEXT DEFAULT 'success',
            error_message TEXT,
            crawled_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (competitor_id) REFERENCES competitors(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_id INTEGER NOT NULL UNIQUE,
            frequency TEXT NOT NULL DEFAULT 'daily',
            active INTEGER DEFAULT 1,
            last_run TEXT,
            next_run TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (competitor_id) REFERENCES competitors(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS change_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_id INTEGER NOT NULL,
            competitor_name TEXT,
            summary TEXT NOT NULL,
            changes_json TEXT NOT NULL DEFAULT '{}',
            old_crawl_id INTEGER,
            new_crawl_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (competitor_id) REFERENCES competitors(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS trend_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            sentiment_score INTEGER,
            keywords_json TEXT NOT NULL DEFAULT '[]',
            competitor_mentions_json TEXT NOT NULL DEFAULT '[]',
            summary TEXT,
            raw_context TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    conn.commit()
    conn.close()
    print("✅ BI Database initialized.")


# --- Competitor CRUD ---

def add_competitor(name, url, favicon_url=None):
    """Add a new competitor to track. Returns the competitor dict or None if duplicate."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO competitors (name, url, favicon_url) VALUES (?, ?, ?)",
            (name, url, favicon_url)
        )
        conn.commit()
        comp_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM competitors WHERE id = ?", (comp_id,)).fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        # URL already exists, return existing
        row = conn.execute("SELECT * FROM competitors WHERE url = ?", (url,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_competitors():
    """Get all tracked competitors."""
    conn = get_db()
    rows = conn.execute(
        "SELECT c.*, s.frequency, s.active as schedule_active "
        "FROM competitors c LEFT JOIN schedules s ON c.id = s.competitor_id "
        "ORDER BY c.created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_competitor(comp_id):
    """Get a single competitor by ID."""
    conn = get_db()
    row = conn.execute("SELECT * FROM competitors WHERE id = ?", (comp_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_competitor(comp_id):
    """Delete a competitor and all related data."""
    conn = get_db()
    conn.execute("DELETE FROM competitors WHERE id = ?", (comp_id,))
    conn.commit()
    conn.close()


def update_competitor_crawl(comp_id, product_count):
    """Update the last crawl timestamp and product count."""
    conn = get_db()
    conn.execute(
        "UPDATE competitors SET last_crawled_at = datetime('now'), product_count = ? WHERE id = ?",
        (product_count, comp_id)
    )
    conn.commit()
    conn.close()


# --- Crawl Results ---

def save_crawl(competitor_id, products, duration_ms=0, status='success', error_message=None):
    """Save a crawl result. Returns the crawl ID."""
    conn = get_db()
    products_json = json.dumps(products, ensure_ascii=False)
    cursor = conn.execute(
        "INSERT INTO crawl_results (competitor_id, products_json, product_count, crawl_duration_ms, status, error_message) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (competitor_id, products_json, len(products), duration_ms, status, error_message)
    )
    conn.commit()
    crawl_id = cursor.lastrowid
    conn.close()

    # Update competitor metadata
    if status == 'success':
        update_competitor_crawl(competitor_id, len(products))

    return crawl_id


def get_latest_crawl(competitor_id):
    """Get the most recent crawl result for a competitor."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM crawl_results WHERE competitor_id = ? AND status = 'success' "
        "ORDER BY crawled_at DESC LIMIT 1",
        (competitor_id,)
    ).fetchone()
    conn.close()
    if row:
        result = dict(row)
        result['products'] = json.loads(result['products_json'])
        return result
    return None


def get_previous_crawl(competitor_id):
    """Get the second most recent crawl result (for comparison)."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM crawl_results WHERE competitor_id = ? AND status = 'success' "
        "ORDER BY crawled_at DESC LIMIT 1 OFFSET 1",
        (competitor_id,)
    ).fetchone()
    conn.close()
    if row:
        result = dict(row)
        result['products'] = json.loads(result['products_json'])
        return result
    return None


def get_crawl_history(competitor_id, limit=10):
    """Get crawl history for a competitor."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, competitor_id, product_count, crawl_duration_ms, status, error_message, crawled_at "
        "FROM crawl_results WHERE competitor_id = ? ORDER BY crawled_at DESC LIMIT ?",
        (competitor_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Schedules ---

def add_schedule(competitor_id, frequency='daily'):
    """Create or update a schedule for a competitor."""
    conn = get_db()
    now = datetime.utcnow().isoformat()
    if frequency == 'daily':
        next_run = (datetime.utcnow() + timedelta(days=1)).isoformat()
    else:
        next_run = (datetime.utcnow() + timedelta(weeks=1)).isoformat()

    try:
        conn.execute(
            "INSERT INTO schedules (competitor_id, frequency, last_run, next_run) VALUES (?, ?, ?, ?)",
            (competitor_id, frequency, now, next_run)
        )
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE schedules SET frequency = ?, active = 1, next_run = ? WHERE competitor_id = ?",
            (frequency, next_run, competitor_id)
        )
    conn.commit()
    conn.close()


def remove_schedule(competitor_id):
    """Remove a schedule for a competitor."""
    conn = get_db()
    conn.execute("DELETE FROM schedules WHERE competitor_id = ?", (competitor_id,))
    conn.commit()
    conn.close()


def get_all_schedules():
    """Get all schedules with competitor info."""
    conn = get_db()
    rows = conn.execute(
        "SELECT s.*, c.name as competitor_name, c.url as competitor_url "
        "FROM schedules s JOIN competitors c ON s.competitor_id = c.id "
        "ORDER BY s.next_run ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_due_schedules():
    """Get schedules that are due to run."""
    conn = get_db()
    now = datetime.utcnow().isoformat()
    rows = conn.execute(
        "SELECT s.*, c.name as competitor_name, c.url as competitor_url "
        "FROM schedules s JOIN competitors c ON s.competitor_id = c.id "
        "WHERE s.active = 1 AND s.next_run <= ?",
        (now,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_schedule_run(schedule_id, frequency):
    """Update schedule after a run."""
    conn = get_db()
    now = datetime.utcnow().isoformat()
    if frequency == 'daily':
        next_run = (datetime.utcnow() + timedelta(days=1)).isoformat()
    else:
        next_run = (datetime.utcnow() + timedelta(weeks=1)).isoformat()

    conn.execute(
        "UPDATE schedules SET last_run = ?, next_run = ? WHERE id = ?",
        (now, next_run, schedule_id)
    )
    conn.commit()
    conn.close()


# --- Change Reports ---

def save_report(competitor_id, competitor_name, summary, changes):
    """Save a change detection report."""
    conn = get_db()
    changes_json = json.dumps(changes, ensure_ascii=False)
    cursor = conn.execute(
        "INSERT INTO change_reports (competitor_id, competitor_name, summary, changes_json) "
        "VALUES (?, ?, ?, ?)",
        (competitor_id, competitor_name, summary, changes_json)
    )
    conn.commit()
    report_id = cursor.lastrowid
    conn.close()
    return report_id


def get_all_reports(limit=50):
    """Get all change reports, newest first."""
    conn = get_db()
    rows = conn.execute(
        "SELECT r.*, c.url as competitor_url "
        "FROM change_reports r LEFT JOIN competitors c ON r.competitor_id = c.id "
        "ORDER BY r.created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d['changes'] = json.loads(d['changes_json'])
        results.append(d)
    return results


def get_report(report_id):
    """Get a single report by ID."""
    conn = get_db()
    row = conn.execute(
        "SELECT r.*, c.url as competitor_url "
        "FROM change_reports r LEFT JOIN competitors c ON r.competitor_id = c.id "
        "WHERE r.id = ?",
        (report_id,)
    ).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d['changes'] = json.loads(d['changes_json'])
        return d
    return None


# --- Trend Reports ---

def save_trend_report(topic, sentiment_score, keywords, competitor_mentions, summary, raw_context):
    """Save a market trend analysis report."""
    conn = get_db()
    keywords_json = json.dumps(keywords, ensure_ascii=False)
    mentions_json = json.dumps(competitor_mentions, ensure_ascii=False)
    
    cursor = conn.execute(
        "INSERT INTO trend_reports (topic, sentiment_score, keywords_json, competitor_mentions_json, summary, raw_context) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (topic, sentiment_score, keywords_json, mentions_json, summary, raw_context)
    )
    conn.commit()
    report_id = cursor.lastrowid
    conn.close()
    return report_id

def get_trend_history(limit=20):
    """Get recent trend reports."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, topic, sentiment_score, keywords_json, competitor_mentions_json, summary, created_at "
        "FROM trend_reports ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    
    results = []
    for r in rows:
        d = dict(r)
        d['keywords'] = json.loads(d['keywords_json'])
        d['competitor_mentions'] = json.loads(d['competitor_mentions_json'])
        results.append(d)
    return results

def get_trend_report(report_id):
    """Get a specific trend report, including raw context."""
    conn = get_db()
    row = conn.execute("SELECT * FROM trend_reports WHERE id = ?", (report_id,)).fetchone()
    conn.close()
    
    if row:
        d = dict(row)
        d['keywords'] = json.loads(d['keywords_json'])
        d['competitor_mentions'] = json.loads(d['competitor_mentions_json'])
        return d
    return None


# Initialize on import
init_db()
