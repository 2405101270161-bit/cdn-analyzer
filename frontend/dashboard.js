/* ═════════════════════════════════════════════════════════════════════════
   CDN Performance Analyzer — Dashboard Logic
   ═════════════════════════════════════════════════════════════════════════ */

const API = "";  // same origin

// ─── Chart instances (for cleanup) ──────────────────────────────────────
let chartTiming = null;
let chartDist = null;
let chartLoadtest = null;

// ─── State ──────────────────────────────────────────────────────────────
let lastResult = null;

// ─── Helpers ────────────────────────────────────────────────────────────
function $(id) { return document.getElementById(id); }
function show(id) { $(id).style.display = ""; }
function hide(id) { $(id).style.display = "none"; }

function setUrl(u) {
    $("url-input").value = u;
    $("url-input").focus();
}

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(2) + " MB";
}

function formatTime(t) {
    return t < 1000 ? t.toFixed(1) + " ms" : (t / 1000).toFixed(2) + " s";
}

function getGradeInfo(score) {
    if (score >= 90) return { grade: "A+  Excellent", cls: "grade-a" };
    if (score >= 80) return { grade: "A   Great",     cls: "grade-a" };
    if (score >= 70) return { grade: "B   Good",      cls: "grade-b" };
    if (score >= 60) return { grade: "C   Average",   cls: "grade-c" };
    if (score >= 40) return { grade: "D   Poor",      cls: "grade-d" };
    return                   { grade: "F   Critical",  cls: "grade-f" };
}

function scorePillClass(s) {
    if (s >= 80) return "score-pill-good";
    if (s >= 60) return "score-pill-ok";
    if (s >= 40) return "score-pill-meh";
    return "score-pill-bad";
}

function cacheClass(status) {
    const s = (status || "").toUpperCase();
    if (s === "HIT") return "cache-hit";
    if (s === "MISS") return "cache-miss";
    return "cache-other";
}

// ─── Loading Animation ──────────────────────────────────────────────────
let loadingInterval = null;

function startLoading(text) {
    $("loading-text").textContent = text || "Analyzing CDN performance…";
    show("loading-section");
    hide("results-section");

    const steps = $("loading-steps").children;
    let idx = 0;
    for (let s of steps) { s.classList.remove("active", "done"); }
    steps[0].classList.add("active");

    loadingInterval = setInterval(() => {
        if (idx < steps.length) {
            steps[idx].classList.remove("active");
            steps[idx].classList.add("done");
        }
        idx++;
        if (idx < steps.length) {
            steps[idx].classList.add("active");
        } else {
            clearInterval(loadingInterval);
        }
    }, 600);
}

function stopLoading() {
    clearInterval(loadingInterval);
    hide("loading-section");
    const steps = $("loading-steps").children;
    for (let s of steps) {
        s.classList.remove("active");
        s.classList.add("done");
    }
}

// ─── Analyze URL ────────────────────────────────────────────────────────
async function analyzeUrl() {
    let url = $("url-input").value.trim();
    if (!url) { $("url-input").focus(); return; }

    // Disable buttons
    $("btn-analyze").disabled = true;
    $("btn-loadtest").disabled = true;

    startLoading("Analyzing " + url + " …");

    try {
        const resp = await fetch(API + "/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ url: url })
        });
        if (resp.status === 401) { window.location.href = "/"; return; }
        const data = await resp.json();

        if (data.error) {
            stopLoading();
            alert("Error: " + data.error);
            return;
        }

        lastResult = data;
        renderResults(data);
        loadHistory();

    } catch (err) {
        stopLoading();
        alert("Network error: " + err.message);
    } finally {
        $("btn-analyze").disabled = false;
        $("btn-loadtest").disabled = false;
    }
}

// ─── Render Results ─────────────────────────────────────────────────────
function renderResults(data) {
    stopLoading();
    show("results-section");
    show("report-actions");

    // Animate sections in
    const sections = document.querySelectorAll(".results-section > *");
    sections.forEach((s, i) => {
        s.classList.add("animate-in", "delay-" + Math.min(i + 1, 5));
    });

    // ── Score ──
    const circumference = 2 * Math.PI * 70;  // r=70
    const dashLen = (data.score / 100) * circumference;
    $("score-fill").setAttribute("stroke-dasharray", dashLen + " " + circumference);
    animateCounter("score-value", data.score);

    const gi = getGradeInfo(data.score);
    $("score-grade").textContent = gi.grade;
    $("score-grade").className = "score-grade " + gi.cls;

    // ── Overview ──
    $("ov-url").textContent = data.domain || data.url;
    $("ov-cdn").textContent = data.cdn || "Unknown";
    $("ov-edge").textContent = data.edge_server || "N/A";
    $("ov-status").textContent = data.status_code || "—";
    $("ov-size").textContent = formatBytes(data.content_size || 0);

    const cacheEl = $("ov-cache");
    cacheEl.textContent = data.cache_status || "N/A";
    cacheEl.className = "overview-value cache-status " + cacheClass(data.cache_status);

    // ── Metrics ──
    $("m-dns").textContent = formatTime(data.dns_time || 0);
    $("m-connect").textContent = formatTime(data.connect_time || 0);
    $("m-ttfb").textContent = formatTime(data.ttfb || 0);
    $("m-total").textContent = formatTime(data.total_time || 0);

    // Metric bars (normalise to max 500ms = 100%)
    const maxMs = 500;
    setTimeout(() => {
        $("bar-dns").style.width     = Math.min(100, (data.dns_time / maxMs) * 100) + "%";
        $("bar-connect").style.width = Math.min(100, (data.connect_time / maxMs) * 100) + "%";
        $("bar-ttfb").style.width    = Math.min(100, (data.ttfb / maxMs) * 100) + "%";
        $("bar-total").style.width   = Math.min(100, (data.total_time / maxMs) * 100) + "%";
    }, 200);

    // ── Timing Chart ──
    renderTimingChart(data);

    // ── Distribution Chart ──
    renderDistributionChart(data);

    // ── Suggestions ──
    renderSuggestions(data.suggestions || []);

    // ── Headers ──
    if (data.headers) {
        const hdr = Object.entries(data.headers)
            .map(([k, v]) => k + ": " + v)
            .join("\n");
        $("headers-code").textContent = hdr;
    }
}

// ─── Animated Counter ───────────────────────────────────────────────────
function animateCounter(id, target) {
    const el = $(id);
    let current = 0;
    const step = Math.max(1, Math.floor(target / 40));
    const interval = setInterval(() => {
        current += step;
        if (current >= target) {
            current = target;
            clearInterval(interval);
        }
        el.textContent = current;
    }, 30);
}

// ─── Charts ─────────────────────────────────────────────────────────────

const chartDefaults = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            labels: { color: "#8494a7", font: { family: "'Inter'", size: 11 } }
        }
    },
    scales: {
        x: {
            ticks: { color: "#8494a7", font: { family: "'Inter'", size: 11 } },
            grid: { color: "rgba(255,255,255,0.04)" }
        },
        y: {
            ticks: { color: "#8494a7", font: { family: "'Inter'", size: 11 } },
            grid: { color: "rgba(255,255,255,0.04)" }
        }
    }
};

function renderTimingChart(data) {
    if (chartTiming) chartTiming.destroy();
    const ctx = $("chart-timing").getContext("2d");

    chartTiming = new Chart(ctx, {
        type: "bar",
        data: {
            labels: ["DNS Lookup", "TCP Connect", "TTFB", "Total Time"],
            datasets: [{
                label: "Time (ms)",
                data: [data.dns_time, data.connect_time, data.ttfb, data.total_time],
                backgroundColor: [
                    "rgba(0, 212, 255, 0.7)",
                    "rgba(123, 47, 255, 0.7)",
                    "rgba(255, 60, 172, 0.7)",
                    "rgba(0, 230, 118, 0.7)"
                ],
                borderColor: [
                    "rgba(0, 212, 255, 1)",
                    "rgba(123, 47, 255, 1)",
                    "rgba(255, 60, 172, 1)",
                    "rgba(0, 230, 118, 1)"
                ],
                borderWidth: 2,
                borderRadius: 8,
                borderSkipped: false
            }]
        },
        options: {
            ...chartDefaults,
            plugins: {
                ...chartDefaults.plugins,
                legend: { display: false }
            }
        }
    });
}

function renderDistributionChart(data) {
    if (chartDist) chartDist.destroy();
    const ctx = $("chart-distribution").getContext("2d");

    chartDist = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: ["DNS", "TCP Connect", "TTFB", "Download"],
            datasets: [{
                data: [
                    data.dns_time,
                    data.connect_time,
                    data.ttfb,
                    Math.max(0, data.total_time - data.ttfb)
                ],
                backgroundColor: [
                    "rgba(0, 212, 255, 0.8)",
                    "rgba(123, 47, 255, 0.8)",
                    "rgba(255, 60, 172, 0.8)",
                    "rgba(0, 230, 118, 0.8)"
                ],
                borderColor: "rgba(6, 8, 15, 0.8)",
                borderWidth: 3,
                hoverOffset: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "65%",
            plugins: {
                legend: {
                    position: "bottom",
                    labels: { color: "#8494a7", font: { family: "'Inter'", size: 11 }, padding: 16 }
                }
            }
        }
    });
}

// ─── Suggestions ────────────────────────────────────────────────────────
function renderSuggestions(suggestions) {
    const list = $("suggestions-list");
    const icons = {
        critical: "🔴",
        warning:  "🟡",
        info:     "🔵",
        success:  "🟢"
    };

    list.innerHTML = suggestions.map(s => `
        <div class="suggestion-item sug-${s.type}">
            <div class="sug-icon">${icons[s.type] || "ℹ️"}</div>
            <div class="sug-content">
                <div class="sug-title">${s.title}</div>
                <div class="sug-detail">${s.detail}</div>
            </div>
        </div>
    `).join("");
}

// ─── Load Test ──────────────────────────────────────────────────────────
async function runLoadTest() {
    let url = $("url-input").value.trim();
    if (!url) { $("url-input").focus(); return; }

    $("btn-analyze").disabled = true;
    $("btn-loadtest").disabled = true;
    startLoading("Running load test (" + url + ") — 20 requests…");

    try {
        const resp = await fetch(API + "/api/loadtest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ url: url, count: 20 })
        });
        if (resp.status === 401) { window.location.href = "/"; return; }
        const data = await resp.json();
        stopLoading();
        renderLoadTest(data);

    } catch (err) {
        stopLoading();
        alert("Load test error: " + err.message);
    } finally {
        $("btn-analyze").disabled = false;
        $("btn-loadtest").disabled = false;
    }
}

function renderLoadTest(data) {
    show("loadtest-section");
    $("loadtest-section").scrollIntoView({ behavior: "smooth", block: "start" });

    // Stats grid
    $("loadtest-stats").innerHTML = [
        { label: "Total Requests", value: data.total_requests },
        { label: "Successful",     value: data.successful },
        { label: "Failed",         value: data.failed },
        { label: "Average",        value: formatTime(data.avg) },
        { label: "Minimum",        value: formatTime(data.min) },
        { label: "Maximum",        value: formatTime(data.max) },
        { label: "Median",         value: formatTime(data.median) },
        { label: "P95",            value: formatTime(data.p95) },
        { label: "Std Dev",        value: formatTime(data.std_dev) },
        { label: "Success Rate",   value: data.success_rate + "%" }
    ].map(s => `
        <div class="lt-stat">
            <div class="lt-stat-value">${s.value}</div>
            <div class="lt-stat-label">${s.label}</div>
        </div>
    `).join("");

    // Chart
    if (chartLoadtest) chartLoadtest.destroy();
    const ctx = $("chart-loadtest").getContext("2d");
    const labels = data.times.map((_, i) => "Req " + (i + 1));

    chartLoadtest = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Response Time (ms)",
                    data: data.times,
                    borderColor: "rgba(0, 212, 255, 1)",
                    backgroundColor: "rgba(0, 212, 255, 0.1)",
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointBackgroundColor: "rgba(0, 212, 255, 1)",
                    pointBorderColor: "#0a0e17",
                    pointBorderWidth: 2
                },
                {
                    label: "Average",
                    data: Array(data.times.length).fill(data.avg),
                    borderColor: "rgba(255, 171, 0, 0.6)",
                    borderDash: [6, 4],
                    pointRadius: 0,
                    fill: false
                }
            ]
        },
        options: {
            ...chartDefaults,
            plugins: {
                ...chartDefaults.plugins,
                legend: {
                    labels: { color: "#8494a7", font: { family: "'Inter'", size: 11 } }
                }
            }
        }
    });
}

// ─── History ────────────────────────────────────────────────────────────
async function loadHistory() {
    try {
        const resp = await fetch(API + "/api/history", { credentials: "include" });
        if (resp.status === 401) { window.location.href = "/"; return; }
        const rows = await resp.json();
        const tbody = $("history-body");

        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-row">No analyses yet. Enter a URL above to get started.</td></tr>';
            return;
        }

        tbody.innerHTML = rows.map(r => {
            const pillCls = scorePillClass(r.score);
            const ts = r.timestamp ? new Date(r.timestamp + "Z").toLocaleString() : "—";
            return `<tr>
                <td>${r.domain || r.url}</td>
                <td>${r.cdn || "—"}</td>
                <td>${(r.dns_time || 0).toFixed(1)} ms</td>
                <td>${(r.ttfb || 0).toFixed(1)} ms</td>
                <td>${(r.total_time || 0).toFixed(1)} ms</td>
                <td>${r.cache_status || "—"}</td>
                <td><span class="score-pill ${pillCls}">${r.score}</span></td>
                <td>${ts}</td>
            </tr>`;
        }).join("");

    } catch (err) {
        console.warn("Could not load history:", err);
    }
}

async function clearHistory() {
    if (!confirm("Clear all analysis history?")) return;
    try {
        await fetch(API + "/api/history/clear", { method: "DELETE", credentials: "include" });
        loadHistory();
    } catch (err) {
        console.warn("Could not clear history:", err);
    }
}

// ─── Print Report ───────────────────────────────────────────────────────
function printReport() {
    window.print();
}

// ─── Logout ─────────────────────────────────────────────────────────────
async function logoutUser() {
    try {
        await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    } catch(e) {}
    window.location.href = "/";
}

// ─── Auth Check + Init ─────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
    // Check authentication
    try {
        const resp = await fetch("/api/auth/me", { credentials: "include" });
        if (resp.ok) {
            const data = await resp.json();
            if (data.user && data.user.fullname) {
                $("user-name").textContent = data.user.fullname;
                $("user-pill").style.display = "flex";
            }
        } else {
            window.location.href = "/";
            return;
        }
    } catch(e) {
        window.location.href = "/";
        return;
    }

    $("url-input").addEventListener("keydown", (e) => {
        if (e.key === "Enter") analyzeUrl();
    });
    loadHistory();
});
