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
BOT_CONFIG = {"auto_replies": {}, "auto_reply_active": False, "locked_group_names": {}, "target_spam": {}, "spam_active": {}}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = "[" + ts + "] " + msg
    LOGS.append(lm)
    print(lm)

MUSIC_EMOJIS = ["🎵", "🎶", "🎸", "🎹", "🎤", "🎧", "🎺", "🎷"]
FUNNY_MSGS = ["Hahaha! 😂", "LOL! Bahut funny! 🤣", "Mast joke tha! 😆", "Dimag ka dahi ho gaya! 🤪", "Comedy king! 👑😂"]
MASTI_MSGS = ["Chalo party karte hain! 🎉", "Masti time! 🥳", "Dhamaal macha dete hain! 💃", "Full masti mode ON! 🔥", "Enjoy karo dosto! 🎊"]

def run_bot(un, pw, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    cl = Client()
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(un, pw)
            log("Session loaded.")
        else:
            log("Logging in...")
            cl.login(un, pw)
            cl.dump_settings(SESSION_FILE)
            log("Session saved.")
    except Exception as e:
        log("Login failed: " + str(e))
        return
    log("Bot started - Monitoring...")
    log("Admin IDs: " + str(admin_ids))
    km = {}
    lm = {}
    original_names = {}
    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            original_names[gid] = g.thread_title
            BOT_CONFIG["spam_active"][gid] = False
            log("Tracking " + str(len(km[gid])) + " members in " + gid)
        except Exception as e:
            log("Error loading " + gid + ": " + str(e))
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
                    if gid in BOT_CONFIG["locked_group_names"]:
                        locked_name = BOT_CONFIG["locked_group_names"][gid]
                        if g.thread_title != locked_name:
                            try:
                                cl.direct_thread_rename(gid, locked_name)
                                log("Group name restored to: " + locked_name)
                            except:
                                pass
                    if BOT_CONFIG["spam_active"].get(gid, False):
                        target_username = BOT_CONFIG["target_spam"].get(gid, {}).get("username")
                        spam_msg = BOT_CONFIG["target_spam"].get(gid, {}).get("message")
                        if target_username and spam_msg:
                            cl.direct_send("@" + target_username + " " + spam_msg, thread_ids=[gid])
                            log("Spam sent to @" + target_username)
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
                            sender_username = sender.username.lower()
                            is_admin = sender_username in [aid.lower() for aid in admin_ids] if admin_ids else True
                            t = m.text.strip() if m.text else ""
                            tl = t.lower()
                            if BOT_CONFIG["auto_reply_active"] and tl in BOT_CONFIG["auto_replies"]:
                                reply = BOT_CONFIG["auto_replies"][tl]
                                cl.direct_send(reply, thread_ids=[gid])
                                log("Auto-reply: " + tl + " -> " + reply)
                            if not ecmd:
                                continue
                            if tl in ["/help", "!help"]:
                                help_msg = "COMMANDS: /help /stats /count /welcome /ping /time /about /autoreply /stopreply /lockname /unlockname /music /youtube /image /funny /masti /kick /rules /spam /stopspam"
                                cl.direct_send(help_msg, thread_ids=[gid])
                                log("Help sent")
                            elif tl in ["/stats", "!stats"]:
                                cl.direct_send("STATS - Total: " + str(STATS['total_welcomed']) + " Today: " + str(STATS['today_welcomed']), thread_ids=[gid])
                                log("Stats sent")
                            elif tl in ["/count", "!count"]:
                                mc = len(g.users)
                                cl.direct_send("MEMBERS - Total: " + str(mc), thread_ids=[gid])
                                log("Count sent")
                            elif tl in ["/welcome", "!welcome"]:
                                cl.direct_send("@" + sender.username + " Test welcome!", thread_ids=[gid])
                                log("Test welcome")
                            elif tl in ["/ping", "!ping"]:
                                cl.direct_send("Pong! Bot is alive!", thread_ids=[gid])
                                log("Ping reply")
                            elif tl in ["/time", "!time"]:
                                ct = datetime.now().strftime("%I:%M %p")
                                cl.direct_send("TIME: " + ct, thread_ids=[gid])
                                log("Time sent")
                            elif tl in ["/about", "!about"]:
                                cl.direct_send("ABOUT - Insta Bot v3.0 - Full Featured Bot", thread_ids=[gid])
                                log("About sent")
                            elif tl.startswith("/autoreply ") or tl.startswith("!autoreply "):
                                parts = t.split(" ", 2)
                                if len(parts) >= 3:
                                    trigger = parts[1].lower()
                                    response = parts[2]
                                    BOT_CONFIG["auto_replies"][trigger] = response
                                    BOT_CONFIG["auto_reply_active"] = True
                                    cl.direct_send("Auto-reply set: " + trigger + " -> " + response, thread_ids=[gid])
                                    log("Auto-reply added: " + trigger)
                            elif tl in ["/stopreply", "!stopreply"]:
                                BOT_CONFIG["auto_reply_active"] = False
                                BOT_CONFIG["auto_replies"] = {}
                                cl.direct_send("Auto-reply stopped!", thread_ids=[gid])
                                log("Auto-reply stopped")
                            elif is_admin and (tl.startswith("/lockname ") or tl.startswith("!lockname ")):
                                parts = t.split(" ", 1)
                                if len(parts) >= 2:
                                    new_name = parts[1]
                                    BOT_CONFIG["locked_group_names"][gid] = new_name
                                    cl.direct_thread_rename(gid, new_name)
                                    cl.direct_send("Group name locked: " + new_name, thread_ids=[gid])
                                    log("Name locked: " + new_name)
                            elif is_admin and (tl in ["/unlockname", "!unlockname"]):
                                if gid in BOT_CONFIG["locked_group_names"]:
                                    del BOT_CONFIG["locked_group_names"][gid]
                                cl.direct_send("Group name unlocked!", thread_ids=[gid])
                                log("Name unlocked")
                            elif tl in ["/music", "!music"]:
                                music = " ".join(random.choices(MUSIC_EMOJIS, k=5))
                                cl.direct_send("Playing music! " + music, thread_ids=[gid])
                                log("Music sent")
                            elif tl.startswith("/youtube ") or tl.startswith("!youtube "):
                                parts = t.split(" ", 1)
                                if len(parts) >= 2:
                                    song = parts[1]
                                    cl.direct_send("Playing on YouTube: " + song + " 🎵", thread_ids=[gid])
                                    log("YouTube: " + song)
                            elif tl in ["/image", "!image"]:
                                cl.direct_send("Image feature - Upload image via /setimage command", thread_ids=[gid])
                                log("Image info sent")
                            elif tl in ["/funny", "!funny"]:
                                cl.direct_send(random.choice(FUNNY_MSGS), thread_ids=[gid])
                                log("Funny sent")
                            elif tl in ["/masti", "!masti"]:
                                cl.direct_send(random.choice(MASTI_MSGS), thread_ids=[gid])
                                log("Masti sent")
                            elif is_admin and (tl.startswith("/kick ") or tl.startswith("!kick ")):
                                parts = t.split(" ", 1)
                                if len(parts) >= 2:
                                    kick_user = parts[1].replace("@", "")
                                    target = next((u for u in g.users if u.username.lower() == kick_user.lower()), None)
                                    if target:
                                        try:
                                            cl.direct_thread_remove_user(gid, target.pk)
                                            cl.direct_send("Kicked @" + target.username, thread_ids=[gid])
                                            log("Kicked: @" + target.username)
                                        except:
                                            cl.direct_send("Cannot kick admin/owner", thread_ids=[gid])
                            elif tl in ["/rules", "!rules"]:
                                rules = "GROUP RULES: 1. Be respectful 2. No spam 3. Follow guidelines 4. Have fun!"
                                cl.direct_send(rules, thread_ids=[gid])
                                log("Rules sent")
                            elif is_admin and (tl.startswith("/spam ") or tl.startswith("!spam ")):
                                parts = t.split(" ", 2)
                                if len(parts) >= 3:
                                    target_user = parts[1].replace("@", "")
                                    spam_message = parts[2]
                                    BOT_CONFIG["target_spam"][gid] = {"username": target_user, "message": spam_message}
                                    BOT_CONFIG["spam_active"][gid] = True
                                    cl.direct_send("Spam started to @" + target_user, thread_ids=[gid])
                                    log("Spam started: @" + target_user)
                            elif is_admin and (tl in ["/stopspam", "!stopspam"]):
                                BOT_CONFIG["spam_active"][gid] = False
                                cl.direct_send("Spam stopped!", thread_ids=[gid])
                                log("Spam stopped")
                        if g.messages:
                            lm[gid] = g.messages[0].id
                    cm = {u.pk for u in g.users}
                    nwm = cm - km[gid]
                    if nwm:
                        for u in g.users:
                            if u.pk in nwm and u.username != un:
                                if STOP_EVENT.is_set():
                                    break
                                for ms in wm:
                                    if STOP_EVENT.is_set():
                                        break
                                    if ucn:
                                        fm = "@" + u.username + " " + ms
                                    else:
                                        fm = ms
                                    cl.direct_send(fm, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log("Welcomed @" + u.username)
                                    for _ in range(dly):
                                        if STOP_EVENT.is_set():
                                            break
                                        time.sleep(1)
                                    if STOP_EVENT.is_set():
                                        break
                                km[gid].add(u.pk)
                    km[gid] = cm
                except Exception as e:
                    log("Error in " + gid + ": " + str(e))
            if STOP_EVENT.is_set():
                break
            for _ in range(pol):
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
        return jsonify({"message": "Already running."})
    un = request.form.get("username")
    pw = request.form.get("password")
    wl = request.form.get("welcome", "").splitlines()
    wl = [m.strip() for m in wl if m.strip()]
    gids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    admin_input = request.form.get("admin_ids", "").strip()
    admin_ids = [a.strip() for a in admin_input.split(",") if a.strip()] if admin_input else []
    dly = int(request.form.get("delay", 3))
    pol = int(request.form.get("poll", 5))
    ucn = request.form.get("use_custom_name") == "yes"
    ecmd = request.form.get("enable_commands") == "yes"
    if not un or not pw or not gids or not wl:
        return jsonify({"message": "Fill all fields."})
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, args=(un, pw, wl, gids, dly, pol, ucn, ecmd, admin_ids), daemon=True)
    BOT_THREAD.start()
    log("Bot started.")
    return jsonify({"message": "Bot started!"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_THREAD
    STOP_EVENT.set()
    log("Stopping...")
    if BOT_THREAD:
        BOT_THREAD.join(timeout=5)
    log("Stopped.")
    return jsonify({"message": "Bot stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-200:]})

@app.route("/stats")
def get_stats():
    return jsonify(STATS)

PAGE_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>INSTA BOT</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial,sans-serif;background:#0f2027;color:#fff;padding:20px}.c{max-width:900px;margin:0 auto;background:rgba(255,255,255,.1);border-radius:15px;padding:30px}h1{text-align:center;margin-bottom:20px;color:#00eaff}.info{background:rgba(67,233,123,.15);border:2px solid rgba(67,233,123,.4);border-radius:10px;padding:15px;margin-bottom:20px;color:#43e97b;font-size:13px;line-height:1.6}.cmd{background:rgba(255,165,0,.15);border:2px solid rgba(255,165,0,.4);border-radius:10px;padding:15px;margin-bottom:20px;color:#ffa500;font-size:12px}label{display:block;margin:10px 0 5px;color:#00eaff;font-weight:600}.sub{font-size:12px;color:#43e97b;margin-top:3px}input,textarea,select{width:100%;padding:10px;border:2px solid rgba(0,234,255,.3);border-radius:8px;background:rgba(255,255,255,.1);color:#fff;font-size:14px}textarea{min-height:80px}button{padding:12px 25px;font-size:16px;font-weight:700;border:none;border-radius:8px;color:#fff;margin:8px 4px;cursor:pointer}.st{background:#00c6ff}.sp{background:#ff512f}.lb{background:rgba(0,0,0,.6);border-radius:12px;padding:15px;margin-top:25px;height:250px;overflow-y:auto;border:2px solid rgba(0,234,255,.3);font-family:monospace;font-size:13px}</style></head><body><div class="c"><h1>INSTA FULL FEATURED BOT</h1><div class="info"><strong>ALL FEATURES INCLUDED</strong><br>Auto-welcome, Commands, Auto-reply, Name Lock, Music, YouTube, Funny/Masti, Admin Controls, Spam Target, Group Rules</div><div class="cmd"><strong>ALL COMMANDS:</strong><br>/autoreply trigger response - Set auto reply<br>/stopreply - Stop auto replies<br>/lockname NAME - Lock group name (admin)<br>/unlockname - Unlock name (admin)<br>/music - Play music emojis<br>/youtube SONG - YouTube song<br>/funny - Random funny msg<br>/masti - Masti message<br>/kick @username - Kick member (admin)<br>/rules - Show group rules<br>/spam @username MESSAGE - Spam user (admin)<br>/stopspam - Stop spam (admin)<br>Plus: /help /stats /count /welcome /ping /time /about</div><form id="f"><label>Bot Username</label><input name="username" placeholder="Instagram username"><label>Bot Password</label><input type="password" name="password" placeholder="Password"><label>Admin Usernames<div class="sub">Comma separated - admin1,admin2 (optional)</div></label><input name="admin_ids" placeholder="admin_username1,admin_username2"><label>Welcome Messages</label><textarea name="welcome" placeholder="Line 1 Line 2"></textarea><label>Mention Username?</label><select name="use_custom_name"><option value="yes">Yes</option><option value="no">No</option></select><label>Enable Commands?</label><select name="enable_commands"><option value="yes">Yes</option><option value="no">No</option></select><label>Group IDs</label><input name="group_ids" placeholder="123,456"><label>Delay</label><input type="number" name="delay" value="3"><label>Check Interval</label><input type="number" name="poll" value="5"><div style="text-align:center;margin-top:15px"><button type="button" class="st" onclick="start()">Start</button><button type="button" class="sp" onclick="stop()">Stop</button></div></form><h3 style="text-align:center;margin-top:30px;color:#00eaff">Logs</h3><div class="lb" id="l">Start bot...</div></div><script>async function start(){let d=new FormData(document.getElementById('f'));let r=await fetch('/start',{method:'POST',body:d});let j=await r.json();alert(j.message)}async function stop(){let r=await fetch('/stop',{method:'POST'});let j=await r.json();alert(j.message)}async function getLogs(){let r=await fetch('/logs');let j=await r.json();document.getElementById('l').innerHTML=j.logs.join('<br>')||'Start...'}setInterval(getLogs,2000)</script></body></html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
