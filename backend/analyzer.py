"""
CDN Performance Analyzer Engine
================================
Core module for analyzing CDN performance, detecting providers,
measuring latency metrics, and generating improvement suggestions.
"""

import requests
import socket
import time
import statistics
from urllib.parse import urlparse
import concurrent.futures


# ─── CDN Detection Signatures ───────────────────────────────────────────────

CDN_SIGNATURES = {
    "Cloudflare": ["cf-ray", "cf-cache-status", "cf-request-id"],
    "AWS CloudFront": ["x-amz-cf-id", "x-amz-cf-pop", "x-cache"],
    "Akamai": ["x-akamai-transformed", "x-akamai-request-id", "akamai"],
    "Fastly": ["x-served-by", "x-cache", "x-cache-hits", "fastly"],
    "Google Cloud CDN": ["x-goog-", "via"],
    "Microsoft Azure CDN": ["x-msedge-ref", "x-azure-ref"],
    "KeyCDN": ["x-edge-location", "server"],
    "StackPath": ["x-sp-", "x-hw"],
    "Sucuri": ["x-sucuri-id", "x-sucuri-cache"],
    "Imperva / Incapsula": ["x-iinfo", "x-cdn"],
    "Netlify": ["x-nf-request-id", "server"],
    "Vercel": ["x-vercel-id", "x-vercel-cache", "server"],
    "BunnyCDN": ["cdn-pullzone", "cdn-uid", "server"],
}

CDN_SERVER_HINTS = {
    "cloudflare": "Cloudflare",
    "akamaighost": "Akamai",
    "akamaiedge": "Akamai",
    "amazons3": "AWS CloudFront",
    "cloudfront": "AWS CloudFront",
    "fastly": "Fastly",
    "google": "Google Cloud CDN",
    "netlify": "Netlify",
    "vercel": "Vercel",
    "bunnycdn": "BunnyCDN",
    "keycdn": "KeyCDN",
    "stackpath": "StackPath",
    "sucuri": "Sucuri",
    "incapsula": "Imperva / Incapsula",
}

CACHE_HEADERS = [
    "cf-cache-status",
    "x-cache",
    "x-vercel-cache",
    "x-drupal-cache",
    "x-varnish-cache",
    "x-proxy-cache",
    "x-cache-status",
]


# ─── Helper Functions ────────────────────────────────────────────────────────

def _normalise_url(url: str) -> str:
    """Ensure URL has a scheme."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _extract_domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname or parsed.path.split("/")[0]


# ─── DNS Lookup ──────────────────────────────────────────────────────────────

def dns_lookup(domain: str) -> float:
    """Return DNS resolution time in milliseconds."""
    start = time.perf_counter()
    try:
        socket.gethostbyname(domain)
    except socket.gaierror:
        pass
    end = time.perf_counter()
    return round((end - start) * 1000, 2)


# ─── CDN Detection ──────────────────────────────────────────────────────────

def detect_cdn(headers: dict) -> str:
    """Detect CDN provider from response headers."""
    headers_lower = {k.lower(): v.lower() for k, v in headers.items()}

    # Check specific header signatures
    for cdn, signatures in CDN_SIGNATURES.items():
        for sig in signatures:
            if sig.lower() in headers_lower:
                return cdn

    # Fallback: check server header
    server = headers_lower.get("server", "")
    for hint, cdn in CDN_SERVER_HINTS.items():
        if hint in server:
            return cdn

    return "No CDN Detected"


# ─── Cache Status ────────────────────────────────────────────────────────────

def parse_cache_status(headers: dict) -> str:
    """Extract cache status from response headers."""
    headers_lower = {k.lower(): v for k, v in headers.items()}
    for hdr in CACHE_HEADERS:
        if hdr in headers_lower:
            return headers_lower[hdr]
    
    # Check for DYNAMIC indicators if no explicit cache status
    cc = headers_lower.get("cache-control", "").lower()
    if "no-cache" in cc or "private" in cc or "max-age=0" in cc:
        return "DYNAMIC"
        
    return "N/A"


# ─── Full Analysis ───────────────────────────────────────────────────────────

def analyze_cdn(url: str) -> dict:
    """
    Run a full CDN performance analysis on the given URL.
    Returns a dictionary with all metrics.
    """
    url = _normalise_url(url)
    domain = _extract_domain(url)

    result = {
        "url": url,
        "domain": domain,
        "cdn": "Unknown",
        "dns_time": 0,
        "connect_time": 0,
        "ttfb": 0,
        "total_time": 0,
        "status_code": 0,
        "cache_status": "N/A",
        "content_size": 0,
        "edge_server": "N/A",
        "score": 0,
        "suggestions": [],
        "headers": {},
        "error": None,
    }

    # 1. DNS Lookup
    result["dns_time"] = dns_lookup(domain)

    # 2. HTTP Request with detailed timing
    try:
        session = requests.Session()

        # Warm-up DNS (already resolved above)
        t_start = time.perf_counter()
        response = session.get(url, timeout=15, allow_redirects=True, headers={
            "User-Agent": "CDN-Performance-Analyzer/1.0 (Research Tool)"
        })
        t_end = time.perf_counter()

        total_time = round((t_end - t_start) * 1000, 2)

        # Extract elapsed timing
        elapsed_ms = round(response.elapsed.total_seconds() * 1000, 2)

        # Approximate TTFB (time to first byte) — requests doesn't expose this
        # directly, so we estimate from elapsed vs total
        ttfb = round(elapsed_ms * 0.6, 2)  # heuristic
        connect_time = round(elapsed_ms * 0.15, 2)

        # Re-measure TTFB more precisely with a second request using stream
        try:
            t2_start = time.perf_counter()
            resp2 = session.get(url, timeout=15, stream=True, headers={
                "User-Agent": "CDN-Performance-Analyzer/1.0 (Research Tool)"
            })
            t2_first_byte = time.perf_counter()
            # Consume a tiny bit of content to ensure first byte
            _ = next(resp2.iter_content(1), None)
            t2_after_byte = time.perf_counter()
            resp2.close()

            ttfb = round((t2_after_byte - t2_start) * 1000, 2)
            connect_time = round((t2_first_byte - t2_start) * 1000 * 0.3, 2)
        except Exception:
            pass

        headers = dict(response.headers)
        result["status_code"] = response.status_code
        result["total_time"] = total_time
        result["ttfb"] = ttfb
        result["connect_time"] = connect_time
        result["cdn"] = detect_cdn(headers)
        result["cache_status"] = parse_cache_status(headers)
        result["content_size"] = len(response.content)
        result["edge_server"] = headers.get("server", headers.get("Server", "N/A"))
        result["headers"] = {k: v for k, v in headers.items()}

    except requests.exceptions.RequestException as e:
        result["error"] = str(e)
        result["score"] = 0
        result["suggestions"] = ["Could not reach the URL. Please check the address."]
        return result

    # 3. Calculate score
    result["score"] = calculate_score(result)

    # 4. Generate suggestions
    result["suggestions"] = get_suggestions(result)

    return result


# ─── Performance Score ───────────────────────────────────────────────────────

def calculate_score(metrics: dict) -> int:
    """
    Calculate a performance score (0–100) based on measured metrics.
    Weighted scoring penalizes high latency and cache misses.
    """
    score = 100.0

    # DNS penalty (ideal < 30ms)
    dns = metrics.get("dns_time", 0)
    if dns > 100:
        score -= 20
    elif dns > 50:
        score -= 10
    elif dns > 30:
        score -= 5

    # TTFB penalty (ideal < 100ms)
    ttfb = metrics.get("ttfb", 0)
    if ttfb > 500:
        score -= 25
    elif ttfb > 300:
        score -= 15
    elif ttfb > 100:
        score -= 8

    # Total time penalty (ideal < 200ms)
    total = metrics.get("total_time", 0)
    if total > 2000:
        score -= 25
    elif total > 1000:
        score -= 15
    elif total > 500:
        score -= 8
    elif total > 200:
        score -= 3

    # Cache penalty
    cache = metrics.get("cache_status", "N/A").upper()
    if cache == "MISS":
        score -= 10
    elif cache == "EXPIRED":
        score -= 7
    elif cache in ("N/A", "UNKNOWN"):
        score -= 3

    # No CDN penalty
    if metrics.get("cdn") in ("No CDN Detected", "Unknown"):
        score -= 10

    # Content size penalty (ideal < 500KB)
    size_kb = metrics.get("content_size", 0) / 1024
    if size_kb > 5000:
        score -= 10
    elif size_kb > 2000:
        score -= 5

    return max(0, min(100, int(score)))


# ─── Improvement Suggestions ────────────────────────────────────────────────

def get_suggestions(metrics: dict) -> list:
    """Generate actionable performance improvement suggestions."""
    suggestions = []

    if metrics.get("cdn") in ("No CDN Detected", "Unknown"):
        suggestions.append({
            "type": "critical",
            "title": "No CDN Detected",
            "detail": "Consider deploying a CDN (Cloudflare, CloudFront, Fastly) to reduce latency and improve global performance."
        })

    cache = metrics.get("cache_status", "N/A").upper()
    if cache == "MISS":
        suggestions.append({
            "type": "warning",
            "title": "Cache MISS Detected",
            "detail": "The response was served from origin. Configure cache-control headers and CDN caching rules to improve hit ratio."
        })
    elif cache == "EXPIRED":
        suggestions.append({
            "type": "warning",
            "title": "Cache EXPIRED",
            "detail": "Increase cache TTL values to reduce origin fetches and improve response times."
        })
    elif cache in ("N/A", "UNKNOWN"):
        suggestions.append({
            "type": "info",
            "title": "No Cache Headers Found",
            "detail": "Add Cache-Control and ETag headers to enable CDN and browser caching."
        })

    if metrics.get("ttfb", 0) > 300:
        suggestions.append({
            "type": "critical",
            "title": "High TTFB (> 300ms)",
            "detail": "Time to First Byte is high. Optimize server processing, use edge computing, or enable server-side caching."
        })
    elif metrics.get("ttfb", 0) > 100:
        suggestions.append({
            "type": "info",
            "title": "TTFB Could Be Improved",
            "detail": "TTFB is acceptable but could be optimized further with edge caching or server tuning."
        })

    if metrics.get("dns_time", 0) > 50:
        suggestions.append({
            "type": "warning",
            "title": "Slow DNS Resolution",
            "detail": "DNS lookup is slow. Consider using a faster DNS provider or enabling DNS prefetching."
        })

    if metrics.get("total_time", 0) > 1000:
        suggestions.append({
            "type": "critical",
            "title": "Slow Response Time (> 1s)",
            "detail": "Total response time is high. Enable compression (gzip/brotli), optimize assets, and leverage CDN edge caching."
        })

    size_kb = metrics.get("content_size", 0) / 1024
    if size_kb > 2000:
        suggestions.append({
            "type": "warning",
            "title": "Large Response Size",
            "detail": f"Response is {size_kb:.0f} KB. Enable compression, minify assets, and lazy-load images to reduce payload."
        })

    if not suggestions:
        suggestions.append({
            "type": "success",
            "title": "Excellent Performance",
            "detail": "No major issues detected. Your website has good CDN configuration and performance."
        })

    return suggestions


# ─── Load Testing ────────────────────────────────────────────────────────────

def load_test(url: str, count: int = 20) -> dict:
    """
    Perform a load test by sending sequential HTTP requests.
    Returns timing statistics.
    """
    url = _normalise_url(url)
    count = min(max(count, 5), 50)  # clamp between 5-50

    times = []
    statuses = []
    errors = 0

    for i in range(count):
        try:
            start = time.perf_counter()
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "CDN-Performance-Analyzer/1.0 (Load Test)"
            })
            end = time.perf_counter()
            elapsed = round((end - start) * 1000, 2)
            times.append(elapsed)
            statuses.append(resp.status_code)
        except Exception:
            errors += 1
            times.append(0)
            statuses.append(0)

    valid_times = [t for t in times if t > 0]

    if not valid_times:
        return {
            "url": url,
            "total_requests": count,
            "successful": 0,
            "failed": errors,
            "times": times,
            "avg": 0,
            "min": 0,
            "max": 0,
            "median": 0,
            "p95": 0,
            "std_dev": 0,
            "success_rate": 0,
        }

    sorted_times = sorted(valid_times)
    p95_index = int(len(sorted_times) * 0.95)

    return {
        "url": url,
        "total_requests": count,
        "successful": len(valid_times),
        "failed": errors,
        "times": times,
        "avg": round(statistics.mean(valid_times), 2),
        "min": round(min(valid_times), 2),
        "max": round(max(valid_times), 2),
        "median": round(statistics.median(valid_times), 2),
        "p95": round(sorted_times[min(p95_index, len(sorted_times) - 1)], 2),
        "std_dev": round(statistics.stdev(valid_times), 2) if len(valid_times) > 1 else 0,
        "success_rate": round(len(valid_times) / count * 100, 1),
    }

# ─── Global Latency Simulation ───────────────────────────────────────────────

def simulate_global_latency(base_ttfb: float) -> list:
    """
    Simulate latency from different global regions based on the actual TTFB.
    Helps visualize global CDN performance.
    """
    import random
    
    # If using a CDN, TTFB is likely from the closest edge, so we add some hop latencies.
    # If high TTFB everywhere, origin is slow or no CDN.
    
    regions = [
        {"id": "na-east", "name": "US East (Virginia)", "lat": 39.04, "lng": -77.48},
        {"id": "na-west", "name": "US West (California)", "lat": 37.33, "lng": -121.89},
        {"id": "eu-central", "name": "Europe (Frankfurt)", "lat": 50.11, "lng": 8.68},
        {"id": "eu-west", "name": "Europe (London)", "lat": 51.50, "lng": -0.12},
        {"id": "asia-ea", "name": "Asia Pacific (Tokyo)", "lat": 35.67, "lng": 139.65},
        {"id": "asia-se", "name": "Asia Pacific (Singapore)", "lat": 1.35, "lng": 103.81},
        {"id": "asia-sa", "name": "Asia Pacific (Mumbai)", "lat": 19.07, "lng": 72.87},
        {"id": "sa-east", "name": "South America (São Paulo)", "lat": -23.55, "lng": -46.63},
        {"id": "af-south", "name": "Africa (Cape Town)", "lat": -33.92, "lng": 18.42},
        {"id": "oceania", "name": "Oceania (Sydney)", "lat": -33.86, "lng": 151.20},
    ]

    results = []
    
    # Randomly pick a "home" region close to the base_ttfb to simulate origin/edge
    home_region = random.choice(regions)
    
    for r in regions:
        if r["id"] == home_region["id"]:
            sim_ttfb = base_ttfb
        else:
            # Add synthetic latency
            distance_penalty = random.uniform(20.0, 150.0)
            if base_ttfb < 50:
                # Likely a good CDN, latency is mostly low globally
                distance_penalty = random.uniform(10.0, 60.0)
                
            sim_ttfb = base_ttfb + distance_penalty
        
        # Color coding
        if sim_ttfb < 100:
            status = "fast"
            color = "#00e676"  # Green
        elif sim_ttfb < 300:
            status = "medium"
            color = "#ffea00"  # Yellow
        else:
            status = "slow"
            color = "#ff3d00"  # Red
            
        results.append({
            "id": r["id"],
            "name": r["name"],
            "lat": r["lat"],
            "lng": r["lng"],
            "ttfb": round(sim_ttfb, 2),
            "status": status,
            "color": color
        })
        
    return results
