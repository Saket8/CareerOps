#!/usr/bin/env python3
"""Helper script to detect and update CareerOps Telegram Channel ID."""

import os
import sys
import json
import urllib.request
from pathlib import Path
import yaml

CONFIG_PATH = Path("/u01/CareerOps/config/config.yaml")
ENV_PATH = Path("/u01/CareerOps/.env")

def get_token():
    # Check .env first
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    return os.getenv("TELEGRAM_BOT_TOKEN", "")

def check_updates():
    token = get_token()
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                print(f"Error from Telegram API: {data}")
                return None
            
            results = data.get("result", [])
            channels_found = []
            for item in reversed(results):
                # Channel post or my_chat_member update
                chat = None
                if "channel_post" in item:
                    chat = item["channel_post"].get("chat")
                elif "my_chat_member" in item:
                    chat = item["my_chat_member"].get("chat")
                elif "message" in item and item["message"].get("chat", {}).get("type") in ("channel", "supergroup", "group"):
                    chat = item["message"].get("chat")
                
                if chat and chat.get("type") in ("channel", "supergroup"):
                    cid = str(chat.get("id"))
                    title = chat.get("title", "Unknown")
                    if (cid, title) not in channels_found:
                        channels_found.append((cid, title))
            
            return channels_found
    except Exception as e:
        print(f"Exception connecting to Telegram: {e}")
        return None

if __name__ == "__main__":
    found = check_updates()
    if found:
        print(f"Found channels: {found}")
    else:
        print("No channel detected yet. Please add the bot as Admin to the channel and post a message.")
