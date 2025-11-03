# app.py
import os, time, threading, json, random, datetime, traceback
from flask import Flask, request, jsonify, render_template_string
from instagrapi import Client

APP_DIR = os.path.dirname(__file__)
SESSION_FILE = os.path.join(APP_DIR, "session.json")
MESSAGES_FILE = os.path.join(APP_DIR, "messages.txt")
WELCOMED_FILE = os.path.join(APP_DIR, "welcomed_users.json")
LOG_FILE = os.path.join(APP_DIR, "bot_log.txt")

app = Flask(__name__)
run_lock = threading.Lock()
last_log_tail = 0

INDEX_HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Sessioni — Manual IG Runner</title>
  <style>
    :root{--accent:#7c5cff;--bg:#061226;color:#eaf0ff}
    body{margin:0;font-family:Inter,system-ui,Arial;background:linear-gradient(180deg,#020214,#061226);color:var(--bg);color:#eaf0ff}
    .wrap{max-width:900px;margin:28px auto;padding:22px;background:rgba(0,0,0,0.18);border-radius:12px;border:1px solid rgba(255,255,255,0.03)}
    h1{color:var(--accent);margin:0 0 12px}
    label{display:block;margin-top:8px;color:#cfe8ff;font-size:13px}
    input,textarea,select{width:100%;padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,0.04);background:transparent;color:#eaf0ff;margin-top:6px}
    .row{display:flex;gap:8px}
    button{padding:10px 12px;border-radius:8px;border:none;background:linear-gradient(90deg,#7c5cff,#5ec2ff);color:#021026;font-weight:700;cursor:pointer}
    .small{font-size:12px;color:rgba(255,255,255,0.6);margin-top:6px}
    pre.logs{height:320px;overflow:auto;background:rgba(0,0,0,0.25);padding:10px;border-radius:8px}
    .hint{font-size:13px;color:#d8eaff;background:rgba(0,0,0,0.18);padding:8px;border-radius:8px;margin-top:8px}
    .danger{color:#ffd0d0}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Sessioni — Manual IG Runner</h1>

    <section>
      <h3>1) Upload / Use session.json</h3>
      <form id="sessionForm">
        <input id="sessionFile" type="file" accept=".json" />
        <div style="margin-top:8px"><button type="submit">Upload session.json</button></div>
      </form>
      <div id="sessionStatus" class="small"></div>
      <div class="hint">If you have a valid <code>session.json</code>, upload it — you won't need username/password. If not, provide username/password below to create a new session.</div>
    </section>

    <section>
      <h3>2) Upload messages.txt</h3>
      <form id="msgForm">
        <input id="msgFile" type="file" accept=".txt" />
        <div style="margin-top:8px"><button type="submit">Upload messages.txt</button></div>
      </form>
      <div id="msgStatus" class="small"></div>
      <div class="hint">Use <code>===</code> on separate lines to split multiple messages. Use <code>{username}</code> placeholder to mention the user.</div>
    </section>

    <section>
      <h3>3) Inputs</h3>
      <label>Group IDs (comma separated)</label>
      <input id="groupIds" placeholder="24632887389663044, 123456..." />
      <label>Task ID (any short name to identify this run)</label>
      <input id="taskId" placeholder="task1" />
      <label>Username (optional if session.json present)</label>
      <input id="username" placeholder="instagram_username" />
      <label>Password (optional)</label>
      <input id="password" type="password" placeholder="password" />
      <label>Restart interval (hours) — used only if creating new session</label>
      <input id="restart_interval" type="number" value="24" min="1" />
      <div style="margin-top:8px" class="row">
        <button id="runBtn">Run Once (manual)</button>
        <button id="clearWelcomed">Clear welcomed_users.json</button>
      </div>
      <div id="runStatus" class="small"></div>
      <div class="hint">This does a single-pass: checks current threads for members who were not welcomed and sends messages once. It does NOT run continuously.</div>
      <div class="hint danger">Do not use on production accounts for spam — use test accounts only.</div>
    </section>

    <section>
      <h3>4) Logs</h3>
      <pre id="logs" class="logs">{{ logs }}</pre>
      <div style="margin-top:6px"><button id="refreshLogs">Refresh</button></div>
    </section>
  </div>

<script>
  async function postForm(url, form) {
    const fd = new FormData();
    for (const el of form.querySelectorAll('input[type=file]')) {
      if (el.files[0]) fd.append(el.name || 'file', el.files[0]);
    }
    const res = await fetch(url, { method:'POST', body: fd });
    return res.json();
  }

  document.getElementById('sessionForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = document.getElementById('sessionFile').files[0];
    if (!f) return alert('Choose session.json file');
    const fd = new FormData(); fd.append('session', f);
    const r = await fetch('/upload-session',{method:'POST',body:fd});
    const j = await r.json();
    document.getElementById('sessionStatus').textContent = j.message;
  });

  document.getElementById('msgForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = document.getElementById('msgFile').files[0];
    if (!f) return alert('Choose messages.txt file');
    const fd = new FormData(); fd.append('messages', f);
    const r = await fetch('/upload-messages',{method:'POST',body:fd});
    const j = await r.json();
    document.getElementById('msgStatus').textContent = j.message;
  });

  document.getElementById('runBtn').addEventListener('click', async () => {
    const group_ids = document.getElementById('groupIds').value;
    const task_id = document.getElementById('taskId').value || ('manual_'+Date.now());
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const restart_interval = document.getElementById('restart_interval').value;
    if (!group_ids) return alert('Enter group IDs');
    document.getElementById('runStatus').textContent = 'Starting run...';
    const r = await fetch('/run-once', {
      method:'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({group_ids, task_id, username, password, restart_interval})
    });
    const j = await r.json();
    document.getElementById('runStatus').textContent = j.message || JSON.stringify(j);
  });

  document.getElementById('refreshLogs').addEventListener('click', async () => {
    const r = await fetch('/logs'); const j = await r.json();
    document.getElementById('logs').textContent = j.logs;
  });

  document.getElementById('clearWelcomed').addEventListener('click', async () => {
    if (!confirm('Clear welcomed_users.json? This forgets who was welcomed.')) return;
    const r = await fetch('/clear-welcomed', { method:'POST' }); const j = await r.json();
    alert(j.message);
  });

  // auto-refresh logs every 3s
  setInterval(async () => {
    const r = await fetch('/logs'); const j = await r.json();
    document.getElementById('logs').textContent = j.logs;
  }, 3000);
</script>
</body>
</html>
"""

# Logging helper
def write_log(line):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full = f"[{ts}] {line}"
    print(full, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(full + "\n")
    except Exception as e:
        print("Failed write log:", e)

def load_messages():
    if not os.path.exists(MESSAGES_FILE):
        return []
    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        msgs = [m.strip() for m in content.split("===") if m.strip()]
        write_log(f"✅ Loaded {len(msgs)} messages from messages.txt")
        return msgs
    except Exception as e:
        write_log(f"⚠️ Error loading messages: {e}")
        return []

def load_welcomed():
    if os.path.exists(WELCOMED_FILE):
        try:
            with open(WELCOMED_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_welcomed(s):
    try:
        with open(WELCOMED_FILE, "w", encoding="utf-8") as f:
            json.dump(list(s), f)
    except Exception as e:
        write_log(f"⚠️ Could not save welcomed users: {e}")

def ensure_session(cl, username=None, password=None):
    # Prefer session.json if present
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
            cl.set_settings(settings)
            write_log("🔄 Loaded session.json")
            return True
        except Exception as e:
            write_log(f"⚠️ Failed to load session.json: {e}")
    # If no session, try login if creds provided
    if username and password:
        try:
            cl.login(username, password)
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(cl.get_settings(), f)
            write_log("🔐 Logged in with credentials and saved session.json")
            return True
        except Exception as e:
            write_log(f"❌ Login failed: {e}")
            return False
    write_log("ℹ️ No session.json and no credentials provided")
    return False

def process_group_once(cl, gid, username, messages, welcomed):
    """Check a single group thread id once and send messages to new users found."""
    try:
        thread = cl.direct_thread(gid)
    except Exception as e:
        write_log(f"⚠️ Could not fetch thread {gid}: {e}")
        return []
    results = []
    for user in thread.users:
        try:
            if user.username == username:  # skip self
                continue
            if user.username in welcomed:
                continue
            # send messages sequentially (with small safe delay)
            for msg in messages:
                text = msg.replace("{username}", f"@{user.username}")
                try:
                    cl.direct_send(text, thread_ids=[gid])
                    write_log(f"✅ Sent to @{user.username} in thread {gid}: {text[:50]}...")
                except Exception as e:
                    write_log(f"⚠️ Error sending to @{user.username}: {e}")
                    # If rate-limited, break and bubble up
                    if "rate" in str(e).lower() or "limit" in str(e).lower() or "Please wait" in str(e):
                        write_log("⏸️ Detected rate-limit while sending; pausing further sends in this run.")
                        return [{"user": user.username, "ok": False, "error": str(e)}]
                time.sleep(random.randint(6, 12))
            welcomed.add(user.username)
            save_welcomed(welcomed)
            results.append({"user": user.username, "ok": True})
        except Exception as e:
            write_log(f"⚠️ Error processing user in thread {gid}: {e}")
            results.append({"user": getattr(user, "username", "unknown"), "ok": False, "error": str(e)})
    return results

@app.route("/")
def index():
    # show tail of log file
    logs = ""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = f.read()[-20000:]
    except Exception:
        logs = ""
    return render_template_string(INDEX_HTML, logs=logs)

@app.route("/upload-session", methods=["POST"])
def upload_session():
    f = request.files.get("session")
    if not f:
        return jsonify(ok=False, message="No file uploaded"), 400
    try:
        f.save(SESSION_FILE)
        write_log("📁 session.json uploaded via UI")
        return jsonify(ok=True, message="session.json uploaded")
    except Exception as e:
        write_log(f"⚠️ Upload session failed: {e}")
        return jsonify(ok=False, message=str(e)), 500

@app.route("/upload-messages", methods=["POST"])
def upload_messages():
    f = request.files.get("messages")
    if not f:
        return jsonify(ok=False, message="No file uploaded"), 400
    try:
        f.save(MESSAGES_FILE)
        write_log("📁 messages.txt uploaded via UI")
        return jsonify(ok=True, message="messages.txt uploaded (use === to separate messages)")
    except Exception as e:
        write_log(f"⚠️ Upload messages failed: {e}")
        return jsonify(ok=False, message=str(e)), 500

@app.route("/run-once", methods=["POST"])
def run_once():
    # Single-run manual execution triggered by user
    data = request.json or {}
    group_ids_raw = data.get("group_ids", "")
    task_id = data.get("task_id") or f"manual_{int(time.time())}"
    username = data.get("username")
    password = data.get("password")
    restart_interval = int(data.get("restart_interval", 24))
    group_ids = [g.strip() for g in group_ids_raw.split(",") if g.strip()]
    if not group_ids:
        return jsonify(ok=False, message="Provide at least one group ID"), 400

    # Acquire lock to prevent concurrent manual runs
    if not run_lock.acquire(blocking=False):
        return jsonify(ok=False, message="Another run is in progress. Try later."), 429

    def worker():
        try:
            write_log(f"▶️ Manual run started (task_id={task_id}) for groups: {group_ids}")
            cl = Client()
            if not ensure_session(cl, username, password):
                write_log("❌ Session/login failed — aborting manual run.")
                return
            messages = load_messages()
            if not messages:
                write_log("❌ No messages loaded — aborting.")
                return
            welcomed = load_welcomed()
            for gid in group_ids:
                if gid == "":
                    continue
                write_log(f"🔎 Checking group thread {gid} ...")
                try:
                    res = process_group_once(cl, gid, username or cl.username, messages, welcomed)
                    write_log(f"ℹ️ Results for {gid}: {res}")
                except Exception as e:
                    write_log(f"⚠️ Error during processing group {gid}: {e}")
            write_log(f"✅ Manual run (task_id={task_id}) completed.")
        except Exception as e:
            write_log(f"🛑 Worker crashed: {e}")
            write_log(traceback.format_exc())
        finally:
            run_lock.release()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return jsonify(ok=True, message=f"Manual run started (task_id={task_id}) — check logs.")

@app.route("/clear-welcomed", methods=["POST"])
def clear_welcomed():
    try:
        if os.path.exists(WELCOMED_FILE):
            os.remove(WELCOMED_FILE)
        return jsonify(ok=True, message="welcomed_users cleared")
    except Exception as e:
        return jsonify(ok=False, message=str(e)), 500

@app.route("/logs")
def logs():
    try:
        content = ""
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                content = f.read()[-20000:]
    except Exception:
        content = ""
    return jsonify(ok=True, logs=content)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
