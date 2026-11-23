#!/usr/bin/env python3
"""Metropolitan Museum Open Access helper (Python standard library only).

  python3 tools/met.py used                 # Met object IDs already published
  python3 tools/met.py search "wave" [N]    # unused public-domain candidates (image not yet checked)
  python3 tools/met.py fetch ID OUTDIR      # verify object, download Commons image, write artwork.json
                                            # exits non-zero if no public-domain image -> try the next candidate
"""
import datetime
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://collectionapi.metmuseum.org/public/collection/v1"
API_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "ArtLetterPublisher/1.0 (open-access art newsletter; python-urllib)"}
WIKIDATA = "https://www.wikidata.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
IMAGE_WIDTH = 960  # a Commons standard thumbnail size (~150-300 KB); old issues use ~600px


def get(url, binary=False, tries=6):
    """GET with retries. Honors Retry-After on 429/503 (Wikimedia rate limits)."""
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                data = r.read()
            return data if binary else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or i == tries - 1:
                raise
            wait = min(int(e.headers.get("Retry-After") or 0) or 2 ** (i + 2), 90)
        except (urllib.error.URLError, TimeoutError) as e:
            if i == tries - 1:
                raise
            wait = 2 ** (i + 2)
        print(f"retry in {wait}s: {url}", file=sys.stderr)
        time.sleep(wait)


def used_ids():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    return sorted(set(re.findall(r"metmuseum\.org/art/collection/search/(\d+)", html)), key=int)


def commons_image(oid):
    """Public-domain copy of a Met object's image on Wikimedia Commons, found via
    Wikidata property P3634 (The Met object ID) -> P18 (image).
    images.metmuseum.org sits behind bot protection, so we do not download from it."""
    q = urllib.parse.urlencode({"action": "query", "list": "search", "format": "json",
                                "srsearch": f"haswbstatement:P3634={oid}"})
    hits = get(f"{WIKIDATA}?{q}")["query"]["search"]
    if not hits:
        return None
    qid = hits[0]["title"]
    q = urllib.parse.urlencode({"action": "wbgetclaims", "entity": qid, "property": "P18", "format": "json"})
    claims = get(f"{WIKIDATA}?{q}").get("claims", {}).get("P18", [])
    if not claims:
        return None
    filename = claims[0]["mainsnak"]["datavalue"]["value"]
    q = urllib.parse.urlencode({"action": "query", "titles": f"File:{filename}", "prop": "imageinfo",
                                "iiprop": "url|extmetadata|mime", "iiurlwidth": IMAGE_WIDTH, "format": "json"})
    page = next(iter(get(f"{COMMONS}?{q}")["query"]["pages"].values()))
    info = (page.get("imageinfo") or [None])[0]
    if not info:
        return None
    license_name = (info.get("extmetadata", {}).get("LicenseShortName", {}) or {}).get("value", "")
    if not re.search(r"public domain|^PD|CC0", license_name, re.I):
        return None
    return {"wikidata": qid, "file": filename, "url": info.get("thumburl") or info["url"],
            "page": info.get("descriptionurl"), "license": license_name}


def describe(o):
    return {
        "objectID": o["objectID"], "title": o.get("title"), "artist": o.get("artistDisplayName"),
        "date": o.get("objectDate"), "department": o.get("department"),
        "classification": o.get("classification"), "medium": o.get("medium"),
        "isHighlight": o.get("isHighlight"),
    }


def cmd_search(query, limit=15):
    used = set(used_ids())
    # v1 search was retired on 2026-10-01; v1.1 is paginated with offset/limit.
    q = urllib.parse.urlencode({"hasImages": "true", "isPublicDomain": "true", "q": query,
                                "offset": 0, "limit": 80})
    ids = (get(f"{API_SEARCH}?{q}").get("objectIDs") or [])
    out = []
    for oid in ids:
        if str(oid) in used:
            continue
        o = get(f"{API}/objects/{oid}")
        if o.get("isPublicDomain") and o.get("artistDisplayName"):
            out.append(describe(o))
        if len(out) >= limit:
            break
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_fetch(oid, outdir):
    if str(oid) in used_ids():
        sys.exit(f"object {oid} was already published")
    o = get(f"{API}/objects/{oid}")
    if not o.get("isPublicDomain"):
        sys.exit(f"object {oid} is not public domain")
    img = commons_image(oid)
    if not img:
        sys.exit(f"object {oid} has no public-domain image on Wikimedia Commons; pick another")
    raw = get(img["url"], binary=True)
    if not raw.startswith(b"\xff\xd8"):
        sys.exit("downloaded image is not a JPEG; pick another object")
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    name = f"met-{oid}.jpg"
    (out / name).write_bytes(raw)
    artwork = {
        "title": o["title"],
        "artist": o.get("artistDisplayName") or "Unknown",
        "date": o.get("objectDate") or "",
        "institution": "The Metropolitan Museum of Art",
        "sourceUrl": o.get("objectURL") or f"https://www.metmuseum.org/art/collection/search/{oid}",
        "apiUrl": f"{API}/objects/{oid}",
        "image": f"assets/{name}",
        "originalImage": o.get("primaryImageSmall") or o.get("primaryImage") or "",
        "imageSource": img["page"],
        "publicDomain": True,
        "credit": o.get("creditLine") or "",
        "retrievedOn": datetime.date.today().isoformat(),
    }
    (out / "artwork.json").write_text(json.dumps(artwork, ensure_ascii=False, indent=2), encoding="utf-8")
    facts = describe(o) | {"culture": o.get("culture"), "artistNationality": o.get("artistNationality"),
                           "artistDisplayBio": o.get("artistDisplayBio"), "dimensions": o.get("dimensions"),
                           "tags": [t.get("term") for t in (o.get("tags") or [])]}
    (out / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out/name} ({len(raw)//1024} KB), {out/'artwork.json'}, {out/'facts.json'}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["used"]:
        print("\n".join(used_ids()))
    elif len(a) in (2, 3) and a[0] == "search":
        cmd_search(a[1], int(a[2]) if len(a) == 3 else 15)
    elif len(a) == 3 and a[0] == "fetch":
        cmd_fetch(a[1], a[2])
    else:
        sys.exit(__doc__)
