#!/usr/bin/env python3
"""
QUANTDESK Local Server v4 — cache + retry + password protection
"""

from flask import Flask, jsonify, request, send_from_directory, redirect, url_for, session, render_template_string
from flask_cors import CORS
import yfinance as yf
import os, time, threading, glob, hashlib

app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get("SECRET_KEY", "quantdesk-secret-2026")

# ── PASSWORD CONFIG ───────────────────────────────────────────────────────────
# Set via environment variable on Render: PASSWORD=yourpassword
APP_PASSWORD = os.environ.get("PASSWORD", "trading2026")

LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QUANTDESK — Accès</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #f8fafc; font-family: 'Courier New', monospace; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
    .card { background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 48px 40px; width: 100%; max-width: 380px; box-shadow: 0 4px 24px rgba(0,0,0,0.06); }
    .logo { font-size: 22px; font-weight: 900; letter-spacing: 4px; color: #1e293b; margin-bottom: 8px; }
    .sub { font-size: 11px; color: #64748b; letter-spacing: 2px; margin-bottom: 36px; }
    label { font-size: 10px; color: #64748b; letter-spacing: 2px; display: block; margin-bottom: 8px; }
    input { width: 100%; padding: 12px 16px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 14px; font-family: monospace; background: #f8fafc; color: #1e293b; outline: none; transition: border 0.2s; }
    input:focus { border-color: #2563eb; }
    button { width: 100%; margin-top: 20px; padding: 13px; background: #2563eb; color: white; border: none; border-radius: 8px; font-size: 12px; font-weight: 700; letter-spacing: 2px; cursor: pointer; transition: background 0.2s; }
    button:hover { background: #1d4ed8; }
    .error { color: #e11d48; font-size: 11px; margin-top: 14px; text-align: center; }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">QUANTDESK</div>
    <div class="sub">TRADING ALPHA · ACCÈS PRIVÉ</div>
    <form method="POST" action="/login">
      <label>MOT DE PASSE</label>
      <input type="password" name="password" placeholder="••••••••••" autofocus />
      <button type="submit">ACCÉDER →</button>
      {% if error %}<div class="error">{{ error }}</div>{% endif %}
    </form>
  </div>
</body>
</html>
"""

# ── AUTH HELPERS ──────────────────────────────────────────────────────────────
def is_authenticated():
    return session.get("auth") == True

def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

def require_auth_api(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            return jsonify({"error": "Non autorisé"}), 401
        return f(*args, **kwargs)
    return decorated

# ── LOGIN ROUTES ──────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET"])
def login_page():
    return render_template_string(LOGIN_PAGE, error=None)

@app.route("/login", methods=["POST"])
def login_post():
    pwd = request.form.get("password", "")
    if pwd == APP_PASSWORD:
        session["auth"] = True
        return redirect("/")
    return render_template_string(LOGIN_PAGE, error="Mot de passe incorrect")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ── CACHE ─────────────────────────────────────────────────────────────────────
_cache = {}
_lock  = threading.Lock()
CACHE_TTL = {"5m": 60, "10m": 120, "1h": 300, "1d": 3600, "quote": 30}

def cache_get(key):
    with _lock:
        if key in _cache:
            data, ts, ttl = _cache[key]
            if time.time() - ts < ttl:
                return data
    return None

def cache_set(key, data, ttl):
    with _lock:
        _cache[key] = (data, time.time(), ttl)

# ── RETRY ─────────────────────────────────────────────────────────────────────
def fetch_with_retry(fn, retries=3, wait=5):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            if "Rate" in msg or "429" in msg or "Too Many" in msg:
                if attempt < retries - 1:
                    time.sleep(wait * (attempt + 1))
                    continue
            raise
    raise Exception("Rate limit persistant. Attendez 30s.")

# ── STATIC ────────────────────────────────────────────────────────────────────
HTML_DIR = os.path.dirname(os.path.abspath(__file__))

def find_html():
    for pat in ["quant-desk*.html", "index.html", "*.html"]:
        matches = glob.glob(os.path.join(HTML_DIR, pat))
        if matches:
            return os.path.basename(sorted(matches)[-1])
    return None

HTML_FILE = find_html()

@app.route("/")
@require_auth
def index():
    if not HTML_FILE:
        return "HTML non trouvé dans " + HTML_DIR, 404
    response = send_from_directory(HTML_DIR, HTML_FILE)
response.headers["Content-Type"] = "text/html; charset=utf-8"
return response

@app.route("/<path:filename>")
def static_files(filename):
    if filename in ("login", "logout", "api"):
        return redirect("/login")
    fp = os.path.join(HTML_DIR, filename)
    if os.path.exists(fp):
        return send_from_directory(HTML_DIR, filename)
    return f"Not found: {filename}", 404

# ── API ───────────────────────────────────────────────────────────────────────
DEFAULT_RANGE = {"5m": "5d", "10m": "5d", "1h": "1mo", "1d": "5y"}

@app.route("/api/chart")
@require_auth_api
def chart():
    ticker   = request.args.get("ticker", "").upper()
    interval = request.args.get("interval", "1d")
    range_   = request.args.get("range", DEFAULT_RANGE.get(interval, "5y"))
    if not ticker:
        return jsonify({"error": "ticker manquant"}), 400
    cache_key = f"chart_{ticker}_{interval}_{range_}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)
    try:
        hist = fetch_with_retry(lambda: yf.Ticker(ticker).history(period=range_, interval=interval, auto_adjust=True))
        if hist.empty:
            return jsonify({"error": f"Pas de données pour {ticker}"}), 404
        data = {
            "ticker": ticker, "interval": interval, "range": range_,
            "closes":  [round(float(v), 4) for v in hist["Close"].tolist()],
            "dates":   [str(d) for d in hist.index.tolist()],
            "opens":   [round(float(v), 4) for v in hist["Open"].tolist()],
            "highs":   [round(float(v), 4) for v in hist["High"].tolist()],
            "lows":    [round(float(v), 4) for v in hist["Low"].tolist()],
            "volumes": [int(v) for v in hist["Volume"].tolist()],
        }
        cache_set(cache_key, data, CACHE_TTL.get(interval, 3600))
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/quote")
@require_auth_api
def quote():
    symbols = [s.strip().upper() for s in request.args.get("symbols", "").split(",") if s.strip()]
    if not symbols:
        return jsonify({"error": "symbols manquants"}), 400
    cache_key = "quote_" + "_".join(sorted(symbols))
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)
    out = {}
    for sym in symbols:
        try:
            def do_q(s=sym):
                info = yf.Ticker(s).fast_info
                price = float(info.last_price or 0)
                prev  = float(info.previous_close or price)
                vol   = int(info.three_month_average_volume or 0)
                return {
                    "regularMarketPrice": round(price, 4),
                    "regularMarketChangePercent": round((price-prev)/prev*100 if prev else 0, 4),
                    "regularMarketVolume": vol
                }
            out[sym] = fetch_with_retry(do_q, retries=2, wait=3)
        except Exception as e:
            out[sym] = {"error": str(e)}
        time.sleep(0.3)
    cache_set(cache_key, out, CACHE_TTL["quote"])
    return jsonify(out)

@app.route("/api/status")
def status():
    return jsonify({"ok": True, "html": HTML_FILE, "cache_keys": len(_cache)})

@app.route("/api/clear-cache")
@require_auth_api
def clear_cache():
    with _lock: _cache.clear()
    return jsonify({"ok": True})

if __name__ == "__main__":
    print("=" * 55)
    print(f"  QUANTDESK Server v4 — Password Protected")
    print(f"  HTML: {HTML_FILE}")
    print(f"  Mot de passe: {APP_PASSWORD}")
    print(f"  Ouvrir: http://localhost:8080")
    print("=" * 55)
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
