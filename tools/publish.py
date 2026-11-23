#!/usr/bin/env python3
"""ART LETTER publishing tool (Python standard library only).

The rules live here and in PUBLISHING.md, so any person or any LLM gets the
same result.

  python3 tools/publish.py verify               # check index.html against publication.json
  python3 tools/publish.py add LETTER.json IMG  # publish a new letter (newest first)
  python3 tools/publish.py rehash               # recompute publication.json from index.html
  python3 tools/publish.py set-comments-api URL  # point the discussion at a comments server
"""
import base64
import hashlib
import json
import mimetypes
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "index.html"
MANIFEST = ROOT / "publication.json"
MANIFEST_VERSION = 2
HASH_SPEC = "artletter-issue-v2"

CONFIG_RE = re.compile(r"(window\.ARTLETTER_CONFIG=)(\{.*?\})(;)")
DATA_RE = re.compile(r"(window\.ARTLETTER_DATA = )(\{.*?\n\})(;\n)", re.S)
IMAGES_RE = re.compile(r"(\(\(\)=>\{const images=)(\{.*?\})(;)")

# Fields that change when a newer letter is added; not part of an issue's identity.
POSITIONAL_FIELDS = ("order", "featured")
REQUIRED_FIELDS = ("id", "title", "question", "category", "body", "summary",
                   "reflection", "date", "artwork")
# Reader-facing topic filters. Add one here deliberately rather than ad hoc.
CATEGORIES = ("자연과 우주", "철학과 인간", "일상과 감정", "시간과 기억", "관계와 사회")
REQUIRED_ARTWORK = ("title", "artist", "date", "institution", "sourceUrl",
                    "image", "publicDomain", "credit", "retrievedOn")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> bytes:
    """Canonical JSON: sorted keys, no whitespace, UTF-8 (no \\u escapes)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------- html i/o
def load():
    html = HTML.read_text(encoding="utf-8")
    m, mi = DATA_RE.search(html), IMAGES_RE.search(html)
    if not m or not mi:
        sys.exit("index.html: ARTLETTER_DATA or images block not found")
    return html, json.loads(m.group(2)), json.loads(mi.group(2))


def save(html, data, images):
    html = DATA_RE.sub(lambda m: m.group(1) + json.dumps(data, indent=2, ensure_ascii=False) + m.group(3), html, count=1)
    html = IMAGES_RE.sub(lambda m: m.group(1) + json.dumps(images) + m.group(3), html, count=1)
    HTML.write_text(html, encoding="utf-8")


def resolve_image(path: str, images: dict) -> bytes:
    """Image bytes for a reference: embedded data URI (older issues) or a file
    under the site root such as assets/met-123.jpg (newer issues)."""
    if path in images:
        return image_bytes(images[path])
    f = (ROOT / path).resolve()
    if path.startswith("assets/") and f.is_file() and ROOT in f.parents:
        return f.read_bytes()
    raise KeyError(f"image {path!r} is neither embedded nor a file in assets/")


def image_bytes(data_uri: str) -> bytes:
    if not data_uri.startswith("data:") or ";base64," not in data_uri:
        raise ValueError("image is not a base64 data URI")
    return base64.b64decode(data_uri.split(";base64,", 1)[1])


# ---------------------------------------------------------------- hashing
def issue_hash(letter: dict, images: dict) -> str:
    """sha256 of the canonical letter, with positional fields removed and every
    image reference replaced by "sha256:<hash of the image bytes>"."""
    def swap(path):
        return "sha256:" + sha256(resolve_image(path, images))

    doc = json.loads(json.dumps(letter))
    for f in POSITIONAL_FIELDS:
        doc.pop(f, None)
    if "image" in doc:
        doc["image"] = swap(doc["image"])
    doc["artwork"]["image"] = swap(doc["artwork"]["image"])
    for a in doc.get("artworks", []):
        a["image"] = swap(a["image"])
    return sha256(canonical(doc))


def build_manifest(data, images, html_text):
    return {
        "hash_spec": HASH_SPEC,
        "html_sha256": sha256(html_text.encode("utf-8")),
        "issues": {l["id"]: issue_hash(l, images) for l in data["letters"]},
        "version": MANIFEST_VERSION,
    }


def write_manifest(manifest):
    MANIFEST.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------- checks
def structural_errors(data, images):
    errs, letters = [], data["letters"]
    ids = [l.get("id") for l in letters]
    if len(set(ids)) != len(ids):
        errs.append("duplicate letter ids")
    for l in letters:
        for f in REQUIRED_FIELDS:
            if not l.get(f):
                errs.append(f"{l.get('id')}: missing {f}")
        art = l.get("artwork") or {}
        for f in REQUIRED_ARTWORK:
            if art.get(f) in (None, ""):
                errs.append(f"{l.get('id')}: artwork missing {f}")
        if art.get("publicDomain") is not True:
            errs.append(f"{l.get('id')}: artwork must be public domain")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(l.get("date", ""))):
            errs.append(f"{l.get('id')}: date must be YYYY-MM-DD")
    dates = [l.get("date", "") for l in letters]
    if dates != sorted(dates, reverse=True):
        errs.append("letters must be ordered newest first")
    if [l.get("order") for l in letters] != list(range(1, len(letters) + 1)):
        errs.append("order must be 1..n in list order")
    if [bool(l.get("featured")) for l in letters] != [i == 0 for i in range(len(letters))]:
        errs.append("exactly the first (newest) letter must be featured")
    used = set()
    for l in letters:
        used.update({l.get("image"), l["artwork"].get("image")} | {a.get("image") for a in l.get("artworks", [])})
    used.discard(None)
    for p in sorted(used - images.keys()):
        try:
            resolve_image(p, images)
        except KeyError as e:
            errs.append(str(e))
    for p in sorted(images.keys() - used):
        errs.append(f"image {p} embedded but unused")
    return errs


# ---------------------------------------------------------------- commands
def cmd_verify():
    html, data, images = load()
    errs = structural_errors(data, images)
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"publication.json unreadable: {e}")
    if manifest.get("hash_spec") != HASH_SPEC or manifest.get("version") != MANIFEST_VERSION:
        errs.append(f"publication.json is not {HASH_SPEC} / version {MANIFEST_VERSION}")
    else:
        expected = build_manifest(data, images, html)
        if manifest["html_sha256"] != expected["html_sha256"]:
            errs.append("html_sha256 does not match index.html")
        want, have = expected["issues"], manifest.get("issues", {})
        for i in sorted(want.keys() | have.keys()):
            if want.get(i) != have.get(i):
                errs.append(f"issue {i}: hash mismatch (manifest {have.get(i)}, actual {want.get(i)})")
    if errs:
        print("VERIFY FAILED"); [print(" -", e) for e in errs]; sys.exit(1)
    print(f"OK: {len(data['letters'])} letters, manifest matches index.html")


def cmd_rehash():
    html, data, images = load()
    errs = structural_errors(data, images)
    if errs:
        print("refusing to rehash:"); [print(" -", e) for e in errs]; sys.exit(1)
    write_manifest(build_manifest(data, images, html))
    print("publication.json updated")


def cmd_add(letter_path, image_path):
    html, data, images = load()
    letter = json.loads(Path(letter_path).read_text(encoding="utf-8"))
    img = Path(image_path)
    raw = img.read_bytes()
    mime = mimetypes.guess_type(img.name)[0]
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        sys.exit(f"unsupported image type: {img.name}")
    key = letter.get("artwork", {}).get("image") or f"assets/{img.name}"
    if not re.fullmatch(r"assets/[A-Za-z0-9._-]+", key):
        sys.exit(f"image path must look like assets/<name>: {key}")
    if key in images:
        sys.exit(f"{key} is already embedded")
    target = ROOT / key
    if target.exists() and target.read_bytes() != raw:
        sys.exit(f"{key} already exists with different bytes")
    if any(l["id"] == letter.get("id") for l in data["letters"]):
        sys.exit(f"letter id {letter.get('id')} already published")

    if letter.get("category") not in CATEGORIES:
        sys.exit(f"category must be one of {CATEGORIES}")
    letter.setdefault("status", "verified")
    letter["image"] = key
    letter["artwork"]["image"] = key
    letter.setdefault("artworks", [dict(letter["artwork"])])
    for a in letter["artworks"]:
        a.setdefault("image", key)
    # New issues keep images as separate files so index.html stays small.
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(raw)

    data["letters"].insert(0, letter)
    data["letters"].sort(key=lambda l: l["date"], reverse=True)
    for i, l in enumerate(data["letters"], 1):
        l["order"], l["featured"] = i, i == 1
    # Keep a stable key order: positional fields right after status, as before.
    data["letters"] = [_reorder(l) for l in data["letters"]]
    data["editionLabel"] = f"{data['letters'][0]['date'][:7]} · ART LETTER"

    errs = structural_errors(data, images)
    if errs:
        print("refusing to publish:"); [print(" -", e) for e in errs]; sys.exit(1)
    save(html, data, images)
    new_html, new_data, new_images = load()
    write_manifest(build_manifest(new_data, new_images, new_html))
    print(f"published {letter['id']}; run `python3 tools/publish.py verify`")


def cmd_set_comments_api(url):
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(:\d+)?/[^\s\"'<>]*", url):
        sys.exit("URL must be https://host/path")
    html, data, images = load()
    m = CONFIG_RE.search(html)
    if not m:
        sys.exit("index.html: ARTLETTER_CONFIG not found")
    config = json.loads(m.group(2))
    config["commentsApi"] = url
    html = CONFIG_RE.sub(lambda m: m.group(1) + json.dumps(config) + m.group(3), html, count=1)
    HTML.write_text(html, encoding="utf-8")
    write_manifest(build_manifest(data, images, html))
    print(f"commentsApi = {url}")


KEY_ORDER = ["id", "title", "question", "category", "body", "summary", "reflection",
             "date", "status", "order", "featured", "image", "artwork", "artworks"]


def _reorder(l):
    out = {k: l[k] for k in KEY_ORDER if k in l}
    out.update({k: v for k, v in l.items() if k not in out})
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["verify"]:
        cmd_verify()
    elif args == ["rehash"]:
        cmd_rehash()
    elif len(args) == 2 and args[0] == "set-comments-api":
        cmd_set_comments_api(args[1])
    elif len(args) == 3 and args[0] == "add":
        cmd_add(args[1], args[2])
    else:
        sys.exit(__doc__)
