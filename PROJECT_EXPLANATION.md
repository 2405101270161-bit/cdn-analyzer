# CDN Performance Analyzer — Complete Project Explanation

> Use this guide to explain every aspect of the project to your teacher.

---

## 1. What is This Project?

A **web-based tool** that analyzes the **CDN (Content Delivery Network) performance** of any website. It tells you:

- **Which CDN** a website uses (Cloudflare, AWS CloudFront, Akamai, etc.)
- **How fast** the website responds (DNS time, connection time, TTFB, total load time)
- **Cache performance** — whether the CDN is caching content properly
- **Performance score** (0–100) with a letter grade
- **Optimization suggestions** — actionable improvements
- **Load testing** — how the site performs under 20 rapid requests

---

## 2. Technology Stack

| Layer        | Technology         | Why We Used It |
|---|---|---|
| **Frontend** | HTML, CSS, JavaScript | Standard web technologies, no framework needed |
| **Styling**  | Vanilla CSS (Dark Mode + Glassmorphism) | Premium, modern look without external CSS frameworks |
| **Charts**   | Chart.js (v4.4.1) via CDN | Industry-standard JS library for interactive data visualization |
| **Backend**  | Python + Flask | Lightweight web framework, ideal for REST APIs |
| **Database** | SQLite | Serverless, zero-config database — perfect for local/student projects |
| **Auth**     | Flask Sessions + SHA-256 Hashing | Secure session-based authentication with salted password hashing |
| **HTTP Testing** | Python `requests` library | Makes HTTP requests to target websites and measures timing |
| **DNS**      | Python `socket` library | Performs DNS lookups to measure resolution time |
| **Fonts**    | Google Fonts (Inter, JetBrains Mono) | Professional typography |

---

## 3. System Architecture

```
┌────────────────────────────────────────────────────┐
│                 User's Browser                      │
│   ┌─────────────┐    ┌──────────────────────────┐  │
│   │ login.html  │───→│  index.html (Dashboard)  │  │
│   │ (Register/  │    │  + style.css             │  │
│   │  Login)     │    │  + dashboard.js           │  │
│   └─────────────┘    │  + Chart.js               │  │
│                      └──────────┬───────────────┘  │
└─────────────────────────────────┼──────────────────┘
                                  │ REST API calls
                                  │ (JSON over HTTP)
┌─────────────────────────────────┼──────────────────┐
│            Flask Backend (app.py)                   │
│   ┌─────────────────────────────┼────────────────┐ │
│   │  Auth Endpoints:            │                 │ │
│   │  POST /api/auth/register    │                 │ │
│   │  POST /api/auth/login       │                 │ │
│   │  POST /api/auth/logout      │                 │ │
│   │  GET  /api/auth/me          │                 │ │
│   ├─────────────────────────────┤                 │ │
│   │  Analysis Endpoints:        │                 │ │
│   │  POST /api/analyze    ──────┼──→ analyzer.py  │ │
│   │  POST /api/loadtest   ──────┼──→ analyzer.py  │ │
│   │  GET  /api/history          │                 │ │
│   │  DELETE /api/history/clear  │                 │ │
│   └─────────────────────────────┼────────────────┘ │
│                                 │                   │
│              ┌──────────────────▼────────────┐     │
│              │    SQLite Database             │     │
│              │  ┌─────────┐  ┌────────────┐  │     │
│              │  │  users  │  │  analyses  │  │     │
│              │  └─────────┘  └────────────┘  │     │
│              └───────────────────────────────┘     │
└────────────────────────────────────────────────────┘
                      │
                      │ HTTP requests to test targets
                      ▼
              ┌───────────────┐
              │ Target Website│
              │ (e.g. cloud-  │
              │  flare.com)   │
              └───────────────┘
```

---

## 4. How Each Feature Works

### 4.1 — User Registration & Login

**How it works:**
1. User fills in name, email, password on `login.html`
2. Frontend sends `POST /api/auth/register` with JSON data
3. Backend **hashes the password** using SHA-256 with a random 16-byte salt
4. Stores `salt:hash` in the `users` table in SQLite
5. On login, backend retrieves the stored hash, re-hashes the provided password with the same salt, and compares
6. If matched, creates a **Flask session** (server-side cookie) — user stays logged in

**Security features:**
- Passwords are **never stored in plain text**
- Each password has a unique **random salt** (prevents rainbow table attacks)
- Sessions use **cryptographic secret key** (randomly generated on each server start)
- API endpoints are **protected** with a `@login_required` decorator

### 4.2 — CDN Detection

**How it works** (in `analyzer.py`):
1. Makes an HTTP GET request to the target URL
2. Reads the **response headers** (like `Server`, `X-Cache`, `Via`, `CF-Ray`, etc.)
3. Compares headers against a **signature database of 13 CDN providers**:

| CDN Provider | Detection Method |
|---|---|
| Cloudflare | `CF-Ray` header or `Server: cloudflare` |
| AWS CloudFront | `X-Amz-Cf-Id` header or `Via: cloudfront` |
| Akamai | `X-Akamai-Transformed` or server contains `akamai` |
| Fastly | `X-Fastly-Request-ID` or `Via: varnish` |
| Google Cloud CDN | `Via: google` or `Server: gws` |
| Vercel | `Server: Vercel` or `X-Vercel-Id` |
| Netlify | `Server: Netlify` |
| Azure CDN | `X-MSEdge-Ref` header |
| KeyCDN | `Server: keycdn` |
| StackPath | `X-HW` header |
| Sucuri | `Server: Sucuri` |
| Imperva/Incapsula | `X-CDN: Incapsula` |
| Limelight | `Via` contains `limelight` |

### 4.3 — Performance Measurement

**DNS Lookup Time:**
```python
# Uses Python's socket library
start = time.time()
socket.getaddrinfo(domain, 443)  # Resolve domain to IP
dns_time = (time.time() - start) * 1000  # Convert to milliseconds
```

**TTFB (Time to First Byte):**
```python
# Measures from request sent → first byte of response arrives
response = requests.get(url)
ttfb = response.elapsed.total_seconds() * 1000
```

**Connect Time & Total Time:**
- Measured using `time.time()` around the full HTTP request
- Connect time ≈ TTFB − DNS (approximate breakdown)

### 4.4 — Performance Scoring (0–100)

Starts at 100 and **subtracts penalties:**

| Condition | Penalty |
|---|---|
| DNS time > 100ms | −10 |
| TTFB > 300ms | −15 |
| TTFB > 600ms | −25 |
| Total time > 1000ms | −15 |
| Total time > 3000ms | −25 |
| Cache status = MISS | −10 |
| No CDN detected | −10 |

**Grades:**
- A+ (90–100), A (80–89), B (70–79), C (60–69), D (40–59), F (0–39)

### 4.5 — Load Testing

**How it works:**
1. Sends **20 sequential HTTP requests** to the target URL
2. Records the response time for each request
3. Calculates statistics:
   - **Average, Min, Max** response times
   - **Median** (middle value)
   - **P95** (95th percentile — worst-case for 95% of users)
   - **Standard Deviation** (consistency)
   - **Success Rate** (% of requests that returned HTTP 200)

### 4.6 — Data Visualization (Chart.js)

**Two charts are rendered:**
1. **Timing Breakdown** (Bar Chart) — DNS, TCP Connect, TTFB, Total Time as colored bars
2. **Performance Distribution** (Doughnut Chart) — proportional breakdown of where time is spent
3. **Load Test** (Line Chart) — response time across all 20 requests with average line

### 4.7 — Analysis History (SQLite)

- Every analysis result is saved to the `analyses` table with the user's ID
- Users only see **their own** history (SQL `WHERE user_id = ?`)
- History shows URL, CDN, DNS, TTFB, Total, Cache, Score, Timestamp
- Can be refreshed or cleared from the dashboard

---

## 5. Project File Structure

```
cdn-analyzer/
├── backend/
│   ├── app.py          ← Flask API server (auth + analysis endpoints)
│   └── analyzer.py     ← Core CDN analysis engine
├── frontend/
│   ├── login.html      ← Login/Register page
│   ├── index.html      ← Main dashboard
│   ├── style.css       ← All styling (dark mode, glassmorphism)
│   └── dashboard.js    ← Frontend logic (API calls, charts, auth)
├── database/
│   └── results.db      ← SQLite database (auto-created)
└── reports/            ← For PDF exports
```

---

## 6. Key Concepts Used (For Teacher)

| Concept | Where It's Used |
|---|---|
| **REST API** | Flask endpoints (`GET`, `POST`, `DELETE`) returning JSON |
| **Client-Server Architecture** | Frontend (browser) ↔ Backend (Flask) via HTTP |
| **MVC Pattern** | Model (SQLite), View (HTML/CSS), Controller (Flask routes) |
| **Session Management** | Flask sessions for login state |
| **Password Hashing** | SHA-256 with random salt for security |
| **CORS** | Flask-CORS for cross-origin request handling |
| **SQL (CRUD Operations)** | CREATE, INSERT, SELECT, DELETE on SQLite |
| **Asynchronous JavaScript** | `async/await` + `fetch()` for non-blocking API calls |
| **Data Visualization** | Chart.js bar, doughnut, and line charts |
| **Responsive Design** | CSS media queries, flexible layouts |
| **DNS Resolution** | Python `socket.getaddrinfo()` |
| **HTTP Protocol Analysis** | Inspecting response headers for CDN detection |
| **Statistical Analysis** | Mean, median, P95, standard deviation for load testing |
| **Database Migration** | Auto-detecting old schema and upgrading tables |

---

## 7. How to Run & Demo

```bash
# 1. Navigate to backend
cd cdn-analyzer/backend

# 2. Start the server
python app.py

# 3. Open in browser
# → http://127.0.0.1:5050

# 4. Register a new account, then login

# 5. Enter any URL (e.g., cloudflare.com) and click Analyze
```

### Quick Demo Script for Teacher:
1. Open the login page → show the professional UI
2. Register a new account → show form validation
3. Login → show redirect to dashboard with your name
4. Analyze **cloudflare.com** → show CDN detection, score, charts
5. Analyze **github.com** → compare results
6. Show the History table → data persists in SQLite
7. Click "Download Report" → generates a print-ready PDF
8. Logout → show session ends, redirects to login

---

## 8. Python Libraries Used

```
flask          → Web framework for building REST APIs
flask-cors     → Handling Cross-Origin Resource Sharing
requests       → Making HTTP requests to target websites
sqlite3        → Database operations (built into Python)
hashlib        → SHA-256 password hashing (built into Python)
secrets        → Cryptographic random number generation (built into Python)
socket         → DNS lookups (built into Python)
time           → Timing measurements (built into Python)
statistics     → Mean, median, stdev calculations (built into Python)
json           → JSON serialization (built into Python)
```

Only **3 external packages** needed: `flask`, `flask-cors`, `requests`. Everything else is built into Python!
