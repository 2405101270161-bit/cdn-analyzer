"""
CDN Performance Analyzer - Flask API with Authentication (PostgreSQL Version)
"""

import os
import json
import hashlib
import secrets
import threading
import time
import psycopg2
import concurrent.futures

from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, send_file, session
from flask_cors import CORS
from analyzer import analyze_cdn, load_test, simulate_global_latency


# --- App Configuration ---

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app, supports_credentials=True)


# --- PostgreSQL Connection ---

def get_db():
    return psycopg2.connect(
        host="localhost",
        database="cdn_analyzer",
        user="postgres",
        password="180825"
    )


# --- Database Setup ---

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            fullname TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id SERIAL PRIMARY KEY,
            user_id INT,
            url TEXT,
            domain TEXT,
            cdn TEXT,
            dns_time FLOAT,
            connect_time FLOAT,
            ttfb FLOAT,
            total_time FLOAT,
            cache_status TEXT,
            content_size INT,
            score INT,
            suggestions TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_jobs (
            id SERIAL PRIMARY KEY,
            user_id INT,
            url TEXT,
            interval_minutes INT DEFAULT 5,
            is_active BOOLEAN DEFAULT TRUE,
            last_run TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_results (
            id SERIAL PRIMARY KEY,
            job_id INT,
            ttfb FLOAT,
            total_time FLOAT,
            score INT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS error_logs (
            id SERIAL PRIMARY KEY,
            user_id INT,
            url TEXT,
            status_code INT,
            error_message TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# --- Password Utils ---

def hash_password(password):
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return salt + ":" + hashed


def verify_password(stored, provided):
    salt, hashed = stored.split(":")
    return hashlib.sha256((salt + provided).encode()).hexdigest() == hashed


# --- Auth Decorator ---

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated


# --- Save Result ---

def save_result(result, user_id=None):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO analyses
        (user_id, url, domain, cdn, dns_time, connect_time, ttfb, total_time,
         cache_status, content_size, score, suggestions)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        user_id,
        result.get("url"),
        result.get("domain"),
        result.get("cdn"),
        result.get("dns_time"),
        result.get("connect_time"),
        result.get("ttfb"),
        result.get("total_time"),
        result.get("cache_status"),
        result.get("content_size"),
        result.get("score"),
        json.dumps(result.get("suggestions", []))
    ))

    conn.commit()
    conn.close()


# --- Auth APIs ---

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()

    hashed = hash_password(data["password"])
    cur.execute(
        "INSERT INTO users (fullname, email, password) VALUES (%s, %s, %s)",
        (data["fullname"], data["email"], hashed)
    )

    conn.commit()
    conn.close()
    return jsonify({"message": "User registered"})


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE email=%s", (data["email"],))
    user = cur.fetchone()

    conn.close()

    if not user or not verify_password(user[3], data["password"]):
        return jsonify({"error": "Invalid login"}), 401

    session["user_id"] = user[0]
    
    return jsonify({
        "message": "Login success",
        "user": {
            "id": user[0],
            "fullname": user[1],
            "email": user[2]
        }
    })


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    if "user_id" in session:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT fullname, email FROM users WHERE id=%s", (session["user_id"],))
        user = cur.fetchone()
        conn.close()
        if user:
            return jsonify({
                "authenticated": True,
                "user": {
                    "id": session["user_id"],
                    "fullname": user[0],
                    "email": user[1]
                }
            })
    return jsonify({"authenticated": False}), 401


# --- CDN APIs ---

@app.route("/api/analyze", methods=["POST"])
@login_required
def api_analyze():
    data = request.get_json()
    result = analyze_cdn(data["url"])
    save_result(result, session["user_id"])
    return jsonify(result)


@app.route("/api/loadtest", methods=["POST"])
@login_required
def api_loadtest():
    data = request.get_json()
    result = load_test(data["url"], data.get("count", 20))

    save_result({
        "url": data["url"],
        "ttfb": result.get("avg_time"),
        "total_time": result.get("avg_time")
    }, session["user_id"])

    return jsonify(result)


@app.route("/api/compare", methods=["POST"])
@login_required
def api_compare():
    data = request.get_json()
    urls = data.get("urls", [])
    
    user_id = session["user_id"]
    
    def analyze_and_save(url):
        res = analyze_cdn(url)
        save_result(res, user_id)
        return res

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(urls) if urls else 1)) as executor:
        results = list(executor.map(analyze_and_save, urls))

    return jsonify(results)


@app.route("/api/global-stats", methods=["POST"])
@login_required
def api_global_stats():
    data = request.get_json()
    res = analyze_cdn(data["url"])
    save_result(res, session["user_id"])

    return jsonify(simulate_global_latency(res.get("ttfb", 0)))


@app.route("/api/history", methods=["GET"])
@login_required
def api_history():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM analyses WHERE user_id = %s ORDER BY timestamp DESC LIMIT 50", (session["user_id"],))
    columns = [desc[0] for desc in cur.description] if cur.description else []
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route("/api/history/clear", methods=["DELETE"])
@login_required
def api_clear_history():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM analyses WHERE user_id = %s", (session["user_id"],))
    conn.commit()
    conn.close()
    return jsonify({"message": "History cleared"})

@app.route("/api/monitor/start", methods=["POST"])
@login_required
def api_monitor_start():
    data = request.get_json()
    url = data.get("url", "").strip()
    if not url: return jsonify({"error": "URL required"}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM monitoring_jobs WHERE user_id=%s AND url=%s", (session["user_id"], url))
    job = cur.fetchone()
    if job:
        cur.execute("UPDATE monitoring_jobs SET is_active=TRUE WHERE id=%s", (job[0],))
    else:
        cur.execute("INSERT INTO monitoring_jobs (user_id, url) VALUES (%s, %s)", (session["user_id"], url))
    conn.commit()
    conn.close()
    return jsonify({"message": "Monitoring started"})

@app.route("/api/monitor/stop", methods=["POST"])
@login_required
def api_monitor_stop():
    data = request.get_json()
    url = data.get("url", "").strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE monitoring_jobs SET is_active=FALSE WHERE user_id=%s AND url=%s", (session["user_id"], url))
    conn.commit()
    conn.close()
    return jsonify({"message": "Monitoring stopped"})

@app.route("/api/monitor/status", methods=["GET"])
@login_required
def api_monitor_status():
    url = request.args.get("url")
    conn = get_db()
    cur = conn.cursor()
    if url:
        cur.execute("SELECT * FROM monitoring_jobs WHERE user_id=%s AND url=%s", (session["user_id"], url))
        columns = [desc[0] for desc in cur.description] if cur.description else []
        job_row = cur.fetchone()
        if not job_row:
            conn.close()
            return jsonify({"is_active": False, "results": []})
        job = dict(zip(columns, job_row))
        
        cur.execute("SELECT ttfb, total_time, score, timestamp FROM monitoring_results WHERE job_id=%s ORDER BY timestamp DESC LIMIT 30", (job["id"],))
        res_columns = [desc[0] for desc in cur.description] if cur.description else []
        results = [dict(zip(res_columns, row)) for row in cur.fetchall()]
        conn.close()
        return jsonify({
            "is_active": bool(job["is_active"]),
            "results": list(reversed(results))
        })
    else:
        cur.execute("SELECT * FROM monitoring_jobs WHERE user_id=%s", (session["user_id"],))
        columns = [desc[0] for desc in cur.description] if cur.description else []
        jobs = [dict(zip(columns, row)) for row in cur.fetchall()]
        conn.close()
        return jsonify(jobs)

@app.route("/api/errors", methods=["GET"])
@login_required
def api_errors():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM error_logs WHERE user_id=%s ORDER BY timestamp DESC LIMIT 50", (session["user_id"],))
    columns = [desc[0] for desc in cur.description] if cur.description else []
    errs = [dict(zip(columns, row)) for row in cur.fetchall()]
    conn.close()
    return jsonify(errs)

# --- Frontend Serving ---

@app.route("/")
def serve_login():
    return send_file(os.path.join(FRONTEND_DIR, "login.html"))

@app.route("/dashboard")
def serve_dashboard():
    return send_file(os.path.join(FRONTEND_DIR, "index.html"))

@app.route("/monitor")
def serve_monitor():
    return send_file(os.path.join(FRONTEND_DIR, "monitor.html"))

@app.route("/compare")
def serve_compare():
    return send_file(os.path.join(FRONTEND_DIR, "compare.html"))

@app.route("/map")
def serve_map():
    return send_file(os.path.join(FRONTEND_DIR, "map.html"))

@app.route("/errors")
def serve_errors():
    return send_file(os.path.join(FRONTEND_DIR, "errors.html"))

@app.route("/<path:filename>")
def serve_frontend_files(filename):
    filepath = os.path.join(FRONTEND_DIR, filename)
    if os.path.isfile(filepath):
        return send_from_directory(FRONTEND_DIR, filename)
    return "Not Found", 404

# --- Background Monitor ---

def monitor_loop():
    while True:
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM monitoring_jobs WHERE is_active = TRUE")
            columns = [desc[0] for desc in cur.description] if cur.description else []
            jobs = [dict(zip(columns, row)) for row in cur.fetchall()]
            
            now = datetime.utcnow()
            for job in jobs:
                last_run = job["last_run"]
                if last_run:
                    diff_mins = (now - last_run).total_seconds() / 60
                    if diff_mins < job["interval_minutes"]:
                        continue
                
                res = analyze_cdn(job["url"])
                cur.execute("UPDATE monitoring_jobs SET last_run = %s WHERE id = %s", (now, job["id"]))
                
                cur.execute("INSERT INTO monitoring_results (job_id, ttfb, total_time, score) VALUES (%s, %s, %s, %s)",
                            (job["id"], res.get("ttfb"), res.get("total_time"), res.get("score")))
                            
                if res.get("error") or res.get("status_code", 0) >= 400:
                    err_msg = res.get("error") or "HTTP Error"
                    cur.execute("INSERT INTO error_logs (user_id, url, status_code, error_message) VALUES (%s, %s, %s, %s)",
                                (job["user_id"], job["url"], res.get("status_code"), err_msg))
                                
            conn.commit()
            conn.close()
        except Exception as e:
            print("Monitor thread error:", e)
            
        time.sleep(60)

# --- Run App ---

if __name__ == "__main__":
    init_db()
    threading.Thread(target=monitor_loop, daemon=True).start()
    app.run(debug=True, port=5050)