#!/usr/bin/env python3
"""
QUANTDESK Server v5 — Multi-user auth system
"""

from flask import Flask, jsonify, request, send_from_directory, redirect, session, render_template_string
from flask_cors import CORS
import yfinance as yf
import os, time, threading, glob, json, hashlib, secrets

app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get("SECRET_KEY", "quantdesk-secret-2026-xK9mZ")

# ── USERS DB (fichier JSON) ───────────────────────────────────────────────────
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin2026")

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

# ── LOGIN / REGISTER PAGE ─────────────────────────────────────────────────────
AUTH_PAGE = """
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QUANTDESK — Accès</title>
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{background:#f8fafc;font-family:'Courier New',monospace;display:flex;align-items:center;justify-content:center;min-height:100vh}
    .card{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:40px;width:100%;max-width:400px;box-shadow:0 4px 24px rgba(0,0,0,0.06)}
    .logo{font-size:20px;font-weight:900;letter-spacing:4px;color:#1e293b;margin-bottom:4px}
    .sub{font-size:10px;color:#64748b;letter-spacing:2px;margin-bottom:28px}
    .tabs{display:flex;gap:0;margin-bottom:24px;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden}
    .tab{flex:1;padding:9px;text-align:center;font-size:11px;font-weight:700;letter-spacing:1px;cursor:pointer;background:#f8fafc;color:#64748b;border:none;transition:all 0.2s}
    .tab.active{background:#2563eb;color:white}
    label{font-size:9px;color:#64748b;letter-spacing:2px;display:block;margin-bottom:6px;margin-top:14px}
    input{width:100%;padding:11px 14px;border:1px solid #e2e8f0;border-radius:7px;font-size:13px;font-family:monospace;background:#f8fafc;color:#1e293b;outline:none;transition:border 0.2s}
    input:focus{border-color:#2563eb}
    button[type=submit]{width:100%;margin-top:18px;padding:12px;background:#2563eb;color:white;border:none;border-radius:7px;font-size:11px;font-weight:700;letter-spacing:2px;cursor:pointer}
    button[type=submit]:hover{background:#1d4ed8}
    .error{color:#e11d48;font-size:11px;margin-top:12px;text-align:center;padding:8px;background:#fff1f2;border-radius:5px}
    .success{color:#059669;font-size:11px;margin-top:12px;text-align:center;padding:8px;background:#f0fdf4;border-radius:5px}
    .info{font-size:10px;color:#64748b;text-align:center;margin-top:12px;line-height:1.6}
    #register-form{display:none}
  </style>
</head>
<body>
<div class="card">
  <div class="logo">QUANTDESK</div>
  <div class="sub">TRADING ALPHA · ACCÈS PRIVÉ</div>

  <div class="tabs">
    <button class="tab active" onclick="showTab('login')">CONNEXION</button>
    <button class="tab" onclick="showTab('register')">CRÉER COMPTE</button>
  </div>

  <form id="login-form" method="POST" action="/login">
    <input type="hidden" name="action" value="login">
    <label>IDENTIFIANT</label>
    <input type="text" name="username" placeholder="votre identifiant" autofocus required />
    <label>MOT DE PASSE</label>
    <input type="password" name="password" placeholder="••••••••••" required />
    <button type="submit">SE CONNECTER →</button>
  </form>

  <form id="register-form" method="POST" action="/login">
    <input type="hidden" name="action" value="register">
    <label>CHOISIR UN IDENTIFIANT</label>
    <input type="text" name="username" placeholder="ex: john_trader" required pattern="[a-zA-Z0-9_]{3,20}" title="3-20 caractères, lettres/chiffres/_"/>
    <label>CHOISIR UN MOT DE PASSE</label>
    <input type="password" name="password" placeholder="••••••••••" required minlength="6" />
    <label>CODE D'INVITATION</label>
    <input type="text" name="invite" placeholder="requis pour créer un compte" required />
    <button type="submit">CRÉER MON COMPTE →</button>
    <div class="info">Un code d'invitation est requis.<br>Contactez l'administrateur.</div>
  </form>

  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  {% if success %}<div class="success">{{ success }}</div>{% endif %}
</div>
<script>
function showTab(t){
  document.getElementById('login-form').style.display=t==='login'?'block':'none';
  document.getElementById('register-form').style.display=t==='register'?'block':'none';
  document.querySelectorAll('.tab').forEach((el,i)=>el.classList.toggle('active',(t==='login'&&i===0)||(t==='register'&&i===1)));
}
{% if tab == 'register' %}showTab('register');{% endif %}
</script>
</body>
</html>
"""

ADMIN_PAGE = """
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QUANTDESK — Admin</title>
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{background:#f8fafc;font-family:'Courier New',monospace;padding:24px}
    .header{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}
    .logo{font-size:18px;font-weight:900;letter-spacing:3px;color:#1e293b}
    a{color:#2563eb;text-decoration:none;font-size:11px}
    .card{background:white;border:1px solid #e2e8f0;border-radius:10px;padding:20px;margin-bottom:16px}
    h2{font-size:11px;letter-spacing:2px;color:#64748b;margin-bottom:16px}
    table{width:100%;border-collapse:collapse;font-size:12px}
    th{text-align:left;padding:8px 12px;font-size:9px;color:#64748b;letter-spacing:1px;border-bottom:1px solid #e2e8f0}
    td{padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#1e293b}
    .badge{display:inline-block;padding:2px 8px;border-radius:3px;font-size:9px;font-weight:700;letter-spacing:1px}
    .active{background:#d1fae5;color:#059669}
    .suspended{background:#fee2e2;color:#e11d48}
    .pending{background:#fef3c7;color:#d97706}
    form{display:inline}
    button{padding:4px 10px;border-radius:4px;cursor:pointer;font-size:10px;font-weight:700;border:1px solid;margin:0 2px}
    .btn-green{background:#d1fae5;color:#059669;border-color:#059669}
    .btn-red{background:#fee2e2;color:#e11d48;border-color:#e11d48}
    .btn-amber{background:#fef3c7;color:#d97706;border-color:#d97706}
    .btn-blue{background:#dbeafe;color:#2563eb;border-color:#2563eb}
    .invite-box{background:#f1f5f9;padding:14px;border-radius:7px;margin-top:12px}
    .invite-code{font-size:20px;font-weight:900;letter-spacing:6px;color:#2563eb;text-align:center;padding:10px}
  </style>
</head>
<body>
<div class="header">
  <div class="logo">QUANTDESK · ADMIN</div>
  <div><a href="/">← Dashboard</a> &nbsp; <a href="/logout">Déconnexion</a></div>
</div>

<div class="card">
  <h2>GESTION DES UTILISATEURS ({{ users|length }})</h2>
  <table>
    <thead>
      <tr><th>IDENTIFIANT</th><th>STATUT</th><th>CRÉÉ LE</th><th>DERNIÈRE CONNEXION</th><th>ACTIONS</th></tr>
    </thead>
    <tbody>
      {% for username, data in users.items() %}
      <tr>
        <td><b>{{ username }}</b></td>
        <td><span class="badge {{ data.status }}">{{ data.status.upper() }}</span></td>
        <td>{{ data.get('created', '—') }}</td>
        <td>{{ data.get('last_login', '—') }}</td>
        <td>
          {% if data.status != 'active' %}
          <form method="POST" action="/admin/action">
            <input type="hidden" name="username" value="{{ username }}">
            <input type="hidden" name="action" value="activate">
            <button class="btn-green" type="submit">✓ Activer</button>
          </form>
          {% endif %}
          {% if data.status == 'active' %}
          <form method="POST" action="/admin/action">
            <input type="hidden" name="username" value="{{ username }}">
            <input type="hidden" name="action" value="suspend">
            <button class="btn-amber" type="submit">⏸ Suspendre</button>
          </form>
          {% endif %}
          <form method="POST" action="/admin/action">
            <input type="hidden" name="username" value="{{ username }}">
            <input type="hidden" name="action" value="delete">
            <button class="btn-red" type="submit" onclick="return confirm('Supprimer {{ username }} ?')">✕ Révoquer</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<div class="card">
  <h2>GÉNÉRER UN CODE D'INVITATION</h2>
  <form method="POST" action="/admin/invite">
    <button class="btn-blue" type="submit">🔑 Générer un nouveau code</button>
  </form>
  {% if invite_code %}
  <div class="invite-box">
    <div style="font-size:10px;color:#64748b;text-align:center;margin-bottom:4px">PARTAGEZ CE CODE (usage unique)</div>
    <div class="invite-code">{{ invite_code }}</div>
    <div style="font-size:9px;color:#64748b;text-align:center;margin-top:4px">Valide 24h · expire {{ invite_expires }}</div>
  </div>
  {% endif %}
</div>
</body>
</html>
"""

# ── AUTH HELPERS ──────────────────────────────────────────────────────────────
def is_authenticated():
    return session.get("auth") and session.get("username")

def is_admin():
    return session.get("is_admin") == True

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

def require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_admin():
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

# ── LOGIN ROUTES ──────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET"])
def login_page():
    tab = request.args.get("tab", "login")
    return render_template_string(AUTH_PAGE, error=None, success=None, tab=tab)

@app.route("/login", methods=["POST"])
def login_post():
    action = request.form.get("action", "login")
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")

    # ── ADMIN LOGIN ──
    if username == "admin" and password == ADMIN_PASSWORD:
        session["auth"] = True
        session["username"] = "admin"
        session["is_admin"] = True
        return redirect("/admin")

    # ── REGISTER ──
    if action == "register":
        invite = request.form.get("invite", "").strip()
        invites = load_invites()
        now = time.time()
        valid = None
        for code, data in invites.items():
            if code == invite and data["expires"] > now and not data["used"]:
                valid = code
                break
        if not valid:
            return render_template_string(AUTH_PAGE, error="Code d'invitation invalide ou expiré.", success=None, tab="register")
        users = load_users()
        if username in users:
            return render_template_string(AUTH_PAGE, error="Cet identifiant est déjà pris.", success=None, tab="register")
        if len(username) < 3:
            return render_template_string(AUTH_PAGE, error="Identifiant trop court (min 3 caractères).", success=None, tab="register")
        users[username] = {
            "password": hash_password(password),
            "status": "active",
            "created": time.strftime("%d/%m/%Y %H:%M"),
            "last_login": None
        }
        save_users(users)
        invites[valid]["used"] = True
        save_invites(invites)
        return render_template_string(AUTH_PAGE, error=None, success=f"Compte créé ! Connectez-vous avec '{username}'.", tab="login")

    # ── LOGIN ──
    users = load_users()
    if username not in users:
        return render_template_string(AUTH_PAGE, error="Identifiant ou mot de passe incorrect.", success=None, tab="login")
    user = users[username]
    if user["status"] == "suspended":
        return render_template_string(AUTH_PAGE, error="Votre accès a été suspendu. Contactez l'administrateur.", success=None, tab="login")
    if user["password"] != hash_password(password):
        return render_template_string(AUTH_PAGE, error="Identifiant ou mot de passe incorrect.", success=None, tab="login")
    # Update last login
    users[username]["last_login"] = time.strftime("%d/%m/%Y %H:%M")
    save_users(users)
    session["auth"] = True
    session["username"] = username
    session["is_admin"] = False
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ── INVITE SYSTEM ──────────────────────────────────────────────────────────────
INVITES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "invites.json")

def load_invites():
    if os.path.exists(INVITES_FILE):
        with open(INVITES_FILE, "r") as f:
            return json.load(f)
    return {}

def save_invites(invites):
    with open(INVITES_FILE, "w") as f:
        json.dump(invites, f, indent=2)

# ── ADMIN ROUTES ───────────────────────────────────────────────────────────────
@app.route("/admin")
@require_admin
def admin_page():
    users = load_users()
    return render_template_string(ADMIN_PAGE, users=users, invite_code=None, invite_expires=None)

@app.route("/admin/action", methods=["POST"])
@require_admin
def admin_action():
    username = request.form.get("username")
    action = request.form.get("action")
    users = load_users()
    if username in users:
        if action == "activate":
            users[username]["status"] = "active"
        elif action == "suspend":
            users[username]["status"] = "suspended"
        elif action == "delete":
            del users[username]
        save_users(users)
    return redirect("/admin")

@app.route("/admin/invite", methods=["POST"])
@require_admin
def admin_invite():
    code = secrets.token_hex(4).upper()
    invites = load_invites()
    invites[code] = {
        "used": False,
        "expires": time.time() + 86400,
        "created": time.strftime("%d/%m/%Y %H:%M")
    }
    save_invites(invites)
    users = load_users()
    expires_str = time.strftime("%d/%m/%Y %H:%M", time.localtime(time.time() + 86400))
    return render_template_string(ADMIN_PAGE, users=users, invite_code=code, invite_expires=expires_str)

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

def fetch_with_retry(fn, retries=3, wait=5):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if "Rate" in str(e) or "429" in str(e):
                if attempt < retries - 1:
                    time.sleep(wait * (attempt + 1))
                    continue
            raise
    raise Exception("Rate limit persistant.")

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
        return "HTML non trouvé", 404
    response = send_from_directory(HTML_DIR, HTML_FILE)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response

@app.route("/<path:filename>")
def static_files(filename):
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
    print(f"  QUANTDESK Server v5 — Multi-user")
    print(f"  HTML: {HTML_FILE}")
    print(f"  Admin: http://localhost:8080/admin")
    print(f"  Mot de passe admin: {ADMIN_PASSWORD}")
    print("=" * 55)
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
