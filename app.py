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
STATS = {"total_welcomed": 0, "today_welcomed": 0, "last_reset": datetime.now().date()}

def log(msg):
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_msg = "[" + timestamp + "] " + msg
    LOGS.append(log_msg)
    print(log_msg)

def run_bot(username, password, welcome_messages, group_ids, delay, poll_interval, use_custom_name, enable_commands):
    cl = Client()
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(username, password)
            log("Loaded existing session.")
        else:
            log("Logging in fresh...")
            cl.login(username, password)
            cl.dump_settings(SESSION_FILE)
            log("Session saved.")
    except Exception as e:
        log("Login failed: " + str(e))
        return

    log("Bot started - Monitoring for NEW members and COMMANDS...")
    known_members = {}
    last_message_ids = {}
    
    for gid in group_ids:
        try:
            group = cl.direct_thread(gid)
            known_members[gid] = {user.pk for user in group.users}
            last_message_ids[gid] = group.messages[0].id if group.messages else None
            log("Tracking " + str(len(known_members[gid])) + " existing members in group " + gid)
        except Exception as e:
            log("Error loading group " + gid + ": " + str(e))
            known_members[gid] = set()
            last_message_ids[gid] = None

    global STATS
    if STATS["last_reset"] != datetime.now().date():
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = datetime.now().date()

    while not STOP_EVENT.is_set():
        try:
            for gid in group_ids:
                if STOP_EVENT.is_set():
                    break
                try:
                    group = cl.direct_thread(gid)
                    
                    if enable_commands:
                        new_messages = []
                        if last_message_ids[gid]:
                            for msg in group.messages:
                                if msg.id == last_message_ids[gid]:
                                    break
                                new_messages.append(msg)
                        
                        for msg in reversed(new_messages):
                            if msg.user_id == cl.user_id:
                                continue
                            text = msg.text.strip().lower() if msg.text else ""
                            
                            if text in ["/help", "!help"]:
                                help_text = "BOT COMMANDS

/help - Show help
/stats - Statistics
/count - Member count
/welcome - Test welcome
/ping - Check bot
/time - Current time
/about - Bot info"
                                cl.direct_send(help_text, thread_ids=[gid])
                                log("Sent help to group " + gid)
                            elif text in ["/stats", "!stats"]:
                                stats_text = "WELCOME STATISTICS

Total: " + str(STATS['total_welcomed']) + "
Today: " + str(STATS['today_welcomed']) + "
Status: Active
Groups: " + str(len(group_ids))
                                cl.direct_send(stats_text, thread_ids=[gid])
                                log("Sent stats to group " + gid)
                            elif text in ["/count", "!count"]:
                                member_count = len(group.users)
                                count_text = "GROUP MEMBERS

Total: " + str(member_count) + " members"
                                cl.direct_send(count_text, thread_ids=[gid])
                                log("Sent count to group " + gid)
                            elif text in ["/welcome", "!welcome"]:
                                sender = next((u for u in group.users if u.pk == msg.user_id), None)
                                if sender:
                                    test_msg = "@" + sender.username + " Test welcome!"
                                    cl.direct_send(test_msg, thread_ids=[gid])
                                    log("Test welcome to @" + sender.username)
                            elif text in ["/ping", "!ping"]:
                                cl.direct_send("Pong! Bot is alive!", thread_ids=[gid])
                                log("Responded to ping in group " + gid)
                            elif text in ["/time", "!time"]:
                                current_time = datetime.now().strftime("%I:%M %p, %d %b %Y")
                                time_text = "CURRENT TIME

" + current_time
                                cl.direct_send(time_text, thread_ids=[gid])
                                log("Sent time to group " + gid)
                            elif text in ["/about", "!about"]:
                                about_text = "ABOUT BOT

Name: Instagram Welcome Bot
Version: 2.0
Features:
- Auto-welcome
- Commands
- Statistics
- 24/7 monitoring"
                                cl.direct_send(about_text, thread_ids=[gid])
                                log("Sent about to group " + gid)
                        
                        if group.messages:
                            last_message_ids[gid] = group.messages[0].id
                    
                    current_members = {user.pk for user in group.users}
                    new_members = current_members - known_members[gid]
                    
                    if new_members:
                        for user in group.users:
                            if user.pk in new_members and user.username != username:
                                if STOP_EVENT.is_set():
                                    break
                                for msg in welcome_messages:
                                    if STOP_EVENT.is_set():
                                        break
                                    if use_custom_name:
                                        final_msg = "@" + user.username + " " + msg
                                    else:
                                        final_msg = msg
                                    cl.direct_send(final_msg, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log("Welcomed @" + user.username + " in group " + gid)
                                    for _ in range(delay):
                                        if STOP_EVENT.is_set():
                                            break
                                        time.sleep(1)
                                    if STOP_EVENT.is_set():
                                        break
                                known_members[gid].add(user.pk)
                    known_members[gid] = current_members
                except Exception as e:
                    log("Error checking group " + gid + ": " + str(e))
            if STOP_EVENT.is_set():
                break
            for _ in range(poll_interval):
                if STOP_EVENT.is_set():
                    break
                time.sleep(1)
        except Exception as e:
            log("Loop error: " + str(e))
    log("Bot stopped. Total: " + str(STATS['total_welcomed']))

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "Bot already running."})
    username = request.form.get("username")
    password = request.form.get("password")
    welcome = request.form.get("welcome", "").splitlines()
    welcome = [m.strip() for m in welcome if m.strip()]
    group_ids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    delay = int(request.form.get("delay", 3))
    poll = int(request.form.get("poll", 10))
    use_custom_name = request.form.get("use_custom_name") == "yes"
    enable_commands = request.form.get("enable_commands") == "yes"
    if not username or not password or not group_ids or not welcome:
        return jsonify({"message": "Please fill all fields."})
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, args=(username, password, welcome, group_ids, delay, poll, use_custom_name, enable_commands), daemon=True)
    BOT_THREAD.start()
    log("Bot started.")
    return jsonify({"message": "Bot started!"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_THREAD
    STOP_EVENT.set()
    log("Stopping bot...")
    if BOT_THREAD:
        BOT_THREAD.join(timeout=5)
    log("Bot stopped.")
    return jsonify({"message": "Bot stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-200:]})

@app.route("/stats")
def get_stats():
    return jsonify(STATS)

PAGE_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>INSTA BOT</title><style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:Arial,sans-serif;background:#0f2027;color:#fff;padding:20px}.container{max-width:1000px;margin:0 auto;background:rgba(255,255,255,.1);border-radius:20px;padding:40px}h1{text-align:center;margin-bottom:30px;color:#00eaff}label{display:block;margin:15px 0 5px;color:#00eaff;font-weight:600}input,textarea,select{width:100%;padding:12px;border:2px solid rgba(0,234,255,.3);border-radius:10px;background:rgba(255,255,255,.1);color:#fff;font-size:15px}textarea{min-height:100px}button{padding:15px 30px;font-size:18px;font-weight:700;border:none;border-radius:10px;color:#fff;margin:10px 5px;cursor:pointer}.start{background:#00c6ff}.stop{background:#ff512f}.log-box{background:rgba(0,0,0,.6);border-radius:15px;padding:20px;margin-top:30px;height:300px;overflow-y:auto;border:2px solid rgba(0,234,255,.3);font-family:monospace}</style></head><body><div class="container"><h1>INSTA WELCOME BOT</h1><form id="f"><label>Instagram Username</label><input name="username" placeholder="Username"><label>Password</label><input type="password" name="password" placeholder="Password"><label>Welcome Messages</label><textarea name="welcome" placeholder="Line 1: Welcome!
Line 2: Enjoy!"></textarea><label>Mention Username?</label><select name="use_custom_name"><option value="yes">Yes</option><option value="no">No</option></select><label>Enable Commands?</label><select name="enable_commands"><option value="yes">Yes</option><option value="no">No</option></select><label>Group IDs</label><input name="group_ids" placeholder="123,456"><label>Delay (sec)</label><input type="number" name="delay" value="3"><label>Check Interval (sec)</label><input type="number" name="poll" value="10"><div style="text-align:center;margin-top:20px"><button type="button" class="start" onclick="start()">Start</button><button type="button" class="stop" onclick="stop()">Stop</button></div></form><h3 style="text-align:center;margin-top:40px;color:#00eaff">Logs</h3><div class="log-box" id="logs">Start bot...</div></div><script>async function start(){let d=new FormData(document.getElementById('f'));let r=await fetch('/start',{method:'POST',body:d});let j=await r.json();alert(j.message)}async function stop(){let r=await fetch('/stop',{method:'POST'});let j=await r.json();alert(j.message)}async function getLogs(){let r=await fetch('/logs');let j=await r.json();document.getElementById('logs').innerHTML=j.logs.join('<br>')||'Start bot...'}setInterval(getLogs,2000)</script></body></html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
