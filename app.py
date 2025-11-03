import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client

app = Flask(__name__)

# -------------------- GLOBAL VARIABLES --------------------
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
SESSION_FILE = "session.json"


# -------------------- LOG FUNCTION --------------------
def log(msg):
    LOGS.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    print(msg)


# -------------------- BOT CORE --------------------
def run_bot(username, password, welcome_messages, group_ids, delay, poll_interval):
    cl = Client()
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(username, password)
            log("✅ Loaded existing session.")
        else:
            log("🔑 Logging in fresh...")
            cl.login(username, password)
            cl.dump_settings(SESSION_FILE)
            log("✅ Session saved.")
    except Exception as e:
        log(f"⚠️ Login failed: {e}")
        return

    log("🤖 Bot started — watching groups for new members...")
    welcomed_users = set()

    while not STOP_EVENT.is_set():
        try:
            for gid in group_ids:
                try:
                    group = cl.direct_thread(gid)
                    for user in group.users:
                        if user.pk not in welcomed_users and user.username != username:
                            msg = welcome_messages[int(time.time()) % len(welcome_messages)]
                            cl.direct_send(msg, thread_ids=[gid])
                            log(f"👋 Sent welcome to @{user.username} in group {gid}")
                            welcomed_users.add(user.pk)
                            time.sleep(delay)
                except Exception as e:
                    log(f"⚠️ Error in group {gid}: {e}")
            time.sleep(poll_interval)
        except Exception as e:
            log(f"⚠️ Loop error: {e}")

    log("🛑 Bot stopped.")


# -------------------- FLASK ROUTES --------------------
@app.route("/")
def index():
    return render_template_string(PAGE_HTML)


@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "⚙️ Bot already running."})

    username = request.form.get("username")
    password = request.form.get("password")
    welcome = request.form.get("welcome", "").splitlines()
    welcome = [m.strip() for m in welcome if m.strip()]
    group_ids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    delay = int(request.form.get("delay", 3))
    poll = int(request.form.get("poll", 10))

    if not username or not password or not group_ids or not welcome:
        return jsonify({"message": "⚠️ Please fill all fields."})

    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, args=(username, password, welcome, group_ids, delay, poll))
    BOT_THREAD.start()
    log("🚀 Bot thread started.")
    return jsonify({"message": "✅ Bot started successfully!"})


@app.route("/stop", methods=["POST"])
def stop_bot():
    STOP_EVENT.set()
    log("🛑 Stop signal sent.")
    return jsonify({"message": "🛑 Bot stopped."})


@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-100:]})


# -------------------- FRONTEND (INLINE HTML) --------------------
PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>INSTA MULTI WELCOME BOT</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron&display=swap');
body {
  font-family: 'Orbitron', sans-serif;
  background: radial-gradient(circle at center, #000010, #000000);
  color: #00ffcc;
  text-align: center;
  height: 100vh;
  overflow: hidden;
}
h1 {
  font-size: 30px;
  text-shadow: 0 0 15px #00ffcc;
  margin-top: 20px;
}
.container {
  background: rgba(0, 0, 0, 0.8);
  border-radius: 15px;
  box-shadow: 0 0 25px #00ffcc;
  padding: 20px;
  width: 90%;
  max-width: 700px;
  margin: 30px auto;
}
input, textarea {
  width: 90%;
  background: rgba(0,0,0,0.8);
  border: 1px solid #00ffcc;
  border-radius: 10px;
  padding: 10px;
  color: #00ffcc;
  margin: 8px;
}
button {
  background: #00ffcc;
  color: black;
  border: none;
  border-radius: 10px;
  padding: 10px 25px;
  font-weight: bold;
  cursor: pointer;
  margin: 10px;
}
button:hover {
  background: #00ffaa;
}
.log-box {
  background: black;
  border: 1px solid #00ffcc;
  border-radius: 10px;
  height: 220px;
  overflow-y: scroll;
  text-align: left;
  color: #00ffcc;
  font-size: 13px;
  padding: 10px;
}
</style>
</head>
<body>
  <h1>INSTA MULTI WELCOME BOT</h1>
  <div class="container">
    <form id="botForm">
      <input type="text" name="username" placeholder="Instagram Username" required><br>
      <input type="password" name="password" placeholder="Password" required><br>
      <textarea name="welcome" placeholder="Enter multiple welcome messages (each line = 1 message)" rows="5"></textarea><br>
      <input type="text" name="group_ids" placeholder="Group Chat IDs (comma separated)" required><br>
      <input type="number" name="delay" placeholder="Delay between messages (sec)" value="3"><br>
      <input type="number" name="poll" placeholder="Poll interval (sec)" value="10"><br>
      <button type="button" onclick="startBot()">Start Bot</button>
      <button type="button" onclick="stopBot()">Stop Bot</button>
    </form>
    <h3>Logs</h3>
    <div class="log-box" id="logs"></div>
  </div>

<script>
async function startBot(){
  let form = new FormData(document.getElementById('botForm'));
  let res = await fetch('/start', {method:'POST', body: form});
  let data = await res.json();
  alert(data.message);
}
async function stopBot(){
  let res = await fetch('/stop', {method:'POST'});
  let data = await res.json();
  alert(data.message);
}
async function fetchLogs(){
  let res = await fetch('/logs');
  let data = await res.json();
  let box = document.getElementById('logs');
  box.innerHTML = data.logs.join('<br>');
  box.scrollTop = box.scrollHeight;
}
setInterval(fetchLogs, 2000);
</script>
</body>
</html>
"""

# -------------------- MAIN --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
