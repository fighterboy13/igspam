import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client

app = Flask(__name__)

BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
SESSION_FILE = "session.json"


def log(msg):
    LOGS.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    print(msg)


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
    return jsonify({"logs": LOGS[-200:]})


PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>INSTA MULTI WELCOME BOT</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600&display=swap');

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  font-family: 'Poppins', sans-serif;
  background: radial-gradient(circle at top left, #0f2027, #203a43, #2c5364);
  color: #fff;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  min-height: 100vh;
  overflow-x: hidden;
}

.container {
  width: 95%;
  max-width: 800px;
  background: rgba(255,255,255,0.05);
  border-radius: 20px;
  padding: 35px 25px;
  box-shadow: 0 0 25px rgba(0,0,0,0.4);
  margin-top: 40px;
}

h1 {
  text-align: center;
  margin-bottom: 30px;
  color: #00eaff;
  letter-spacing: 1px;
  font-size: 26px;
  font-weight: 600;
}

label {
  display: block;
  margin-top: 15px;
  margin-bottom: 5px;
  color: #ccc;
  font-size: 15px;
}

input, textarea, select {
  width: 100%;
  padding: 12px 15px;
  border: none;
  border-radius: 10px;
  background: rgba(255,255,255,0.1);
  color: #fff;
  font-size: 15px;
  outline: none;
}

textarea {
  resize: none;
  height: 100px;
}

button {
  border: none;
  padding: 14px 25px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 12px;
  color: white;
  margin: 10px;
  cursor: pointer;
  transition: 0.3s;
}

.start {
  background: linear-gradient(135deg, #00c6ff, #0072ff);
}
.stop {
  background: linear-gradient(135deg, #ff512f, #dd2476);
}
.sample {
  background: linear-gradient(135deg, #43e97b, #38f9d7);
}
button:hover {
  transform: scale(1.05);
}

.buttons {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  margin-top: 15px;
}

.log-box {
  background: rgba(0,0,0,0.5);
  border-radius: 10px;
  padding: 10px;
  font-size: 14px;
  height: 220px;
  overflow-y: auto;
  margin-top: 10px;
  border: 1px solid rgba(255,255,255,0.1);
}

h3 {
  text-align: center;
  margin-top: 20px;
  color: #9ee7ff;
  font-weight: 500;
}

@media (max-width: 600px) {
  .container {
    padding: 25px 15px;
  }
  h1 {
    font-size: 22px;
  }
  button {
    width: 100%;
  }
}
</style>
</head>
<body>
  <div class="container">
    <h1>INSTA MULTI WELCOME BOT</h1>
    <form id="botForm">
      <label>Instagram Username</label>
      <input type="text" name="username" placeholder="Enter Instagram Username">

      <label>Password</label>
      <input type="password" name="password" placeholder="Enter Password">

      <label>Welcome Messages (each line = 1 message)</label>
      <textarea name="welcome" placeholder="Enter multiple welcome messages here"></textarea>

      <label>Group Chat IDs (comma separated)</label>
      <input type="text" name="group_ids" placeholder="e.g. 24632887389663044,123456789">

      <label>Delay between messages (seconds)</label>
      <input type="number" name="delay" value="3">

      <label>Poll interval (seconds)</label>
      <input type="number" name="poll" value="10">

      <div class="buttons">
        <button type="button" class="start" onclick="startBot()">Start Bot</button>
        <button type="button" class="stop" onclick="stopBot()">Stop Bot</button>
        <button type="button" class="sample" onclick="downloadSample()">Download Sample</button>
      </div>
    </form>

    <h3>Logs</h3>
    <div class="log-box" id="logs">No logs yet.</div>
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
  if(data.logs.length === 0) box.innerHTML = "No logs yet.";
  else box.innerHTML = data.logs.join('<br>');
  box.scrollTop = box.scrollHeight;
}
setInterval(fetchLogs, 2000);

function downloadSample(){
  const text = "Welcome to the group!\\nGlad to have you here.\\nEnjoy chatting!";
  const blob = new Blob([text], {type: 'text/plain'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'welcome_messages.txt';
  link.click();
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
