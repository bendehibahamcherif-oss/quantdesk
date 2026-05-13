#!/usr/bin/env python3
"""QUANTDESK Server v6 — Multi-user + reset password + sessions actives"""

from flask import Flask, jsonify, request, send_from_directory, redirect, session, render_template_string
from flask_cors import CORS
import yfinance as yf
import os, time, threading, glob, json, hashlib, secrets

app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get("SECRET_KEY", "quantdesk-secret-2026-xK9mZ")
app.config["SESSION_PERMANENT"] = False          # session expire à la fermeture du navigateur
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True

USERS_FILE   = os.environ.get('USERS_FILE', '/data/users.json')
INVITES_FILE = os.environ.get('INVITES_FILE', '/data/invites.json')
RESETS_FILE  = os.environ.get('RESETS_FILE', '/data/resets.json')
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin2026")

# ── SESSIONS ACTIVES (en mémoire) ─────────────────────────────────────────────
_active_sessions = {}  # {session_id: {username, login_time, last_seen}}

def track_session(username):
    sid = session.get('_id')
    if not sid:
        sid = secrets.token_hex(8)
        session['_id'] = sid
    _active_sessions[sid] = {
        'username': username,
        'login_time': time.strftime("%d/%m/%Y %H:%M"),
        'last_seen': time.strftime("%H:%M:%S")
    }

def untrack_session():
    sid = session.get('_id')
    if sid and sid in _active_sessions:
        del _active_sessions[sid]

def update_last_seen():
    sid = session.get('_id')
    if sid and sid in _active_sessions:
        _active_sessions[sid]['last_seen'] = time.strftime("%H:%M:%S")

def get_active_sessions():
    return list(_active_sessions.values())

# ── JSON HELPERS ──────────────────────────────────────────────────────────────
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE) as f: return json.load(f)
    return {}

def save_users(u):
    with open(USERS_FILE, "w") as f: json.dump(u, f, indent=2)

def load_invites():
    if os.path.exists(INVITES_FILE):
        with open(INVITES_FILE) as f: return json.load(f)
    return {}

def save_invites(i):
    with open(INVITES_FILE, "w") as f: json.dump(i, f, indent=2)

def load_resets():
    if os.path.exists(RESETS_FILE):
        with open(RESETS_FILE) as f: return json.load(f)
    return {}

def save_resets(r):
    with open(RESETS_FILE, "w") as f: json.dump(r, f, indent=2)

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

# ── AUTH HELPERS ──────────────────────────────────────────────────────────────
def is_authenticated():
    return session.get("auth") and session.get("username")

def is_admin():
    return session.get("is_admin") == True

def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated(): return redirect("/login")
        update_last_seen()
        return f(*args, **kwargs)
    return decorated

def require_auth_api(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated(): return jsonify({"error": "Non autorisé"}), 401
        update_last_seen()
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_admin(): return redirect("/login")
        return f(*args, **kwargs)
    return decorated

# ── AUTH PAGES ────────────────────────────────────────────────────────────────
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
    .card{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:36px;width:100%;max-width:400px;box-shadow:0 4px 24px rgba(0,0,0,0.06)}
    .logo{font-size:20px;font-weight:900;letter-spacing:4px;color:#1e293b;margin-bottom:4px}
    .sub{font-size:10px;color:#64748b;letter-spacing:2px;margin-bottom:24px}
    .tabs{display:flex;margin-bottom:20px;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden}
    .tab{flex:1;padding:9px;text-align:center;font-size:11px;font-weight:700;letter-spacing:1px;cursor:pointer;background:#f8fafc;color:#64748b;border:none;transition:all 0.2s}
    .tab.active{background:#2563eb;color:white}
    label{font-size:9px;color:#64748b;letter-spacing:2px;display:block;margin-bottom:5px;margin-top:12px}
    input{width:100%;padding:10px 14px;border:1px solid #e2e8f0;border-radius:7px;font-size:13px;font-family:monospace;background:#f8fafc;color:#1e293b;outline:none}
    input:focus{border-color:#2563eb}
    button[type=submit]{width:100%;margin-top:16px;padding:12px;background:#2563eb;color:white;border:none;border-radius:7px;font-size:11px;font-weight:700;letter-spacing:2px;cursor:pointer}
    .error{color:#e11d48;font-size:11px;margin-top:10px;text-align:center;padding:8px;background:#fff1f2;border-radius:5px}
    .success{color:#059669;font-size:11px;margin-top:10px;text-align:center;padding:8px;background:#f0fdf4;border-radius:5px}
    .info{font-size:10px;color:#64748b;text-align:center;margin-top:10px;line-height:1.6}
    .link{color:#2563eb;cursor:pointer;font-size:10px;text-align:center;margin-top:10px;display:block;background:none;border:none;width:100%;text-decoration:underline}
    form{display:none}
    form.active{display:block}
  </style>
</head>
<body>
<div class="card">
  <div class="logo">QUANT<span style="color:#00e676">⚡</span>DESK</div>
  <div class="sub">OPTIONS INTRADAY · ACCÈS PRIVÉ</div>

  <div class="tabs">
    <button class="tab active" onclick="showTab('login')">CONNEXION</button>
    <button class="tab" onclick="showTab('register')">CRÉER COMPTE</button>
    <button class="tab" onclick="showTab('reset')">MOT DE PASSE</button>
  </div>

  <!-- LOGIN -->
  <form id="login-form" class="active" method="POST" action="/login">
    <input type="hidden" name="action" value="login">
    <label>IDENTIFIANT</label>
    <input type="text" name="username" placeholder="votre identifiant" autofocus required />
    <label>MOT DE PASSE</label>
    <input type="password" name="password" placeholder="••••••••••" required />
    <button type="submit">SE CONNECTER →</button>
    <button type="button" class="link" onclick="showTab('reset')">Mot de passe oublié ?</button>
  </form>

  <!-- REGISTER -->
  <form id="register-form" method="POST" action="/login">
    <input type="hidden" name="action" value="register">
    <label>IDENTIFIANT (3-20 caractères)</label>
    <input type="text" name="username" placeholder="ex: john_trader" required pattern="[a-zA-Z0-9_]{3,20}" />
    <label>MOT DE PASSE (min 6 caractères)</label>
    <input type="password" name="password" placeholder="••••••••••" required minlength="6" />
    <label>CODE D'INVITATION</label>
    <input type="text" name="invite" placeholder="fourni par l'administrateur" required />
    <button type="submit">CRÉER MON COMPTE →</button>
    <div class="info">Code d'invitation requis · Contactez l'administrateur</div>
  </form>

  <!-- RESET PASSWORD -->
  <form id="reset-form" method="POST" action="/login">
    <input type="hidden" name="action" value="reset_request">
    <label>IDENTIFIANT</label>
    <input type="text" name="username" placeholder="votre identifiant" required />
    <button type="submit">DEMANDER RÉINITIALISATION →</button>
    <div class="info">L'administrateur recevra votre demande et vous enverra un code de réinitialisation.</div>
  </form>

  <!-- RESET CONFIRM (avec code) -->
  <form id="reset-confirm-form" method="POST" action="/login">
    <input type="hidden" name="action" value="reset_confirm">
    <label>IDENTIFIANT</label>
    <input type="text" name="username" placeholder="votre identifiant" required />
    <label>CODE DE RÉINITIALISATION</label>
    <input type="text" name="reset_code" placeholder="code fourni par admin" required />
    <label>NOUVEAU MOT DE PASSE</label>
    <input type="password" name="new_password" placeholder="••••••••••" required minlength="6" />
    <button type="submit">CHANGER MOT DE PASSE →</button>
  </form>

  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  {% if success %}<div class="success">{{ success }}</div>{% endif %}
</div>
<script>
function showTab(t){
  ['login','register','reset','reset-confirm'].forEach(id=>{
    const f=document.getElementById(id+'-form');
    if(f) f.className=id===t?'active':'';
  });
  document.querySelectorAll('.tab').forEach((el,i)=>{
    el.classList.toggle('active',
      (t==='login'&&i===0)||(t==='register'&&i===1)||(t==='reset'&&i===2)||(t==='reset-confirm'&&i===2)
    );
  });
}
{% if tab %}showTab('{{ tab }}');{% endif %}
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
  <title>QUANTDESK Admin</title>
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{background:#f8fafc;font-family:'Courier New',monospace;padding:20px}
    .header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}
    .logo{font-size:16px;font-weight:900;letter-spacing:3px;color:#1e293b}
    .nav a{color:#2563eb;text-decoration:none;font-size:11px;margin-left:12px}
    .card{background:white;border:1px solid #e2e8f0;border-radius:10px;padding:18px;margin-bottom:14px}
    h2{font-size:10px;letter-spacing:2px;color:#64748b;margin-bottom:14px;font-weight:800}
    table{width:100%;border-collapse:collapse;font-size:11px}
    th{text-align:left;padding:7px 10px;font-size:8px;color:#64748b;letter-spacing:1px;border-bottom:1px solid #e2e8f0;white-space:nowrap}
    td{padding:9px 10px;border-bottom:1px solid #f1f5f9;color:#1e293b;vertical-align:middle}
    .badge{display:inline-block;padding:2px 7px;border-radius:3px;font-size:8px;font-weight:700;letter-spacing:1px}
    .active{background:#d1fae5;color:#059669}
    .suspended{background:#fee2e2;color:#e11d48}
    .online{background:#dbeafe;color:#2563eb}
    form{display:inline}
    button{padding:3px 8px;border-radius:4px;cursor:pointer;font-size:9px;font-weight:700;border:1px solid;margin:1px}
    .g{background:#d1fae5;color:#059669;border-color:#059669}
    .r{background:#fee2e2;color:#e11d48;border-color:#e11d48}
    .y{background:#fef3c7;color:#d97706;border-color:#d97706}
    .b{background:#dbeafe;color:#2563eb;border-color:#2563eb}
    .p{background:#ede9fe;color:#7c3aed;border-color:#7c3aed}
    .invite-box{background:#f1f5f9;padding:12px;border-radius:7px;margin-top:10px;text-align:center}
    .code{font-size:22px;font-weight:900;letter-spacing:6px;color:#2563eb;padding:8px}
    .reset-box{background:#fef3c7;padding:12px;border-radius:7px;margin-top:10px}
    .dot-online{width:7px;height:7px;border-radius:50%;background:#059669;display:inline-block;margin-right:4px;box-shadow:0 0 6px #059669}
    .dot-offline{width:7px;height:7px;border-radius:50%;background:#cbd5e1;display:inline-block;margin-right:4px}
  </style>
</head>
<body>
<div class="header">
  <div class="logo">QUANT⚡DESK · ADMIN</div>
  <div class="nav">
    <a href="/">← Dashboard</a>
    <a href="/admin">🔄 Actualiser</a>
    <a href="/logout">Déconnexion</a>
  </div>
</div>

<!-- SESSIONS ACTIVES -->
<div class="card">
  <h2>🟢 CONNECTÉS EN CE MOMENT ({{ active_sessions|length }})</h2>
  {% if active_sessions %}
  <table>
    <thead><tr><th>IDENTIFIANT</th><th>CONNEXION</th><th>DERNIÈRE ACTIVITÉ</th></tr></thead>
    <tbody>
      {% for s in active_sessions %}
      <tr>
        <td><span class="dot-online"></span><b>{{ s.username }}</b></td>
        <td>{{ s.login_time }}</td>
        <td>{{ s.last_seen }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div style="color:#64748b;font-size:11px;padding:8px">Aucun utilisateur connecté</div>
  {% endif %}
</div>

<!-- GESTION UTILISATEURS -->
<div class="card">
  <h2>👥 COMPTES UTILISATEURS ({{ users|length }})</h2>
  <table>
    <thead>
      <tr><th>IDENTIFIANT</th><th>STATUT</th><th>EN LIGNE</th><th>CRÉÉ LE</th><th>DERNIÈRE CONNEXION</th><th>ACTIONS</th></tr>
    </thead>
    <tbody>
      {% for username, data in users.items() %}
      {% set is_online = active_usernames and username in active_usernames %}
      <tr>
        <td><b>{{ username }}</b></td>
        <td><span class="badge {{ data.status }}">{{ data.status.upper() }}</span></td>
        <td>{% if is_online %}<span class="badge online">● EN LIGNE</span>{% else %}<span style="color:#94a3b8;font-size:9px">hors ligne</span>{% endif %}</td>
        <td style="font-size:10px;color:#64748b">{{ data.get('created','—') }}</td>
        <td style="font-size:10px;color:#64748b">{{ data.get('last_login','—') }}</td>
        <td>
          {% if data.status != 'active' %}
          <form method="POST" action="/admin/action"><input type="hidden" name="username" value="{{ username }}"><input type="hidden" name="action" value="activate"><button class="g" type="submit">✓ Activer</button></form>
          {% endif %}
          {% if data.status == 'active' %}
          <form method="POST" action="/admin/action"><input type="hidden" name="username" value="{{ username }}"><input type="hidden" name="action" value="suspend"><button class="y" type="submit">⏸ Suspendre</button></form>
          {% endif %}
          <form method="POST" action="/admin/action"><input type="hidden" name="username" value="{{ username }}"><input type="hidden" name="action" value="reset_password"><button class="p" type="submit">🔑 Reset MDP</button></form>
          <form method="POST" action="/admin/action"><input type="hidden" name="username" value="{{ username }}"><input type="hidden" name="action" value="delete"><button class="r" type="submit" onclick="return confirm('Supprimer {{ username }} ?')">✕ Révoquer</button></form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<!-- DEMANDES DE RESET -->
{% if reset_requests %}
<div class="card">
  <h2>🔐 DEMANDES DE RÉINITIALISATION MOT DE PASSE ({{ reset_requests|length }})</h2>
  <table>
    <thead><tr><th>IDENTIFIANT</th><th>DEMANDÉ LE</th><th>CODE À TRANSMETTRE</th><th>EXPIRE</th><th>ACTION</th></tr></thead>
    <tbody>
      {% for username, data in reset_requests.items() %}
      <tr>
        <td><b>{{ username }}</b></td>
        <td style="font-size:10px;color:#64748b">{{ data.created }}</td>
        <td><b style="color:#7c3aed;letter-spacing:3px;font-size:14px">{{ data.code }}</b></td>
        <td style="font-size:10px;color:#64748b">{{ data.expires_str }}</td>
        <td>
          <form method="POST" action="/admin/action"><input type="hidden" name="username" value="{{ username }}"><input type="hidden" name="action" value="clear_reset"><button class="r" type="submit">✕ Annuler</button></form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

<!-- INVITATIONS -->
<div class="card">
  <h2>🎟️ CODES D'INVITATION</h2>
  <form method="POST" action="/admin/invite">
    <button class="b" type="submit">+ Générer un code</button>
  </form>
  {% if invite_code %}
  <div class="invite-box">
    <div style="font-size:9px;color:#64748b;margin-bottom:4px">PARTAGEZ CE CODE (usage unique · 24h)</div>
    <div class="code">{{ invite_code }}</div>
    <div style="font-size:9px;color:#64748b">Expire le {{ invite_expires }}</div>
  </div>
  {% endif %}
  {% if reset_code_info %}
  <div class="reset-box">
    <div style="font-size:9px;color:#d97706;margin-bottom:6px">🔑 CODE RESET POUR <b>{{ reset_code_info.username }}</b></div>
    <div class="code" style="color:#7c3aed">{{ reset_code_info.code }}</div>
    <div style="font-size:9px;color:#64748b">Transmettez ce code à l'utilisateur · Expire dans 1h</div>
  </div>
  {% endif %}
</div>
</body>
</html>
"""

# ── LOGIN ROUTES ──────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET"])
def login_page():
    return render_template_string(AUTH_PAGE, error=None, success=None, tab=request.args.get("tab","login"))

@app.route("/login", methods=["POST"])
def login_post():
    action   = request.form.get("action","login")
    username = request.form.get("username","").strip().lower()
    password = request.form.get("password","")

    # ADMIN
    if username == "admin" and password == ADMIN_PASSWORD and action == "login":
        session["auth"] = True; session["username"] = "admin"; session["is_admin"] = True
        track_session("admin")
        return redirect("/admin")

    # REGISTER
    if action == "register":
        invite = request.form.get("invite","").strip()
        invites = load_invites(); now = time.time()
        valid = next((c for c,d in invites.items() if c==invite and d["expires"]>now and not d["used"]), None)
        if not valid:
            return render_template_string(AUTH_PAGE, error="Code d'invitation invalide ou expiré.", success=None, tab="register")
        users = load_users()
        if username in users:
            return render_template_string(AUTH_PAGE, error="Identifiant déjà pris.", success=None, tab="register")
        if len(username) < 3:
            return render_template_string(AUTH_PAGE, error="Identifiant trop court (min 3).", success=None, tab="register")
        users[username] = {"password": hash_password(password), "status": "active",
                           "created": time.strftime("%d/%m/%Y %H:%M"), "last_login": None}
        save_users(users)
        invites[valid]["used"] = True; save_invites(invites)
        return render_template_string(AUTH_PAGE, error=None, success=f"Compte créé ! Connectez-vous avec '{username}'.", tab="login")

    # RESET REQUEST
    if action == "reset_request":
        users = load_users()
        if username not in users:
            return render_template_string(AUTH_PAGE, error="Identifiant introuvable.", success=None, tab="reset")
        code = secrets.token_hex(3).upper()
        resets = load_resets()
        resets[username] = {"code": code, "expires": time.time()+3600,
                            "created": time.strftime("%d/%m/%Y %H:%M"),
                            "expires_str": time.strftime("%H:%M", time.localtime(time.time()+3600))}
        save_resets(resets)
        return render_template_string(AUTH_PAGE, error=None,
            success="Demande envoyée. L'administrateur vous transmettra un code de réinitialisation.", tab="reset-confirm")

    # RESET CONFIRM
    if action == "reset_confirm":
        new_password = request.form.get("new_password","")
        reset_code   = request.form.get("reset_code","").strip().upper()
        resets = load_resets()
        if username not in resets:
            return render_template_string(AUTH_PAGE, error="Aucune demande de réinitialisation trouvée.", success=None, tab="reset-confirm")
        r = resets[username]
        if r["code"] != reset_code:
            return render_template_string(AUTH_PAGE, error="Code incorrect.", success=None, tab="reset-confirm")
        if time.time() > r["expires"]:
            return render_template_string(AUTH_PAGE, error="Code expiré. Refaites une demande.", success=None, tab="reset")
        users = load_users()
        users[username]["password"] = hash_password(new_password)
        save_users(users)
        del resets[username]; save_resets(resets)
        return render_template_string(AUTH_PAGE, error=None, success="Mot de passe changé ! Connectez-vous.", tab="login")

    # LOGIN
    users = load_users()
    if username not in users:
        return render_template_string(AUTH_PAGE, error="Identifiant ou mot de passe incorrect.", success=None, tab="login")
    user = users[username]
    if user["status"] == "suspended":
        return render_template_string(AUTH_PAGE, error="Accès suspendu. Contactez l'administrateur.", success=None, tab="login")
    if user["password"] != hash_password(password):
        return render_template_string(AUTH_PAGE, error="Identifiant ou mot de passe incorrect.", success=None, tab="login")
    users[username]["last_login"] = time.strftime("%d/%m/%Y %H:%M")
    save_users(users)
    session["auth"] = True; session["username"] = username; session["is_admin"] = False
    track_session(username)
    return redirect("/")

@app.route("/logout")
def logout():
    untrack_session()
    session.clear()
    return redirect("/login")

# ── ADMIN ROUTES ──────────────────────────────────────────────────────────────
@app.route("/admin")
@require_admin
def admin_page():
    users   = load_users()
    resets  = load_resets()
    active  = get_active_sessions()
    active_usernames = {s["username"] for s in active}
    reset_requests = {u:d for u,d in resets.items() if d["expires"] > time.time()}
    return render_template_string(ADMIN_PAGE, users=users, active_sessions=active,
        active_usernames=active_usernames, reset_requests=reset_requests,
        invite_code=None, invite_expires=None, reset_code_info=None)

@app.route("/admin/action", methods=["POST"])
@require_admin
def admin_action():
    username = request.form.get("username")
    action   = request.form.get("action")
    users    = load_users()
    reset_code_info = None
    if username in users:
        if action == "activate":   users[username]["status"] = "active"
        elif action == "suspend":  users[username]["status"] = "suspended"
        elif action == "delete":   del users[username]
        elif action == "reset_password":
            code = secrets.token_hex(3).upper()
            resets = load_resets()
            resets[username] = {"code": code, "expires": time.time()+3600,
                                "created": time.strftime("%d/%m/%Y %H:%M"),
                                "expires_str": time.strftime("%H:%M", time.localtime(time.time()+3600))}
            save_resets(resets)
            reset_code_info = {"username": username, "code": code}
        elif action == "clear_reset":
            resets = load_resets()
            if username in resets: del resets[username]; save_resets(resets)
        save_users(users)
    active = get_active_sessions()
    active_usernames = {s["username"] for s in active}
    resets = load_resets()
    reset_requests = {u:d for u,d in resets.items() if d["expires"] > time.time()}
    return render_template_string(ADMIN_PAGE, users=users, active_sessions=active,
        active_usernames=active_usernames, reset_requests=reset_requests,
        invite_code=None, invite_expires=None, reset_code_info=reset_code_info)

@app.route("/admin/invite", methods=["POST"])
@require_admin
def admin_invite():
    code = secrets.token_hex(4).upper()
    invites = load_invites()
    invites[code] = {"used": False, "expires": time.time()+86400, "created": time.strftime("%d/%m/%Y %H:%M")}
    save_invites(invites)
    users  = load_users()
    active = get_active_sessions()
    active_usernames = {s["username"] for s in active}
    resets = load_resets()
    reset_requests = {u:d for u,d in resets.items() if d["expires"] > time.time()}
    expires_str = time.strftime("%d/%m/%Y %H:%M", time.localtime(time.time()+86400))
    return render_template_string(ADMIN_PAGE, users=users, active_sessions=active,
        active_usernames=active_usernames, reset_requests=reset_requests,
        invite_code=code, invite_expires=expires_str, reset_code_info=None)

# ── API USER INFO ─────────────────────────────────────────────────────────────
@app.route("/api/me")
@require_auth_api
def me():
    return jsonify({"username": session.get("username"), "is_admin": session.get("is_admin", False)})

# ── CACHE ─────────────────────────────────────────────────────────────────────
_cache = {}
_lock  = threading.Lock()
CACHE_TTL = {"5m": 60, "10m": 120, "1h": 300, "1d": 3600, "quote": 30}

def cache_get(key):
    with _lock:
        if key in _cache:
            data, ts, ttl = _cache[key]
            if time.time() - ts < ttl: return data
    return None

def cache_set(key, data, ttl):
    with _lock: _cache[key] = (data, time.time(), ttl)

def fetch_with_retry(fn, retries=3, wait=5):
    for attempt in range(retries):
        try: return fn()
        except Exception as e:
            if ("Rate" in str(e) or "429" in str(e)) and attempt < retries-1:
                time.sleep(wait*(attempt+1)); continue
            raise
    raise Exception("Rate limit persistant.")

# ── STATIC ────────────────────────────────────────────────────────────────────
HTML_DIR  = os.path.dirname(os.path.abspath(__file__))

def find_html():
    for pat in ["quant-desk*.html","index.html","*.html"]:
        matches = glob.glob(os.path.join(HTML_DIR, pat))
        if matches: return os.path.basename(sorted(matches)[-1])
    return None

HTML_FILE = find_html()

@app.route("/")
@require_auth
def index():
    if not HTML_FILE: return "HTML non trouvé", 404
    response = send_from_directory(HTML_DIR, HTML_FILE)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response

@app.route("/<path:filename>")
def static_files(filename):
    fp = os.path.join(HTML_DIR, filename)
    if os.path.exists(fp): return send_from_directory(HTML_DIR, filename)
    return f"Not found: {filename}", 404

# ── API ───────────────────────────────────────────────────────────────────────
DEFAULT_RANGE = {"5m":"5d","10m":"5d","1h":"1mo","1d":"5y"}

@app.route("/api/chart")
@require_auth_api
def chart():
    ticker   = request.args.get("ticker","").upper()
    interval = request.args.get("interval","1d")
    range_   = request.args.get("range", DEFAULT_RANGE.get(interval,"5y"))
    if not ticker: return jsonify({"error":"ticker manquant"}),400
    cache_key = f"chart_{ticker}_{interval}_{range_}"
    cached = cache_get(cache_key)
    if cached: return jsonify(cached)
    try:
        hist = fetch_with_retry(lambda: yf.Ticker(ticker).history(period=range_,interval=interval,auto_adjust=True))
        if hist.empty: return jsonify({"error":f"Pas de données pour {ticker}"}),404
        data = {"ticker":ticker,"interval":interval,"range":range_,
                "closes": [round(float(v),4) for v in hist["Close"].tolist()],
                "dates":  [str(d) for d in hist.index.tolist()],
                "opens":  [round(float(v),4) for v in hist["Open"].tolist()],
                "highs":  [round(float(v),4) for v in hist["High"].tolist()],
                "lows":   [round(float(v),4) for v in hist["Low"].tolist()],
                "volumes":[int(v) for v in hist["Volume"].tolist()]}
        cache_set(cache_key, data, CACHE_TTL.get(interval,3600))
        return jsonify(data)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/quote")
@require_auth_api
def quote():
    symbols = [s.strip().upper() for s in request.args.get("symbols","").split(",") if s.strip()]
    if not symbols: return jsonify({"error":"symbols manquants"}),400
    cache_key = "quote_"+"_".join(sorted(symbols))
    cached = cache_get(cache_key)
    if cached: return jsonify(cached)
    out = {}
    for sym in symbols:
        try:
            def do_q(s=sym):
                info  = yf.Ticker(s).fast_info
                price = float(info.last_price or 0)
                prev  = float(info.previous_close or price)
                vol   = int(info.three_month_average_volume or 0)
                return {"regularMarketPrice":round(price,4),
                        "regularMarketChangePercent":round((price-prev)/prev*100 if prev else 0,4),
                        "regularMarketVolume":vol}
            out[sym] = fetch_with_retry(do_q, retries=2, wait=3)
        except Exception as e: out[sym] = {"error":str(e)}
        time.sleep(0.3)
    cache_set(cache_key, out, CACHE_TTL["quote"])
    return jsonify(out)

@app.route("/api/status")
def status():
    return jsonify({"ok":True,"html":HTML_FILE,"cache_keys":len(_cache),"active_users":len(_active_sessions)})

@app.route("/api/clear-cache")
@require_auth_api
def clear_cache():
    with _lock: _cache.clear()
    return jsonify({"ok":True})

# Créer /data si absent (dev local)
os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)

if __name__ == "__main__":
    print("="*55)
    print(f"  QUANTDESK Server v6 — Multi-user + Reset MDP")
    print(f"  HTML: {HTML_FILE}")
    print(f"  Admin: http://localhost:8080/admin")
    print(f"  Mot de passe admin: {ADMIN_PASSWORD}")
    print("="*55)
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
