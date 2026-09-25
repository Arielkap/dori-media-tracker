#!/usr/bin/env python3
"""
Telegram Alert Sender for Dori Media Tracker
Sends formatted alerts directly via Telegram Bot API.
Zero LLM tokens used.
"""

import os
import sys
import json
import urllib.request
import urllib.error

ENV_PATHS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    "/docker/hermes-agent-umxh/data/.env",
    "/opt/data/.env",
    os.path.expanduser("~/.env")
]

DEFAULT_CHAT_ID = "8929130284"

def get_telegram_token() -> str:
    # 1. Check environment variable
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token.strip("\"' ")

    # 2. Check known .env paths
    for path in ENV_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("TELEGRAM_BOT_TOKEN="):
                            val = line.split("=", 1)[1].strip("\"' ")
                            if val:
                                return val
            except Exception:
                pass
    return None

def send_alert(message: str, chat_id: str = DEFAULT_CHAT_ID) -> bool:
    token = get_telegram_token()
    if not token:
        print("[ERROR] Nie znaleziono TELEGRAM_BOT_TOKEN w środowisku ani plikach .env", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        print(f"[ERROR] Błąd API Telegram ({e.code}): {err_msg}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] Błąd połączenia z Telegramem: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "🐟 <b>Dori:</b> Płyń dalej, płyń dalej... Próba mikrofonu!"
    ok = send_alert(msg)
    print("Wysłano pomyślnie!" if ok else "Błąd wysyłania.")
