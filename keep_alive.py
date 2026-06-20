"""
keep_alive.py — Minimal Flask server to keep Replit alive via UptimeRobot.

Usage:
    Import and call keep_alive() before starting the bot in main.py
    if you need 24/7 uptime on Replit free tier.

    On Replit Deployments (paid) this file is NOT needed — the bot
    runs as a background worker and stays alive automatically.
"""
from threading import Thread
from flask import Flask

app = Flask("")


@app.route("/")
def home():
    return "Genesis Peptide Store — Bot is running ✅"


@app.route("/health")
def health():
    return {"status": "ok"}, 200


def run():
    app.run(host="0.0.0.0", port=5000)


def keep_alive():
    """Start the Flask server in a background thread."""
    t = Thread(target=run)
    t.daemon = True
    t.start()
    print("Keep-alive server started on port 5000")
