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

def run_bot(un, pw, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    cl = Client()
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(un, pw)
            log("Session loaded")
        else:
            cl.login(un, pw)
            cl.dump_settings(SESSION_FILE)
            log("Session saved")
    except Exception as e:
        log("Login failed: " + str(e))
        return
    log("Bot started!")
    log("Admins: " + str(admin_ids))
    km = {}
    lm = {}
    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log("Group " + gid + " ready")
        except Exception as e:
            log("Error: " + str(e))
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
                    if BOT_CONFIG["spam_active"].get(gid, False):
                        tu = BOT_CONFIG["target_spam"].get(gid, {}).get("username")
                        sm = BOT_CONFIG["target_spam"].get(gid, {}).get("message")
                        if tu and sm:
                            cl.direct_send("@" + tu + " " + sm, thread_ids=[gid])
                            log("Spam to @" + tu)
                            time.sleep(2)
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
                            su = sender.username.lower()
                            ia = su in [a.lower() for a in admin_ids] if admin_ids else True
                            t = m.text.strip() if m.text else ""
                            tl = t.lower()
                            if BOT_CONFIG["auto_reply_active"] and tl in BOT_CONFIG["auto_replies"]:
                                cl.direct_send(BOT_CONFIG["auto_replies"][tl], thread_ids=[gid])
                                log("Auto-reply sent")
                            if not ecmd:
                                continue
                            if tl in ["/help", "!help"]:
                                cl.direct_send("COMMANDS: /autoreply /stopreply /addvideo /addaudio /video /audio /library /music /funny /masti /kick /spam /stopspam /rules /stats /count /ping /time /about /welcome", thread_ids=[gid])
                                log("Help sent")
                            elif tl in ["/stats", "!stats"]:
                                cl.direct_send("STATS - Total: " + str(STATS['total_welcomed']) + " Today: " + str(STATS['today_welcomed']), thread_ids=[gid])
                            elif tl in ["/count", "!count"]:
                                cl.direct_send("MEMBERS: " + str(len(g.users)), thread_ids=[gid])
                            elif tl in ["/welcome", "!welcome"]:
                                cl.direct_send("@" + sender.username + " Test!", thread_ids=[gid])
                            elif tl in ["/ping", "!ping"]:
                                cl.direct_send("Pong! Alive!", thread_ids=[gid])
                            elif tl in ["/time", "!time"]:
                                cl.direct_send("TIME: " + datetime.now().strftime("%I:%M %p"), thread_ids=[gid])
                            elif tl in ["/about", "!about"]:
                                cl.direct_send("Instagram Bot v3.0 - Full Featured", thread_ids=[gid])
                            elif tl.startswith("/autoreply "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["auto_replies"][p[1].lower()] = p[2]
                                    BOT_CONFIG["auto_reply_active"] = True
                                    cl.direct_send("Auto-reply set: " + p[1] + " -> " + p[2], thread_ids=[gid])
                            elif tl in ["/stopreply", "!stopreply"]:
                                BOT_CONFIG["auto_reply_active"] = False
                                BOT_CONFIG["auto_replies"] = {}
                                cl.direct_send("Auto-reply stopped!", thread_ids=[gid])
                            elif ia and tl.startswith("/addvideo "):
                                p = t.split(" ", 3)
                                if len(p) >= 4:
                                    BOT_CONFIG["media_library"][p[1].lower()] = {"type": "video", "format": p[2].upper(), "link": p[3]}
                                    cl.direct_send("Video saved: " + p[1], thread_ids=[gid])
                            elif ia and tl.startswith("/addaudio "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["media_library"][p[1].lower()] = {"type": "audio", "link": p[2]}
                                    cl.direct_send("Audio saved: " + p[1], thread_ids=[gid])
                            elif tl.startswith("/video "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    n = p[1].lower()
                                    if n in BOT_CONFIG["media_library"] and BOT_CONFIG["media_library"][n]["type"] == "video":
                                        md = BOT_CONFIG["media_library"][n]
                                        cl.direct_send("VIDEO: " + p[1].upper() + " | Type: " + md.get("format", "VIDEO") + " | Watch: " + md["link"], thread_ids=[gid])
                                    else:
                                        cl.direct_send("Video not found!", thread_ids=[gid])
                            elif tl.startswith("/audio "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    n = p[1].lower()
                                    if n in BOT_CONFIG["media_library"] and BOT_CONFIG["media_library"][n]["type"] == "audio":
                                        md = BOT_CONFIG["media_library"][n]
                                        cl.direct_send("AUDIO: " + p[1].upper() + " | Listen: " + md["link"], thread_ids=[gid])
                                    else:
                                        cl.direct_send("Audio not found!", thread_ids=[gid])
                            elif tl in ["/library", "!library"]:
                                if BOT_CONFIG["media_library"]:
                                    vids = [k for k, v in BOT_CONFIG["media_library"].items() if v["type"] == "video"]
                                    auds = [k for k, v in BOT_CONFIG["media_library"].items() if v["type"] == "audio"]
                                    msg = "LIBRARY | Videos: " + ", ".join(vids) if vids else "" + " | Audios: " + ", ".join(auds) if auds else ""
                                    cl.direct_send(msg, thread_ids=[gid])
                                else:
                                    cl.direct_send("Library empty!", thread_ids=[gid])
                            elif tl in ["/music", "!music"]:
                                cl.direct_send("Music! " + " ".join(random.choices(MUSIC_EMOJIS, k=5)), thread_ids=[gid])
                            elif tl in ["/funny", "!funny"]:
                                cl.direct_send(random.choice(FUNNY), thread_ids=[gid])
                            elif tl in ["/masti", "!masti"]:
                                cl.direct_send(random.choice(MASTI), thread_ids=[gid])
                            elif ia and tl.startswith("/kick "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    ku = p[1].replace("@", "")
                                    tg = next((u for u in g.users if u.username.lower() == ku.lower()), None)
                                    if tg:
                                        try:
                                            cl.direct_thread_remove_user(gid, tg.pk)
                                            cl.direct_send("Kicked @" + tg.username, thread_ids=[gid])
                                        except:
                                            cl.direct_send("Cannot kick", thread_ids=[gid])
                            elif tl in ["/rules", "!rules"]:
                                cl.direct_send("RULES: 1.Respect 2.No spam 3.Follow guidelines 4.Have fun!", thread_ids=[gid])
                            elif ia and tl.startswith("/spam "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["target_spam"][gid] = {"username": p[1].replace("@", ""), "message": p[2]}
                                    BOT_CONFIG["spam_active"][gid] = True
                                    cl.direct_send("Spam started", thread_ids=[gid])
                            elif ia and tl in ["/stopspam", "!stopspam"]:
                                BOT_CONFIG["spam_active"][gid] = False
                                cl.direct_send("Spam stopped!", thread_ids=[gid])
                        if g.messages:
                            lm[gid] = g.messages[0].id
                    cm = {u.pk for u in g.users}
                    nwm = cm - km[gid]
                    if nwm:
                        for u in g.users:
                            if u.pk in nwm and u.username != un:
                                if STOP_EVENT.is_set():
                                    break
                                log("NEW: @" + u.username)
                                for ms in wm:
                                    if STOP_EVENT.is_set():
                                        break
                                    fm = ("@" + u.username + " " + ms) if ucn else ms
                                    cl.direct_send(fm, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log("Welcomed @" + u.username)
                                    time.sleep(dly)
                                km[gid].add(u.pk)
                    km[gid] = cm
                except:
                    pass
            time.sleep(pol)
        except:
            pass
    log("Stopped")

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "Running"})
    un = request.form.get("username")
    pw = request.form.get("password")
    wl = [m.strip() for m in request.form.get("welcome", "").splitlines() if m.strip()]
    gids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    adm = [a.strip() for a in request.form.get("admin_ids", "").split(",") if a.strip()]
    if not un or not pw or not gids or not wl:
        return jsonify({"message": "Fill fields"})
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, args=(un, pw, wl, gids, int(request.form.get("delay", 3)), int(request.form.get("poll", 5)), request.form.get("use_custom_name") == "yes", request.form.get("enable_commands") == "yes", adm), daemon=True)
    BOT_THREAD.start()
    return jsonify({"message": "Started!"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    STOP_EVENT.set()
    return jsonify({"message": "Stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-200:]})

PAGE_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>🌟 NEON BOT</title><style>@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&display=swap');*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Orbitron',sans-serif;min-height:100vh;background:#000;background-image:radial-gradient(circle at 20% 50%,rgba(120,0,255,.3) 0%,transparent 50%),radial-gradient(circle at 80% 80%,rgba(255,0,150,.3) 0%,transparent 50%),radial-gradient(circle at 40% 20%,rgba(0,255,255,.3) 0%,transparent 50%);background-size:200% 200%;animation:gradientShift 15s ease infinite;color:#fff;padding:20px}@keyframes gradientShift{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}@keyframes neonPulse{0%,100%{text-shadow:0 0 10px #0ff,0 0 20px #0ff,0 0 30px #0ff}50%{text-shadow:0 0 5px #0ff,0 0 10px #0ff,0 0 15px #0ff}}@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}@keyframes glow{0%,100%{box-shadow:0 0 5px #0ff,0 0 10px #0ff,0 0 15px #0ff}50%{box-shadow:0 0 10px #0ff,0 0 20px #0ff,0 0 30px #0ff}}.c{max-width:1100px;margin:0 auto;background:rgba(10,10,30,.85);border-radius:30px;padding:40px;box-shadow:0 0 50px rgba(0,255,255,.4);border:2px solid rgba(0,255,255,.5);backdrop-filter:blur(10px);animation:float 6s ease-in-out infinite}h1{text-align:center;font-size:48px;font-weight:900;margin-bottom:30px;background:linear-gradient(90deg,#0ff,#f0f,#0ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:neonPulse 2s ease-in-out infinite;letter-spacing:3px;text-transform:uppercase}.fg{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-bottom:30px}.fb{background:linear-gradient(135deg,rgba(0,255,255,.1),rgba(255,0,255,.1));border:2px solid rgba(0,255,255,.4);border-radius:20px;padding:20px;animation:glow 3s ease-in-out infinite}.fb:hover{transform:translateY(-5px)}.ft{color:#0ff;font-size:18px;font-weight:700;margin-bottom:15px;text-transform:uppercase;letter-spacing:2px}.fl{color:#fff;font-size:13px;line-height:1.8;list-style:none}.fl li:before{content:"▸ ";color:#f0f}label{display:block;margin:15px 0 8px;color:#0ff;font-weight:700;font-size:14px;text-transform:uppercase;letter-spacing:1px}.sub{font-size:11px;color:#aaa;margin-top:5px;font-weight:400}input,textarea,select{width:100%;padding:14px;border:2px solid rgba(0,255,255,.4);border-radius:15px;background:rgba(0,20,40,.6);color:#fff;font-size:14px;font-family:'Orbitron',sans-serif}input:focus,textarea:focus,select:focus{outline:0;border-color:#0ff;box-shadow:0 0 15px rgba(0,255,255,.5)}textarea{min-height:90px}.bc{display:flex;justify-content:center;gap:20px;margin-top:30px;flex-wrap:wrap}button{padding:16px 40px;font-size:18px;font-weight:700;border:none;border-radius:50px;cursor:pointer;font-family:'Orbitron',sans-serif;text-transform:uppercase;letter-spacing:2px}.bs{background:linear-gradient(135deg,#0ff,#0af);color:#000;box-shadow:0 0 20px rgba(0,255,255,.5)}.bs:hover{transform:scale(1.05)}.bp{background:linear-gradient(135deg,#f0f,#f06);color:#fff;box-shadow:0 0 20px rgba(255,0,255,.5)}.bp:hover{transform:scale(1.05)}.ls{margin-top:40px}.lt{text-align:center;color:#0ff;font-size:24px;margin-bottom:20px;text-transform:uppercase;letter-spacing:3px}.lb{background:rgba(0,0,0,.7);border:2px solid rgba(0,255,255,.4);border-radius:20px;padding:20px;height:280px;overflow-y:auto;font-family:monospace;font-size:13px;line-height:1.8;box-shadow:inset 0 0 20px rgba(0,255,255,.2)}.le{color:#0ff;margin-bottom:5px}</style></head><body><div class="c"><h1>🌟 NEON BOT 🌟</h1><div class="fg"><div class="fb"><div class="ft">⚡ AUTO</div><ul class="fl"><li>24x7 Auto-Welcome</li><li>Auto-Reply System</li><li>Real-time Detection</li></ul></div><div class="fb"><div class="ft">🎬 MEDIA</div><ul class="fl"><li>YouTube Videos</li><li>Audio Library</li><li>Quick Access</li></ul></div><div class="fb"><div class="ft">🎮 FUN</div><ul class="fl"><li>Funny Messages</li><li>Music Emojis</li><li>Admin Controls</li></ul></div></div><form id="f"><label>🤖 Username</label><input name="username"><label>🔐 Password</label><input type="password" name="password"><label>👑 Admins<div class="sub">admin1,admin2</div></label><input name="admin_ids"><label>💬 Welcome<div class="sub">One per line</div></label><textarea name="welcome" placeholder="Welcome!
Join us!"></textarea><label>Mention?</label><select name="use_custom_name"><option value="yes">Yes</option><option value="no">No</option></select><label>Commands?</label><select name="enable_commands"><option value="yes">Yes</option></select><label>Groups<div class="sub">123,456</div></label><input name="group_ids"><label>Delay</label><input type="number" name="delay" value="3"><label>Poll</label><input type="number" name="poll" value="5"><div class="bc"><button type="button" class="bs" onclick="start()">START</button><button type="button" class="bp" onclick="stop()">STOP</button></div></form><div class="ls"><div class="lt">LOGS</div><div class="lb" id="l">Waiting...</div></div></div><script>async function start(){let r=await fetch('/start',{method:'POST',body:new FormData(document.getElementById('f'))});alert((await r.json()).message)}async function stop(){let r=await fetch('/stop',{method:'POST'});alert((await r.json()).message)}setInterval(async()=>{let r=await fetch('/logs');let d=await r.json();document.getElementById('l').innerHTML=d.logs.map(l=>'<div class="le">'+l+'</div>').join('')||'Start...'},2000)</script></body></html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
