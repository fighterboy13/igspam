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
    m = f"[{ts}] {msg}"
    LOGS.append(m)
    print(m)

MUSIC_EMOJIS = ["🎵","🎶","🎸","🎹","🎤","🎧"]
FUNNY = ["Hahaha 🤣","LOL 🤣","Pagal 😂","King 👑😂"]
MASTI = ["Party 🎉","Masti 🥳","Dhamaal 💃","Enjoy 🔥"]

# ================= BOT CORE =================
def run_bot(session_token, welcome_msgs, gids, delay, poll,
            mention_user, enable_cmds, admin_ids):

    cl = Client()

    try:
        cl.login_by_sessionid(session_token)
        me = cl.account_info().username
        log(f"Logged in via SESSION as @{me}")
    except Exception as e:
        log("❌ Session login failed: " + str(e))
        return

    km = {}
    lm = {}

    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log(f"Group ready: {gid}")
        except Exception as e:
            log(f"Group error {gid}: {e}")
            km[gid] = set()
            lm[gid] = None

    while not STOP_EVENT.is_set():
        for gid in gids:
            if STOP_EVENT.is_set():
                break
            try:
                g = cl.direct_thread(gid)

                # ---------- SPAM ----------
                if BOT_CONFIG["spam_active"].get(gid):
                    ts = BOT_CONFIG["target_spam"].get(gid)
                    if ts:
                        cl.direct_send(
                            "@" + ts["username"] + " " + ts["message"],
                            thread_ids=[gid]
                        )
                        log("Spam sent")
                        time.sleep(2)

                # ---------- COMMANDS ----------
                if enable_cmds or BOT_CONFIG["auto_reply_active"]:
                    new_msgs = []
                    if lm[gid]:
                        for m in g.messages:
                            if m.id == lm[gid]:
                                break
                            new_msgs.append(m)

                    for m in reversed(new_msgs):
                        if m.user_id == cl.user_id:
                            continue

                        sender = next((u for u in g.users if u.pk == m.user_id), None)
                        if not sender:
                            continue

                        su = sender.username.lower()
                        is_admin = su in [a.lower() for a in admin_ids] if admin_ids else True
                        txt = (m.text or "").strip()
                        tl = txt.lower()

                        if BOT_CONFIG["auto_reply_active"] and tl in BOT_CONFIG["auto_replies"]:
                            cl.direct_send(BOT_CONFIG["auto_replies"][tl], thread_ids=[gid])

                        if not enable_cmds:
                            continue

                        if tl in ["/help","!help"]:
                            cl.direct_send(
                                "COMMANDS:\n/help /stats /count /ping /time /about\n"
                                "/autoreply key msg\n/stopreply\n"
                                "/music /funny /masti\n"
                                "/spam @user msg\n/stopspam",
                                thread_ids=[gid]
                            )

                        elif tl in ["/ping","!ping"]:
                            cl.direct_send("Pong! ✅", thread_ids=[gid])

                        elif tl in ["/time","!time"]:
                            cl.direct_send(datetime.now().strftime("%I:%M %p"), thread_ids=[gid])

                        elif tl in ["/about","!about"]:
                            cl.direct_send("Instagram Bot v3.0 (SESSION)", thread_ids=[gid])

                        elif tl.startswith("/autoreply "):
                            p = txt.split(" ",2)
                            if len(p)==3:
                                BOT_CONFIG["auto_replies"][p[1].lower()] = p[2]
                                BOT_CONFIG["auto_reply_active"] = True

                        elif tl in ["/stopreply","!stopreply"]:
                            BOT_CONFIG["auto_reply_active"] = False
                            BOT_CONFIG["auto_replies"] = {}

                        elif tl in ["/music","!music"]:
                            cl.direct_send(" ".join(random.choices(MUSIC_EMOJIS,k=5)), thread_ids=[gid])

                        elif tl in ["/funny","!funny"]:
                            cl.direct_send(random.choice(FUNNY), thread_ids=[gid])

                        elif tl in ["/masti","!masti"]:
                            cl.direct_send(random.choice(MASTI), thread_ids=[gid])

                        elif is_admin and tl.startswith("/spam "):
                            p = txt.split(" ",2)
                            if len(p)==3:
                                BOT_CONFIG["target_spam"][gid] = {
                                    "username": p[1].replace("@",""),
                                    "message": p[2]
                                }
                                BOT_CONFIG["spam_active"][gid] = True

                        elif is_admin and tl in ["/stopspam","!stopspam"]:
                            BOT_CONFIG["spam_active"][gid] = False

                    if g.messages:
                        lm[gid] = g.messages[0].id

                # ---------- WELCOME ----------
                cm = {u.pk for u in g.users}
                new_users = cm - km[gid]

                for u in g.users:
                    if u.pk in new_users and u.username != me:
                        for w in welcome_msgs:
                            msg = f"@{u.username} {w}" if mention_user else w
                            cl.direct_send(msg, thread_ids=[gid])
                            STATS["total_welcomed"] += 1
                            STATS["today_welcomed"] += 1
                            time.sleep(delay)

                km[gid] = cm

            except:
                pass

        time.sleep(poll)

    log("🛑 BOT STOPPED")

# ================= FLASK =================
@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start():
    global BOT_THREAD
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message":"Already running"})

    session_token = request.form.get("session")
    welcome = [x.strip() for x in request.form.get("welcome","").splitlines() if x.strip()]
    gids = [x.strip() for x in request.form.get("group_ids","").split(",") if x.strip()]
    admins = [x.strip() for x in request.form.get("admin_ids","").split(",") if x.strip()]

    if not session_token or not welcome or not gids:
        return jsonify({"message":"Fill all fields"})

    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot,
        args=(
            session_token,
            welcome,
            gids,
            int(request.form.get("delay",3)),
            int(request.form.get("poll",5)),
            request.form.get("mention")=="yes",
            request.form.get("commands")=="yes",
            admins
        ),
        daemon=True
    )
    BOT_THREAD.start()
    return jsonify({"message":"Started"})

@app.route("/stop", methods=["POST"])
def stop():
    STOP_EVENT.set()
    return jsonify({"message":"Stopped"})

@app.route("/logs")
def logs():
    return jsonify({"logs": LOGS[-200:]})

# ================= UI =================
PAGE_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>NEON SESSION BOT</title></head>
<body style="background:#000;color:#0ff;font-family:Arial;padding:20px">
<h2>INSTAGRAM SESSION BOT</h2>
<form id="f">
Session Token:<br><input name="session" style="width:100%"><br><br>
Admins:<br><input name="admin_ids"><br><br>
Welcome:<br><textarea name="welcome"></textarea><br><br>
Groups:<br><input name="group_ids"><br><br>
Mention?<select name="mention"><option value="yes">Yes</option></select>
Commands?<select name="commands"><option value="yes">Yes</option></select><br><br>
Delay:<input name="delay" value="3">
Poll:<input name="poll" value="5"><br><br>
<button type="button" onclick="start()">START</button>
<button type="button" onclick="stop()">STOP</button>
</form>
<pre id="l">Waiting...</pre>
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
 l.innerText=d.logs.join("\\n");
},2000)
</script>
</body>
</html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
