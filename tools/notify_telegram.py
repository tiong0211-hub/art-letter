#!/usr/bin/env python3
"""Send newly published ART LETTER issues to Telegram.

Compares publication.json at two git revisions and posts one message per new
issue. Used by .github/workflows/telegram.yml; works from any machine.

  TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python3 tools/notify_telegram.py BASE_REV
  python3 tools/notify_telegram.py BASE_REV --dry-run     # print instead of sending
"""
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = os.environ.get("SITE_URL", "https://tiong0211-hub.github.io/art-letter/")


def issues_at(rev):
    try:
        raw = subprocess.run(["git", "show", f"{rev}:publication.json"], cwd=ROOT,
                             capture_output=True, check=True, text=True).stdout
        return set(json.loads(raw).get("issues", {}))
    except (subprocess.CalledProcessError, ValueError):
        return set()


def letters():
    text = (ROOT / "index.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r"window\.ARTLETTER_DATA = (\{.*?\n\});\n", text, re.S).group(1))
    return {l["id"]: l for l in data["letters"]}


def message(l):
    art = l["artwork"]
    link = SITE + "#/letter/" + urllib.parse.quote(l["id"])
    e = html.escape
    return (f"🖼 <b>ART LETTER · {e(l['date'])}</b>\n\n"
            f"<b>{e(l['title'])}</b>\n\n"
            f"{e(l['summary'])}\n\n"
            f"<i>{e(l['question'])}</i>\n\n"
            f"— {e(art['artist'])}, 《{e(art['title'][:120])}》\n"
            f"<a href=\"{e(link)}\">레터 읽기 →</a>")


def send(text):
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    body = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "false"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    with urllib.request.urlopen(req, timeout=30) as r:
        if not json.load(r).get("ok"):
            raise RuntimeError("Telegram API refused the message")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    dry = "--dry-run" in args
    base = [a for a in args if a != "--dry-run"][0]
    new_ids = set(json.loads((ROOT / "publication.json").read_text(encoding="utf-8"))["issues"]) - issues_at(base)
    all_letters = letters()
    todo = sorted((all_letters[i] for i in new_ids if i in all_letters), key=lambda l: l["date"])
    if not todo:
        print("no new issues")
        return
    if not dry and not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
        print("::warning::TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set; skipping Telegram")
        return
    for l in todo:
        text = message(l)
        if dry:
            print(text, "\n---")
        else:
            send(text)
            print(f"sent {l['id']}")


if __name__ == "__main__":
    main()
