import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client

app = Flask(__name__)
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []

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

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    print(lm)

MUSIC_EMOJIS = ["🎵","🎶","🎸","🎹","🎤","🎧","🎺","🎷"]
FUNNY = ["Hahaha 😂","LOL 🤣","Mast 😆","Pagal 🤪","King 👑😂"]
MASTI = ["Party 🎉","Masti 🥳","Dhamaal 💃","Full ON 🔥","Enjoy 🎊"]

# ===================== BOT CORE =====================

def run_bot(session_token, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    cl = Client()

    try:
        cl.set_settings({
            "cookies": {
                "sessionid": session_token
            }
        })
        cl.get_timeline_feed()
        log("Session token login successful ✅")
    except Exception as e:
        log("Session login failed ❌ : " + str(e))
        return

    log("Bot started 🚀")
    log("Admins: " + str(admin_ids))

    known_members = {}
    last_msg = {}

    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            known_members[gid] = {u.pk for u in g.users}
            last_msg[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log(f"Group ready: {gid}")
        except Exception as e:
            log(f"Group error {gid}: {e}")
            known_members[gid] = set()
            last_msg[gid] = None

    while not STOP_EVENT.is_set():
        for gid in gids:
            if STOP_EVENT.is_set():
                break
            try:
                g = cl.direct_thread(gid)

                # ===== SPAM =====
                if BOT_CONFIG["spam_active"].get(gid):
                    t = BOT_CONFIG["target_spam"][gid]
                    cl.direct_send(f"@{t['username']} {t['message']}", thread_ids=[gid])
                    log("Spam sent")
                    time.sleep(2)

                # ===== COMMANDS =====
                if ecmd:
                    new_msgs = []
                    for m in g.messages:
                        if m.id == last_msg[gid]:
                            break
                        new_msgs.append(m)

                    for m in reversed(new_msgs):
                        if m.user_id == cl.user_id:
                            continue

                        sender = next((u for u in g.users if u.pk == m.user_id), None)
                        if not sender:
                            continue

                        text = (m.text or "").strip()
                        tl = text.lower()
                        is_admin = sender.username.lower() in [a.lower() for a in admin_ids] if admin_ids else True

                        if tl in ["/help","!help"]:
                            cl.direct_send(
                                "COMMANDS:\n"
                                "/help\n/ping\n/stats\n/count\n/time\n/about\n"
                                "/autoreply word reply\n/stopreply\n"
                                "/spam @user msg\n/stopspam\n"
                                "/music /funny /masti",
                                thread_ids=[gid]
                            )

                        elif tl in ["/ping","!ping"]:
                            cl.direct_send("Pong! ✅", thread_ids=[gid])

                        elif tl.startswith("/autoreply "):
                            p = text.split(" ",2)
                            BOT_CONFIG["auto_replies"][p[1].lower()] = p[2]
                            BOT_CONFIG["auto_reply_active"] = True
                            cl.direct_send("Auto reply added", thread_ids=[gid])

                        elif tl in ["/stopreply","!stopreply"]:
                            BOT_CONFIG["auto_replies"].clear()
                            BOT_CONFIG["auto_reply_active"] = False
                            cl.direct_send("Auto reply stopped", thread_ids=[gid])

                        elif is_admin and tl.startswith("/spam "):
                            p = text.split(" ",2)
                            BOT_CONFIG["target_spam"][gid] = {
                                "username": p[1].replace("@",""),
                                "message": p[2]
                            }
                            BOT_CONFIG["spam_active"][gid] = True
                            cl.direct_send("Spam started", thread_ids=[gid])

                        elif is_admin and tl in ["/stopspam","!stopspam"]:
                            BOT_CONFIG["spam_active"][gid] = False
                            cl.direct_send("Spam stopped", thread_ids=[gid])

                        elif tl in ["/music","!music"]:
                            cl.direct_send(" ".join(random.choices(MUSIC_EMOJIS,k=5)), thread_ids=[gid])

                        elif tl in ["/funny","!funny"]:
                            cl.direct_send(random.choice(FUNNY), thread_ids=[gid])

                        elif tl in ["/masti","!masti"]:
                            cl.direct_send(random.choice(MASTI), thread_ids=[gid])

                    if g.messages:
                        last_msg[gid] = g.messages[0].id

                # ===== WELCOME =====
                current = {u.pk for u in g.users}
                new_users = current - known_members[gid]

                for u in g.users:
                    if u.pk in new_users:
                        for msg in wm:
                            text = f"@{u.username} {msg}" if ucn else msg
                            cl.direct_send(text, thread_ids=[gid])
                            log(f"Welcomed @{u.username}")
                            time.sleep(dly)

                known_members[gid] = current

            except:
                pass

        time.sleep(pol)

    log("Bot stopped 🛑")

# ===================== FLASK =====================

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start():
    global BOT_THREAD
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message":"Already running"})

    token = request.form.get("session_token")
    wm = request.form.get("welcome","").splitlines()
    gids = request.form.get("group_ids","").split(",")
    admins = request.form.get("admin_ids","").split(",")

    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot,
        args=(token, wm, gids, 3, 5, True, True, admins),
        daemon=True
    )
    BOT_THREAD.start()
    return jsonify({"message":"Bot started"})

@app.route("/stop", methods=["POST"])
def stop():
    STOP_EVENT.set()
    return jsonify({"message":"Stopped"})

@app.route("/logs")
def logs():
    return jsonify({"logs":LOGS[-200:]})

# ===================== UI =====================

PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>SESSION BOT</title>
</head>
<body style="background:#000;color:#0ff">
<h2>Paste Session Token</h2>
<form id="f">
<input name="session_token" style="width:100%" placeholder="sessionid here"><br><br>
<textarea name="welcome" placeholder="Welcome msg"></textarea><br>
<input name="group_ids" placeholder="group ids"><br>
<input name="admin_ids" placeholder="admins"><br><br>
<button type="button" onclick="start()">START</button>
<button type="button" onclick="stop()">STOP</button>
</form>
<pre id="log"></pre>
<script>
async function start(){
 let r=await fetch('/start',{method:'POST',body:new FormData(f)});
 alert((await r.json()).message)
}
async function stop(){
 let r=await fetch('/stop',{method:'POST'});
 alert((await r.json()).message)
}
setInterval(async()=>{
 let r=await fetch('/logs');
 let d=await r.json();
 log.innerText=d.logs.join("\\n")
},2000)
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run("0.0.0.0",5000)
