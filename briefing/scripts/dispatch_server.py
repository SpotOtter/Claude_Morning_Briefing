"""Driver accounts for the briefing site (login now, dispatch later). Standard library only.

Runs on 127.0.0.1 behind nginx (which proxies /api/ to it). Accounts are created by the admin or the lead with a
temporary password that must be changed at first sign-in. Data lives in a SQLite file under /data.

Environment: DISPATCH_DB, DISPATCH_PORT, DISPATCH_HOST, ADMIN_NAME, ADMIN_TEMP, DISPATCH_STATIC (dev only).
"""
import base64, hashlib, hmac, json, os, re, secrets, sqlite3, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB = os.environ.get("DISPATCH_DB", "/data/dispatch.db")
HOST = os.environ.get("DISPATCH_HOST", "127.0.0.1")
PORT = int(os.environ.get("DISPATCH_PORT", "8081"))
STATIC = os.environ.get("DISPATCH_STATIC", "")
SESSION_DAYS = 90
MIN_PW = 6
ROLES = ("admin", "lead", "driver")
COOKIE = "bsid"
TEMP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no I, O, 0 or 1, so a code is easy to read aloud


# ---------- passwords ----------
def _b64(b): return base64.b64encode(b).decode()
def hash_pw(pw):
    salt = os.urandom(16)
    if hasattr(hashlib, "scrypt"):
        h = hashlib.scrypt(pw.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
        return "scrypt$16384$8$1$%s$%s" % (_b64(salt), _b64(h))
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 600000, 32)   # fallback if this Python lacks scrypt
    return "pbkdf2$600000$%s$%s" % (_b64(salt), _b64(h))
def check_pw(pw, stored):
    try:
        parts = stored.split("$")
        if parts[0] == "scrypt":
            _, n, r, p, salt, h = parts
            got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        else:
            _, it, salt, h = parts
            got = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(salt), int(it), 32)
        return hmac.compare_digest(got, base64.b64decode(h))
    except Exception:
        return False
DUMMY = hash_pw("not-a-real-password")   # checked for unknown usernames so timing does not reveal who exists

def temp_password():
    c = "".join(secrets.choice(TEMP_ALPHABET) for _ in range(8))
    return c[:4] + "-" + c[4:]
def norm_temp(s): return re.sub(r"[\s-]", "", s or "").upper()


# ---------- usernames ----------
def clean(s): return re.sub(r"[^A-Za-z]", "", s or "")
def make_username(first, last, taken_lc):
    """First-L, then First-Lx, First-Lxy ... when the shorter one is already taken."""
    parts = (first or "").split()
    f = clean(parts[0]) if parts else ""
    l = clean(last)
    if not f or not l: raise ValueError("Enter a first and a last name using letters.")
    f = f[0].upper() + f[1:].lower()
    for n in range(1, len(l) + 1):
        cand = f + "-" + l[:n][0].upper() + l[1:n].lower()
        if cand.lower() not in taken_lc: return cand
    base = f + "-" + l[0].upper() + l[1:].lower()
    i = 2
    while (base + str(i)).lower() in taken_lc: i += 1
    return base + str(i)


# ---------- storage ----------
lock = threading.Lock()
def conn():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    with lock, conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, username TEXT NOT NULL, username_lc TEXT NOT NULL UNIQUE,
          first TEXT NOT NULL, last TEXT NOT NULL, role TEXT NOT NULL, pw TEXT NOT NULL,
          must_change INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1,
          created INTEGER NOT NULL, last_login INTEGER);
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires INTEGER NOT NULL, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
        """)

def taken_names(c): return {r["username_lc"] for r in c.execute("SELECT username_lc FROM users")}

def create_user(c, first, last, role, password):
    uname = make_username(first, last, taken_names(c))
    c.execute("INSERT INTO users (username, username_lc, first, last, role, pw, must_change, created) VALUES (?,?,?,?,?,?,1,?)",
              (uname, uname.lower(), first.strip(), last.strip(), role, hash_pw(password), int(time.time())))
    return c.execute("SELECT * FROM users WHERE username_lc=?", (uname.lower(),)).fetchone()

def bootstrap_admin():
    """Create the admin the first time. A new ADMIN_TEMP value also resets the admin's password (recovery)."""
    name = (os.environ.get("ADMIN_NAME") or "Admin User").split()
    first, last = name[0], " ".join(name[1:]) or "Admin"
    given = os.environ.get("ADMIN_TEMP", "")
    marker = hashlib.sha256(given.encode()).hexdigest() if given else ""
    with lock, conn() as c:
        admin = c.execute("SELECT * FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1").fetchone()
        applied = c.execute("SELECT v FROM meta WHERE k='admin_temp_applied'").fetchone()
        if admin is None:
            usable = given if len(given) >= MIN_PW else ""
            pw = usable or temp_password()
            u = create_user(c, first, last, "admin", norm_temp(pw) if not usable else pw)
            if usable: c.execute("INSERT OR REPLACE INTO meta VALUES ('admin_temp_applied', ?)", (marker,))
            else:
                print("ADMIN ACCOUNT CREATED. Username: %s  Temporary password: %s  (you must change it at first sign-in)" % (u["username"], pw), flush=True)
        elif given and len(given) >= MIN_PW and (applied is None or applied["v"] != marker):
            c.execute("UPDATE users SET pw=?, must_change=1 WHERE id=?", (hash_pw(given), admin["id"]))
            c.execute("DELETE FROM sessions WHERE user_id=?", (admin["id"],))
            c.execute("INSERT OR REPLACE INTO meta VALUES ('admin_temp_applied', ?)", (marker,))
            print("Admin password reset from the add-on option. Username: %s" % admin["username"], flush=True)


# ---------- lockouts (in memory) ----------
class Limiter:
    def __init__(self, max_fails, window, lock_for):
        self.max, self.window, self.lock_for, self.d, self.m = max_fails, window, lock_for, {}, threading.Lock()
    def wait(self, key):
        with self.m:
            e = self.d.get(key)
            return max(0, int(e["until"] - time.time())) if e else 0
    def fail(self, key):
        now = time.time()
        with self.m:
            e = self.d.get(key)
            if not e or now - e["first"] > self.window: e = {"n": 0, "first": now, "until": 0}
            e["n"] += 1
            if e["n"] >= self.max: e["until"] = now + self.lock_for; e["n"] = 0; e["first"] = now
            self.d[key] = e
    def reset(self, key):
        with self.m: self.d.pop(key, None)
by_user = Limiter(5, 900, 900)     # 5 wrong tries for one username -> locked for 15 minutes
by_ip = Limiter(30, 900, 900)      # 30 wrong tries from one address -> locked for 15 minutes


# ---------- HTTP ----------
def pub(u):
    return {"id": u["id"], "username": u["username"], "name": (u["first"] + " " + u["last"]).strip(), "role": u["role"],
            "must_change": bool(u["must_change"]), "last_login": u["last_login"]}

class H(BaseHTTPRequestHandler):
    server_version = "briefing-login"
    protocol_version = "HTTP/1.1"
    def log_message(self, fmt, *a): print("%s %s" % (self.command, self.path.split("?")[0]), a[1] if len(a) > 1 else "", flush=True)

    # -- helpers
    def ip(self): return self.headers.get("CF-Connecting-IP") or self.headers.get("X-Real-IP") or self.client_address[0]
    def https(self): return "https" in (self.headers.get("CF-Visitor", "") + self.headers.get("X-Forwarded-Proto", ""))
    def send(self, code, obj=None, cookie=None, raw=None, ctype="application/json"):
        body = raw if raw is not None else json.dumps(obj if obj is not None else {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype != "application/json" else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie: self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(body)
    def err(self, code, msg, **extra): self.send(code, dict(error=msg, **extra))
    def cookie_str(self, token, max_age):
        s = "%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d" % (COOKIE, token, max_age)
        return s + ("; Secure" if self.https() else "")
    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 4096: raise ValueError("too big")
        if "application/json" not in (self.headers.get("Content-Type") or ""): raise ValueError("bad type")
        o = self.headers.get("Origin")
        if o and re.sub(r"^https?://", "", o) != self.headers.get("Host", ""): raise ValueError("bad origin")
        d = json.loads(self.rfile.read(n) or b"{}")
        if not isinstance(d, dict): raise ValueError("bad body")
        return d
    def token(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE and v: return v
        return None
    def me(self, c):
        t = self.token()
        if not t: return None
        return c.execute("""SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
                            WHERE s.token_hash=? AND s.expires>? AND u.active=1""",
                         (hashlib.sha256(t.encode()).hexdigest(), int(time.time()))).fetchone()
    def start_session(self, c, uid):
        t = secrets.token_urlsafe(32)
        now = int(time.time())
        c.execute("INSERT INTO sessions VALUES (?,?,?,?)", (hashlib.sha256(t.encode()).hexdigest(), uid, now + SESSION_DAYS * 86400, now))
        c.execute("DELETE FROM sessions WHERE expires<?", (now,))
        return self.cookie_str(t, SESSION_DAYS * 86400)

    # -- routing
    def do_GET(self): self.route()
    def do_HEAD(self): self.route()
    def do_POST(self): self.route()
    def route(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        try:
            if STATIC and self.command in ("GET", "HEAD") and path in ("/drivers", "/drivers.html"):
                return self.send(200, raw=open(os.path.join(STATIC, "drivers.html"), "rb").read(), ctype="text/html")
            if not path.startswith("/api/"): return self.err(404, "Not found.")
            ep = path[5:]
            if self.command == "GET" and ep == "me": return self.api_me()
            if self.command == "GET" and ep == "users": return self.api_users()
            if self.command == "POST":
                try: d = self.body()
                except (ValueError, json.JSONDecodeError): return self.err(400, "Bad request.")
                if ep == "login": return self.api_login(d)
                if ep == "logout": return self.api_logout()
                if ep == "change-password": return self.api_change(d)
                if ep == "users": return self.api_create(d)
                m = re.fullmatch(r"users/(\d+)/(reset|remove)", ep)
                if m: return self.api_manage(int(m.group(1)), m.group(2))
            return self.err(404, "Not found.")
        except Exception as e:
            print("ERROR", repr(e), file=sys.stderr, flush=True)
            return self.err(500, "Something went wrong. Try again.")

    # -- endpoints
    def api_login(self, d):
        uname = str(d.get("username", "")).strip().lower()[:60]; pw = str(d.get("password", ""))[:200]
        ip = self.ip()
        w = max(by_ip.wait(ip), by_user.wait(uname))
        if w: return self.err(429, "Too many tries. Wait %d minutes and try again." % max(1, (w + 59) // 60))
        with lock, conn() as c:
            u = c.execute("SELECT * FROM users WHERE username_lc=? AND active=1", (uname,)).fetchone()
            ok = False
            if u:
                ok = check_pw(pw, u["pw"]) or (bool(u["must_change"]) and check_pw(norm_temp(pw), u["pw"]))
            else:
                check_pw(pw, DUMMY)
            if not ok:
                by_user.fail(uname); by_ip.fail(ip)
                return self.err(401, "Wrong username or password.")
            by_user.reset(uname)
            c.execute("UPDATE users SET last_login=? WHERE id=?", (int(time.time()), u["id"]))
            cookie = self.start_session(c, u["id"])
            u = c.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
        self.send(200, {"user": pub(u)}, cookie=cookie)

    def api_logout(self):
        t = self.token()
        if t:
            with lock, conn() as c: c.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(t.encode()).hexdigest(),))
        self.send(200, {"ok": True}, cookie=self.cookie_str("", 0))

    def api_me(self):
        with conn() as c: u = self.me(c)
        if not u: return self.err(401, "Not signed in.")
        self.send(200, {"user": pub(u)})

    def api_change(self, d):
        cur, new = str(d.get("current", ""))[:200], str(d.get("new", ""))[:200]
        with lock, conn() as c:
            u = self.me(c)
            if not u: return self.err(401, "Not signed in.")
            key = u["username_lc"]
            w = by_user.wait(key)
            if w: return self.err(429, "Too many tries. Wait %d minutes and try again." % max(1, (w + 59) // 60))
            if not (check_pw(cur, u["pw"]) or (bool(u["must_change"]) and check_pw(norm_temp(cur), u["pw"]))):
                by_user.fail(key); return self.err(400, "Your current password is wrong.")
            if len(new) < MIN_PW: return self.err(400, "Use at least %d characters." % MIN_PW)
            if new == cur or norm_temp(new) == norm_temp(cur): return self.err(400, "Pick a different password than the temporary one.")
            c.execute("UPDATE users SET pw=?, must_change=0 WHERE id=?", (hash_pw(new), u["id"]))
            keep = hashlib.sha256(self.token().encode()).hexdigest()
            c.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (u["id"], keep))
            by_user.reset(key)
            u = c.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
        self.send(200, {"user": pub(u)})

    def staff(self, c):
        """The signed-in admin or lead, or None (after sending the error)."""
        u = self.me(c)
        if not u: self.err(401, "Not signed in."); return None
        if u["must_change"]: self.err(403, "Choose a new password first.", must_change=True); return None
        if u["role"] not in ("admin", "lead"): self.err(403, "Only the admin or the lead can do that."); return None
        return u

    def api_users(self):
        with conn() as c:
            u = self.staff(c)
            if not u: return
            rows = c.execute("SELECT * FROM users WHERE active=1 ORDER BY CASE role WHEN 'admin' THEN 0 WHEN 'lead' THEN 1 ELSE 2 END, username_lc").fetchall()
        self.send(200, {"users": [pub(r) for r in rows], "can_make_leads": u["role"] == "admin"})

    def api_create(self, d):
        first, last, role = str(d.get("first", ""))[:40], str(d.get("last", ""))[:60], str(d.get("role", "driver"))
        with lock, conn() as c:
            u = self.staff(c)
            if not u: return
            if role not in ("driver", "lead") or (role == "lead" and u["role"] != "admin"): role = "driver"
            pw = temp_password()
            try: new = create_user(c, first, last, role, norm_temp(pw))
            except ValueError as e: return self.err(400, str(e))
        self.send(200, {"user": pub(new), "temp_password": pw})

    def api_manage(self, uid, action):
        with lock, conn() as c:
            u = self.staff(c)
            if not u: return
            t = c.execute("SELECT * FROM users WHERE id=? AND active=1", (uid,)).fetchone()
            if not t: return self.err(404, "That person was not found.")
            if t["id"] == u["id"]: return self.err(400, "Use your own password page to change your password.")
            if t["role"] == "admin" or (u["role"] == "lead" and t["role"] != "driver"):
                return self.err(403, "You cannot change that account.")
            if action == "reset":
                pw = temp_password()
                c.execute("UPDATE users SET pw=?, must_change=1 WHERE id=?", (hash_pw(norm_temp(pw)), uid))
                c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
                return self.send(200, {"temp_password": pw, "user": pub(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())})
            c.execute("UPDATE users SET active=0 WHERE id=?", (uid,))
            c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        self.send(200, {"ok": True})


def main():
    init_db()
    bootstrap_admin()
    ThreadingHTTPServer.daemon_threads = True
    srv = ThreadingHTTPServer((HOST, PORT), H)
    print("Driver login server on %s:%d" % (HOST, PORT), flush=True)
    srv.serve_forever()

if __name__ == "__main__":
    main()
