import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientLoginRequiredError, ClientError, PrivateError, PleaseWaitFewMinutes

app = Flask(__name__)

BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
START_TIME = None

STATS = {
    "total_welcomed": 0,
    "today_welcomed": 0,
    "last_reset": datetime.now().date()
}

BOT_CONFIG = {
    "auto_replies": {},
    "auto_reply_active": False,
    "target_spam": {},
    "spam_active": {},
    "media_library": {}
}

def reset_daily_stats():
    today = datetime.now().date()
    if STATS["last_reset"] != today:
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = today

def uptime():
    if not START_TIME:
        return "00:00:00"
    delta = datetime.now() - START_TIME
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    print(lm)

MUSIC_EMOJIS = ["🎵","🎶","🎸","🎹","🎤","🎧"]
FUNNY = ["Hahaha 🤣","LOL 🤣","Mast 😆","Pagal 🤪","King 👑😂"]
MASTI = ["Party 🎉","Masti 🥳","Dhamaal 💃","Full ON 🔥","Enjoy 🎊"]

def safe_client_operation(cl, operation, *args, **kwargs):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return operation(*args, **kwargs)
        except (LoginRequired, ClientLoginRequiredError) as e:
            log(f"❌ Login expired: {str(e)[:50]}")
            return None
        except PleaseWaitFewMinutes as e:
            wait_time = 60 * (attempt + 1)
            log(f"⏳ Rate limited, waiting {wait_time}s")
            time.sleep(wait_time)
            continue
        except ClientError as e:
            log(f"⚠️ Client error (attempt {attempt+1}): {str(e)[:50]}")
            if attempt == max_retries - 1:
                return None
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            log(f"❌ Unexpected error: {str(e)[:50]}")
            return None
    return None

def run_bot(session_token, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    global START_TIME
    START_TIME = datetime.now()
    
    cl = Client()
    
    try:
        if not session_token or len(session_token.strip()) < 100:
            log("❌ Session login failed: Token too short/empty (need 300+ chars)")
            return
        
        log("🔄 Validating session token...")
        log(f"📏 Token length: {len(session_token)} chars")
        
        cl.login_by_sessionid(session_token.strip())
        account_info = safe_client_operation(cl, cl.account_info)
        if not account_info:
            log("❌ Session login failed: Invalid session")
            return
            
        me = account_info.username
        log(f"✅ Session login success: @{me} (ID: {account_info.pk})")
        
    except Exception as e:
        error_msg = str(e).split('
')[0][:100]
        log(f"❌ Session login failed: {error_msg}")
        log("💡 Get fresh token: Instagram.com → F12 → Application → Local Storage → sessionid")
        return

    km = {}
    lm = {}
    
    for gid in gids:
        try:
            thread = safe_client_operation(cl, cl.direct_thread, gid)
            if thread:
                km[gid] = {u.pk for u in thread.users}
                lm[gid] = thread.messages[0].id if thread.messages else None
                BOT_CONFIG["spam_active"][gid] = False
                log(f"✅ Group ready: {gid}")
            else:
                km[gid] = set()
                lm[gid] = None
                log(f"⚠️ Group access failed: {gid}")
        except Exception as e:
            km[gid] = set()
            lm[gid] = None
            log(f"⚠️ Group init failed: {gid}")

    log("🚀 Bot started successfully!")
    
    while not STOP_EVENT.is_set():
        reset_daily_stats()
        
        for gid in gids:
            if STOP_EVENT.is_set():
                break
                
            try:
                thread = safe_client_operation(cl, cl.direct_thread, gid)
                if not thread:
                    time.sleep(2)
                    continue

                if BOT_CONFIG["spam_active"].get(gid):
                    target = BOT_CONFIG["target_spam"].get(gid)
                    if target:
                        msg = f"@{target['username']} {target['message']}"
                        safe_client_operation(cl, cl.direct_send, msg, thread_ids=[gid])
                        log(f"📤 Spam sent to {gid}")
                        time.sleep(2)

                if ecmd or BOT_CONFIG["auto_reply_active"]:
                    new_msgs = []
                    if lm[gid]:
                        for m in thread.messages:
                            if m.id == lm[gid]:
                                break
                            new_msgs.append(m)

                    for m in reversed(new_msgs):
                        if m.user_id == account_info.pk:
                            continue

                        sender = next((u for u in thread.users if u.pk == m.user_id), None)
                        if not sender:
                            continue

                        su = sender.username.lower()
                        is_admin = su in [a.lower() for a in admin_ids] if admin_ids else False
                        text = (m.text or "").strip().lower()

                        if BOT_CONFIG["auto_reply_active"] and text in BOT_CONFIG["auto_replies"]:
                            reply = BOT_CONFIG["auto_replies"][text]
                            safe_client_operation(cl, cl.direct_send, reply, thread_ids=[gid])

                        if not ecmd:
                            continue

                        if text in ["/help", "!help"]:
                            help_msg = "🔥 COMMANDS:
/help /ping /time /uptime
/music /funny /masti
autoreply/spam (admin only)"
                            safe_client_operation(cl, cl.direct_send, help_msg, thread_ids=[gid])

                        elif text in ["/ping", "!ping"]:
                            safe_client_operation(cl, cl.direct_send, "Pong! ✅", thread_ids=[gid])

                        elif text in ["/time", "!time"]:
                            safe_client_operation(cl, cl.direct_send, 
                                datetime.now().strftime("%I:%M %p"), thread_ids=[gid])

                        elif text in ["/uptime", "!uptime"]:
                            safe_client_operation(cl, cl.direct_send, f"Uptime: {uptime()}", thread_ids=[gid])

                        elif text.startswith("/autoreply ") and is_admin:
                            parts = text.split(" ", 2)
                            if len(parts) == 3:
                                BOT_CONFIG["auto_replies"][parts[1].lower()] = parts[2]
                                safe_client_operation(cl, cl.direct_send, f"✅ Set reply for '{parts[1]}'", thread_ids=[gid])

                        elif text in ["/stopreply", "!stopreply"] and is_admin:
                            BOT_CONFIG["auto_reply_active"] = False
                            BOT_CONFIG["auto_replies"] = {}
                            safe_client_operation(cl, cl.direct_send, "❌ Auto-reply stopped", thread_ids=[gid])

                        elif text in ["/music", "!music"]:
                            emojis = " ".join(random.choices(MUSIC_EMOJIS, k=5))
                            safe_client_operation(cl, cl.direct_send, emojis, thread_ids=[gid])

                        elif text in ["/funny", "!funny"]:
                            safe_client_operation(cl, cl.direct_send, random.choice(FUNNY), thread_ids=[gid])

                        elif text in ["/masti", "!masti"]:
                            safe_client_operation(cl, cl.direct_send, random.choice(MASTI), thread_ids=[gid])

                        elif is_admin and text.startswith("/spam "):
                            parts = text.split(" ", 2)
                            if len(parts) == 3:
                                BOT_CONFIG["target_spam"][gid] = {
                                    "username": parts[1].replace("@", ""),
                                    "message": parts[2]
                                }
                                BOT_CONFIG["spam_active"][gid] = True
                                safe_client_operation(cl, cl.direct_send, "🔥 Spam ON", thread_ids=[gid])

                        elif is_admin and text in ["/stopspam", "!stopspam"]:
                            BOT_CONFIG["spam_active"][gid] = False
                            safe_client_operation(cl, cl.direct_send, "⏹️ Spam OFF", thread_ids=[gid])

                    if thread.messages:
                        lm[gid] = thread.messages[0].id

                current_members = {u.pk for u in thread.users}
                new_users = current_members - km[gid]

                for user in thread.users:
                    if user.pk in new_users:
                        for msg in wm:
                            final_msg = f"@{user.username} {msg}" if ucn else msg
                            safe_client_operation(cl, cl.direct_send, final_msg, thread_ids=[gid])
                            STATS["total_welcomed"] += 1
                            STATS["today_welcomed"] += 1
                            log(f"👋 Welcomed: @{user.username}")
                            time.sleep(dly)

                km[gid] = current_members

            except Exception as e:
                log(f"⚠️ Group {gid} error: {str(e)[:50]}")

        time.sleep(pol)

    log("🛑 BOT STOPPED")

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start():
    global BOT_THREAD
    
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "⚠️ Bot already running!"})

    token = request.form.get("session", "").strip()
    welcome_msgs = [x.strip() for x in request.form.get("welcome", "").splitlines() if x.strip()]
    gids = [x.strip() for x in request.form.get("group_ids", "").split(",") if x.strip()]
    admins = [x.strip() for x in request.form.get("admin_ids", "").split(",") if x.strip()]

    if not token or len(token) < 100:
        return jsonify({"message": "❌ Session token required (300+ chars)!"})
    if not welcome_msgs:
        return jsonify({"message": "❌ Welcome messages required!"})
    if not gids:
        return jsonify({"message": "❌ Group IDs required!"})

    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot,
        args=(
            token, welcome_msgs, gids,
            float(request.form.get("delay", 3)),
            float(request.form.get("poll", 5)),
            request.form.get("use_custom_name") == "yes",
            request.form.get("enable_commands") == "yes",
            admins
        ),
        daemon=True
    )
    BOT_THREAD.start()
    log("🎉 Bot started!")
    return jsonify({"message": "🚀 Bot started successfully!"})

@app.route("/stop", methods=["POST"])
def stop():
    STOP_EVENT.set()
    log("🛑 Bot stopping...")
    return jsonify({"message": "⏹️ Bot stopping..."})

@app.route("/logs")
def logs():
    return jsonify({
        "logs": LOGS[-200:], 
        "uptime": uptime(), 
        "status": "running" if BOT_THREAD and BOT_THREAD.is_alive() else "stopped"
    })

@app.route("/stats")
def stats():
    reset_daily_stats()
    return jsonify({
        "uptime": uptime(),
        "status": "running" if BOT_THREAD and BOT_THREAD.is_alive() else "stopped",
        "total_welcomed": STATS["total_welcomed"],
        "today_welcomed": STATS["today_welcomed"]
    })

PAGE_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Premium Instagram Bot ✅</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>*{margin:0;padding:0;box-sizing:border-box;}body{font-family:'Inter',sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:20px;color:#2d3748;}.container{max-width:800px;margin:0 auto;background:rgba(255,255,255,0.95);backdrop-filter:blur(20px);border-radius:24px;box-shadow:0 25px 50px rgba(0,0,0,0.15);overflow:hidden;border:1px solid rgba(255,255,255,0.2);}.header{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:white;padding:30px;text-align:center;position:relative;overflow:hidden;}.header h1{font-size:2.5rem;font-weight:700;margin-bottom:10px;}.status-bar{display:flex;justify-content:space-between;align-items:center;padding:20px 30px;background:#f8fafc;border-bottom:1px solid #e2e8f0;}.status-item{display:flex;align-items:center;gap:8px;font-weight:500;}.status-running{color:#10b981;}.status-stopped{color:#ef4444;}.status-dot{width:12px;height:12px;border-radius:50%;background:#10b981;animation:pulse 2s infinite;}.status-stopped .status-dot{background:#ef4444;}@keyframes pulse{0%{opacity:1;}50%{opacity:0.5;}100%{opacity:1;}}.content{padding:30px;}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:30px;}.form-group{position:relative;}.form-group.full{grid-column:1/-1;}label{display:block;margin-bottom:8px;font-weight:600;color:#374151;font-size:0.95rem;}input,textarea{width:100%;padding:14px 16px;border:2px solid #e5e7eb;border-radius:12px;font-size:1rem;background:white;transition:all 0.3s ease;font-family:inherit;}input:focus,textarea:focus{outline:none;border-color:#4f46e5;box-shadow:0 0 0 3px rgba(79,70,229,0.1);transform:translateY(-1px);}textarea{resize:vertical;min-height:120px;}.checkbox-group{display:flex;align-items:center;gap:12px;padding:16px;background:#f8fafc;border-radius:12px;border:2px solid #e5e7eb;transition:all 0.3s ease;cursor:pointer;}.checkbox-group:hover{border-color:#4f46e5;background:#eff6ff;}.checkbox-group input[type="checkbox"]{width:auto;transform:scale(1.2);}.controls{display:flex;gap:16px;justify-content:center;margin:40px 0;}.btn{padding:16px 40px;border:none;border-radius:16px;font-size:1.1rem;font-weight:600;cursor:pointer;transition:all 0.3s ease;display:flex;align-items:center;gap:10px;text-decoration:none;font-family:inherit;}.btn-start{background:linear-gradient(135deg,#10b981,#059669);color:white;box-shadow:0 10px 25px rgba(16,185,129,0.4);}.btn-start:hover{transform:translateY(-2px);box-shadow:0 15px 35px rgba(16,185,129,0.6);}.btn-stop{background:linear-gradient(135deg,#ef4444,#dc2626);color:white;box-shadow:0 10px 25px rgba(239,68,68,0.4);}.btn-stop:hover{transform:translateY(-2px);box-shadow:0 15px 35px rgba(239,68,68,0.6);}.logs-container{background:#1e293b;border-radius:16px;padding:24px;margin-top:30px;overflow:hidden;}.logs-header{display:flex;justify-content:space-between;align-items:center;color:white;margin-bottom:20px;font-weight:600;}#logs{background:#0f172a;color:#e2e8f0;border-radius:12px;padding:20px;height:300px;overflow-y:auto;font-family:monospace;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;border:1px solid #334155;}.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;margin-bottom:30px;}.stat-card{background:white;padding:24px;border-radius:16px;text-align:center;box-shadow:0 10px 25px rgba(0,0,0,0.1);border:1px solid #e5e7eb;transition:all 0.3s ease;}.stat-card:hover{transform:translateY(-4px);box-shadow:0 20px 40px rgba(0,0,0,0.15);}.stat-number{font-size:2.5rem;font-weight:700;color:#4f46e5;margin-bottom:8px;}.stat-label{color:#6b7280;font-weight:500;}@media(max-width:768px){.form-grid{grid-template-columns:1fr;}.header h1{font-size:2rem;}.controls{flex-direction:column;}}</style>
</head><body>
<div class="container">
<div class="header"><h1><i class="fas fa-robot"></i> Premium Bot</h1><p>Instagram Automation Dashboard</p></div>
<div class="status-bar" id="statusBar"><div class="status-item status-stopped"><div class="status-dot"></div><span>Status: Stopped</span></div><div class="status-item"><span id="uptime">00:00:00</span></div></div>
<div class="content">
<div class="stats-grid" id="statsGrid" style="display:none;"><div class="stat-card"><div class="stat-number" id="totalWelcomed">0</div><div class="stat-label">Total Welcomed</div></div><div class="stat-card"><div class="stat-number" id="todayWelcomed">0</div><div class="stat-label">Today Welcomed</div></div></div>
<form id="botForm">
<div class="form-grid">
<div class="form-group"><label for="session"><i class="fas fa-key"></i> Session Token</label><input type="password" id="session" name="session" placeholder="F12→Application→Local Storage→sessionid" required></div>
<div class="form-group"><label for="admin_ids"><i class="fas fa-users"></i> Admin IDs</label><input type="text" id="admin_ids" name="admin_ids" placeholder="admin1,admin2"></div>
<div class="form-group full"><label for="welcome"><i class="fas fa-comment-dots"></i> Welcome Messages</label><textarea id="welcome" name="welcome">Welcome bro! 🔥
Have fun! 🎉
Enjoy stay! 😊
No spam plz 👮</textarea></div>
<div class="form-group"><label>Group IDs</label><input type="text" name="group_ids" placeholder="1234567890,0987654321" required></div>
<div class="form-group"><label>Delay (s)</label><input type="number" name="delay" value="3" min="1" max="10"></div>
<div class="form-group"><label>Poll (s)</label><input type="number" name="poll" value="5" min="2" max="30"></div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:30px;">
<div class="checkbox-group" onclick="toggleCheckbox('use_custom_name')"><input type="checkbox" id="use_custom_name" name="use_custom_name" value="yes" checked><label for="use_custom_name" style="cursor:pointer;flex:1;margin:0;"><i class="fas fa-user-tag"></i> @username</label></div>
<div class="checkbox-group" onclick="toggleCheckbox('enable_commands')"><input type="checkbox" id="enable_commands" name="enable_commands" value="yes" checked><label for="enable_commands" style="cursor:pointer;flex:1;margin:0;"><i class="fas fa-terminal"></i> Commands</label></div>
</div>
<div class="controls"><button type="button" class="btn btn-start" onclick="startBot()"><i class="fas fa-play"></i> Start</button><button type="button" class="btn btn-stop" onclick="stopBot()"><i class="fas fa-stop"></i> Stop</button></div>
</form>
<div class="logs-container"><div class="logs-header"><div><i class="fas fa-list"></i> Live Logs</div><button onclick="clearLogs()" style="background:none;border:1px solid #94a3b8;color:white;padding:8px 16px;border-radius:8px;cursor:pointer;">Clear</button></div><div id="logs">🚀 Bot ready! Get sessionid from browser</div></div>
</div></div>
<script>
let statusInterval;
function toggleCheckbox(id){document.getElementById(id).click();}
async function startBot(){try{const formData=new FormData(document.getElementById('botForm'));const token=formData.get('session');if(!token||token.length<100)return alert('❌ Token 300+ chars!');const response=await fetch('/start',{method:'POST',body:formData});const result=await response.json();alert('✅'+result.message);updateStatus();}catch(e){alert('❌'+e.message);}}
async function stopBot(){try{const response=await fetch('/stop',{method:'POST'});const result=await response.json();alert('✅'+result.message);updateStatus();}catch(e){alert('❌'+e.message);}}
async function updateStatus(){try{const r=await fetch('/stats');const d=await r.json();document.getElementById('uptime').textContent=d.uptime;const sb=document.getElementById('statusBar');const sd=sb.querySelector('.status-dot');const st=sb.querySelector('span');if(d.status==='running'){sb.classList.remove('status-stopped');sb.classList.add('status-running');sd.style.background='#10b981';st.textContent='Status: Running';document.getElementById('statsGrid').style.display='grid';document.getElementById('totalWelcomed').textContent=d.total_welcomed;document.getElementById('todayWelcomed').textContent=d.today_welcomed;}else{sb.classList.add('status-stopped');sb.classList.remove('status-running');sd.style.background='#ef4444';st.textContent='Status: Stopped';document.getElementById('statsGrid').style.display='none';}}catch(e){}}
async function updateLogs(){try{const r=await fetch('/logs');const d=await r.json();document.getElementById('logs').textContent=d.logs.join('\
');document.getElementById('logs').scrollTop=document.getElementById('logs').scrollHeight;}catch(e){}}
function clearLogs(){document.getElementById('logs').textContent='🧹 Cleared!';}
statusInterval=setInterval(()=>{updateStatus();updateLogs();},2000);updateStatus();updateLogs();
</script></body></html>"""

if __name__ == "__main__":
    print("🚀 Premium Instagram Bot Starting...")
    print("📱 Session Token: F12 → Application → Local Storage → sessionid")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
