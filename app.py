import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
from instagrapi.exceptions import ClientError, LoginRequired  # Fixed import

app = Flask(__name__)
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
SESSION_FILE = "session.json"
STATS = {"total_welcomed": 0, "today_welcomed": 0, "last_reset": datetime.now().date()}
BOT_CONFIG = {"auto_replies": {}, "auto_reply_active": False, "target_spam": {}, "spam_active": {}, "media_library": {}}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = "[" + ts + "] " + msg
    LOGS.append(lm)
    print(lm)

MUSIC_EMOJIS = ["🎵", "🎶", "🎸", "🎹", "🎤", "🎧", "🎺", "🎷"]
FUNNY = ["Hahaha! 😂", "LOL! 🤣", "Mast! 😆", "Pagal! 🤪", "King! 👑😂"]
MASTI = ["Party! 🎉", "Masti! 🥳", "Dhamaal! 💃", "Full ON! 🔥", "Enjoy! 🎊"]

def get_free_proxy():
    proxies = [
        "http://103.153.39.19:80",
        "http://47.74.66.248:8888", 
        "http://103.175.220.158:5746",
        "http://47.74.79.77:8888",
    ]
    return random.choice(proxies)

def run_bot(un, pw, wm, gids, dly, pol, ucn, ecmd, admin_ids, proxy=None):
    cl = Client()
    
    # Proxy setup
    current_proxy = proxy or get_free_proxy()
    log(f"🔄 Using proxy: {current_proxy}")
    try:
        cl.set_proxy(current_proxy)
        time.sleep(2)
        log("✅ Proxy set successfully!")
    except Exception as e:
        log(f"⚠️ Proxy failed, continuing without: {e}")

    # FIXED LOGIN - Proper exception handling
    max_retries = 3
    for attempt in range(max_retries):
        try:
            log(f"🔐 Login attempt {attempt + 1}/{max_retries}")
            
            if os.path.exists(SESSION_FILE):
                cl.load_settings(SESSION_FILE)
                cl.login(un, pw)
                log("✅ Session loaded & verified")
            else:
                cl.login(un, pw)
                cl.dump_settings(SESSION_FILE)
                log("✅ New session saved")
            break  # Success
            
        except (LoginRequired, ClientError) as e:  # ✅ FIXED: Parentheses added
            log(f"⏳ Login error: {str(e)[:100]}")
            if "blacklist" in str(e).lower() or attempt == max_retries - 1:
                log("🔄 Changing proxy for next attempt...")
                current_proxy = get_free_proxy()
                cl.set_proxy(current_proxy)
            time.sleep(30 * (attempt + 1))
        except Exception as e:
            log(f"❌ Login failed: {e}")
            if attempt == max_retries - 1:
                log("💥 Max retries reached!")
                return
    
    log("🚀 Bot started successfully!")
    log("👑 Admins: " + str(admin_ids))
    
    # Initialize groups
    km = {}
    lm = {}
    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log("✅ Group " + gid + " ready")
        except Exception as e:
            log(f"⚠️ Group {gid} error: {e}")
            km[gid] = set()
            lm[gid] = None
    
    global STATS
    if STATS["last_reset"] != datetime.now().date():
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = datetime.now().date()
    
    while not STOP_EVENT.is_set():
        try:
            for gid in gids:
                if STOP_EVENT.is_set():
                    break
                try:
                    g = cl.direct_thread(gid)
                    
                    # Spam logic
                    if BOT_CONFIG["spam_active"].get(gid, False):
                        tu = BOT_CONFIG["target_spam"].get(gid, {}).get("username")
                        sm = BOT_CONFIG["target_spam"].get(gid, {}).get("message")
                        if tu and sm:
                            cl.direct_send("@" + tu + " " + sm, thread_ids=[gid])
                            log("📨 Spam sent to @" + tu)
                            time.sleep(2)
                    
                    # Command processing (shortened)
                    if ecmd or BOT_CONFIG["auto_reply_active"]:
                        nm = []
                        if lm[gid]:
                            for m in g.messages:
                                if m.id == lm[gid]:
                                    break
                                nm.append(m)
                        
                        for m in reversed(nm):
                            if m.user_id == cl.user_id:
                                continue
                            sender = next((u for u in g.users if u.pk == m.user_id), None)
                            if not sender:
                                continue
                            t = m.text.strip() if m.text else ""
                            tl = t.lower()
                            
                            # Auto reply
                            if BOT_CONFIG["auto_reply_active"] and tl in BOT_CONFIG["auto_replies"]:
                                cl.direct_send(BOT_CONFIG["auto_replies"][tl], thread_ids=[gid])
                            
                            if not ecmd:
                                continue
                            
                            # Basic commands only
                            if tl in ["/ping", "/stats", "/help"]:
                                cl.direct_send("🤖 Bot Active! Use /help for commands", thread_ids=[gid])
                        
                        if g.messages:
                            lm[gid] = g.messages[0].id
                    
                    # Welcome new members
                    cm = {u.pk for u in g.users}
                    nwm = cm - km[gid]
                    if nwm:
                        for u in g.users:
                            if u.pk in nwm and u.username != un:
                                log(f"👋 NEW: @{u.username}")
                                for ms in wm:
                                    fm = (f"@{u.username} " + ms) if ucn else ms
                                    cl.direct_send(fm, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    time.sleep(dly)
                                km[gid].add(u.pk)
                    km[gid] = cm
                    
                except Exception as e:
                    log(f"⚠️ Group {gid} error: {str(e)[:50]}")
            
            time.sleep(pol)
            
        except Exception as e:
            log(f"⚠️ Main loop error: {e}")
            time.sleep(10)
    
    log("🛑 Bot stopped")

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "Bot already running!"})
    
    un = request.form.get("username")
    pw = request.form.get("password")
    wl = [m.strip() for m in request.form.get("welcome", "").splitlines() if m.strip()]
    gids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    proxy_input = request.form.get("proxy", "")
    
    if not all([un, pw, gids, wl]):
        return jsonify({"message": "❌ Fill all required fields!"})
    
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot, 
        args=(un, pw, wl, gids, int(request.form.get("delay", 3)), 
              int(request.form.get("poll", 5)), 
              request.form.get("use_custom_name") == "yes", 
              request.form.get("enable_commands") == "yes", 
              [], proxy_input),
        daemon=True
    )
    BOT_THREAD.start()
    return jsonify({"message": "🚀 Bot started with anti-ban!"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_THREAD
    STOP_EVENT.set()
    if BOT_THREAD:
        BOT_THREAD.join(timeout=5)
    return jsonify({"message": "🛑 Bot stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-100:]})

# Same HTML as before (keeping it short)
PAGE_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>🚀 ANTI-BAN BOT</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial,sans-serif;background:#000;color:#fff;padding:15px}body::before{content:'';position:fixed;top:0;left:0;width:100%;height:100%;background:linear-gradient(45deg,#0f0f23,#1a0033);opacity:.8;z-index:-1}.c{max-width:600px;margin:0 auto;background:rgba(10,10,30,.9);border-radius:20px;padding:25px;border:2px solid #00ffff;box-shadow:0 0 30px rgba(0,255,255,.3)}h1{text-align:center;font-size:45px;background:linear-gradient(90deg,#00ffff,#ff00ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:pulse 2s infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.7}}input,textarea,select{width:100%;padding:12px;margin:8px 0;border-radius:10px;background:rgba(0,20,40,.8);color:#fff;border:2px solid rgba(0,255,255,.4)}input:focus,textarea:focus{outline:0;border-color:#00ffff;box-shadow:0 0 15px rgba(0,255,255,.4)}button{padding:15px 30px;background:linear-gradient(135deg,#00ffff,#0099cc);color:#000;border:none;border-radius:25px;font-weight:700;cursor:pointer;margin:10px;transition:all .3s}button:hover{transform:scale(1.05)}.logs{background:rgba(0,0,0,.8);border:2px solid #00ffff;border-radius:15px;padding:20px;height:300px;overflow-y:auto;font-family:monospace;font-size:14px;margin-top:20px}</style></head><body><div class="c"><h1>🚀 ANTI-BAN BOT</h1><form id="f"><label>👤 Username</label><input name="username" required><label>🔑 Password</label><input type="password" name="password" required><label>📢 Welcome Msgs</label><textarea name="welcome" placeholder="Welcome!&#10;Have fun!">Welcome!&#10;Have fun!</textarea><label>📢 Groups</label><input name="group_ids" placeholder="123456,789012" required><label>🌐 Proxy (Optional)</label><input name="proxy" placeholder="http://user:pass@ip:port"><label>⏱️ Delay</label><input type="number" name="delay" value="3" min="1"><div style="display:flex;gap:10px"><button type="button" onclick="start()">🚀 START</button><button type="button" onclick="stop()">🛑 STOP</button></div></form><div class="logs" id="logs">Waiting...</div></div><script>async function start(){let f=document.getElementById('f');let r=await fetch('/start',{method:'POST',body:new FormData(f)});let res=await r.json();alert(res.message)}async function stop(){let r=await fetch('/stop',{method:'POST'});let res=await r.json();alert(res.message)}setInterval(async()=>{try{let r=await fetch('/logs');let d=await r.json();document.getElementById('logs').innerHTML=d.logs.map(l=>'<div>'+l+'</div>').join('')||'Ready!'}catch(e){}},3000)</script></body></html>"""

if __name__ == "__main__":
    log("🎉 Anti-Ban Bot Deployed on Render!")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
