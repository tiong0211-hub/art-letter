#!/usr/bin/env python3
"""Export comments from the old ChatGPT-hosted server into SQL for D1.

Run on your own computer (needs internet access to the old server):

  python3 export_old_comments.py > import.sql
  npx wrangler d1 execute art-letter-comments --remote --file import.sql

Original authors' delete keys cannot be recovered, so imported comments can
only be deleted with the ADMIN_TOKEN.
"""
import json
import secrets
import sys
import urllib.request

OLD_API = "https://art-letter-gallery-review.bonnyhoneydew.chatgpt.site/api/comments"
ISSUES = sys.argv[1:] or ["2026-11-19", "2026-11-17", "pilot-2026-11-14"]


def q(v):
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"


key = secrets.token_hex(32)
print("-- exported from", OLD_API)
total = 0
for issue in ISSUES:
    req = urllib.request.Request(f"{OLD_API}?issue={issue}", headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=30) as r:
        comments = json.load(r).get("comments", [])
    print(f"-- {issue}: {len(comments)}", file=sys.stderr)
    for c in comments:
        deleted = bool(c.get("deleted"))
        print("INSERT OR IGNORE INTO comments (id, issue, parent_id, nickname, body, owner_hash, ip_hash, created_at, deleted_at) VALUES ("
              + ", ".join([q(c["id"]), q(issue), q(c.get("parentId")), q(c.get("nickname") or "독자"),
                           q(c.get("body") or ""), "NULL", "NULL", q(c["createdAt"]),
                           q(c["createdAt"]) if deleted else "NULL"]) + ");")
        total += 1
print(f"-- total {total}", file=sys.stderr)
