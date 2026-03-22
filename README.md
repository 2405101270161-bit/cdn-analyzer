# CDN Performance Analyzer

A **web-based tool** that analyzes the **CDN (Content Delivery Network) performance** of any website. 

## Features
- **CDN Detection**: Identifies which CDN a website uses (Cloudflare, AWS CloudFront, Akamai, etc.).
- **Performance Metrics**: Measures DNS time, connection time, TTFB, and total load time.
- **Cache Performance**: Checks hether the CDN is caching content properly.
- **Performance Scoring**: Provides a score (0–100) and a letter grade based on response times and caching.
- **Load Testing**: Simulates 20 rapid requests to test performance under load.
- **Visualizations**: Interactive charts display the timing breakdown, performance distribution, and load test results (powered by Chart.js).
- **Authentication**: Secure user registration and login using Flask sessions and password hashing.
- **History Tracking**: Saves previous analysis results securely to a SQLite database for each user.

## Technology Stack
- **Frontend**: HTML, Vanilla CSS (Dark Mode + Glassmorphism), JavaScript (Chart.js v4.4.1)
- **Backend**: Python + Flask
- **Database**: SQLite
- **HTTP/DNS Testing**: Python `requests` and `socket` libraries

## Project Structure
```
cdn-analyzer/
├── backend/
│   ├── app.py          # Flask API server
│   └── analyzer.py     # Core CDN analysis engine
├── frontend/
│   ├── login.html      # Login/Register page
│   ├── index.html      # Main dashboard
│   ├── style.css       # All styling
│   └── dashboard.js    # Frontend logic (API calls, charts)
├── database/
│   └── results.db      # SQLite database (auto-created)
└── reports/            # For PDF exports
```

## Installation & Usage

1. **Clone the repository and jump to the backend directory**
   ```bash
   git clone https://github.com/2405101270161-bit/cdn-analyzer.git
   cd cdn-analyzer/backend
   ```

2. **Install requirements**
   Ensure you have Python installed, then run:
   ```bash
   pip install flask flask-cors requests
   ```

3. **Start the server**
   ```bash
   python app.py
   ```

4. **Open the App**
   Open your browser and navigate to `http://127.0.0.1:5050`.

5. **Register, Login, and Analyze!**
   Register a new account or log in if you already have one. Enter a website URL (e.g., `cloudflare.com`) and click Analyze to view CDN details, performance metrics, and history.
