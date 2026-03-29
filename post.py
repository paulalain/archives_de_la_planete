"""
Instagram Bot — Archives de la Planète
Posts a historical photo every day with a description and geolocation.
"""

import os
import sys
import json
import time
import random
import hashlib
import requests
from datetime import date, datetime


# ─── CONFIG ──────────────────────────────────────────────────────────────────

API_RECORDS = (
    "https://opendata.hauts-de-seine.fr/api/explore/v2.1/catalog/datasets/"
    "archives-de-la-planete/records"
)

IG_USER_ID     = os.environ["IG_USER_ID"]       # Numeric ID of the Instagram Business account
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"] # Meta long-lived access token
GRAPH_URL      = "https://graph.facebook.com/v21.0"

HASHTAGS = (
    "#archivesdelaplanete #albertkahn #autochrome #histoirephotographie "
    "#patrimoine #photographiehistorique #couleurancienne #memoriedumonde "
    "#archivesphoto #debXXsiecle #histoiredumonde #photographiepatrimoine"
)


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def log(msg: str):
    print(f"[{datetime.utcnow().isoformat()}] {msg}", flush=True)


def daily_seed() -> int:
    """Deterministic seed based on today's date → same image if the script is re-run."""
    today = date.today().isoformat()
    return int(hashlib.md5(today.encode()).hexdigest(), 16) % (10 ** 9)


# ─── STEP 1: fetch an image from the API ────────────────────────────────────

def fetch_record() -> dict:
    """
    Fetches a random record that has:
    - an available image ('vignette' or 'image' field)
    - a geolocation
    - a description (title or caption)
    """
    seed = daily_seed()
    params = {
        "where": "geo_point_2d is not null",
        "order_by": f"random({seed})",
        "limit": 1,
    }
    log(f"Calling API with seed={seed}…")
    r = requests.get(API_RECORDS, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    results = data.get("results", [])
    if not results:
        raise ValueError("No records returned by the API.")
    return results[0]


def extract_image_url(record: dict) -> str:
    """Extracts the public image URL from known dataset fields."""
    fields = record.get("fields", record)  # v2.1 returns fields at the root level

    # Search through common dataset field names
    for key in ("vignette", "image", "photo", "fichier"):
        val = fields.get(key)
        if not val:
            continue
        # Opendatasoft sometimes returns a list of dicts with a "url" key
        if isinstance(val, list) and val and isinstance(val[0], dict):
            url = val[0].get("url") or val[0].get("download_url")
            if url:
                return url if url.startswith("http") else "https://opendata.hauts-de-seine.fr" + url
        if isinstance(val, dict):
            url = val.get("url") or val.get("download_url")
            if url:
                return url if url.startswith("http") else "https://opendata.hauts-de-seine.fr" + url
        if isinstance(val, str) and val.startswith("http"):
            return val

    raise ValueError(f"Could not find image URL. Available fields: {list(fields.keys())}")


def extract_geo(record: dict) -> tuple[float, float] | None:
    """Returns (lat, lon) or None."""
    fields = record.get("fields", record)
    geo = fields.get("geo_point_2d")
    if not geo:
        return None
    if isinstance(geo, dict):
        return geo.get("lat"), geo.get("lon")
    if isinstance(geo, list) and len(geo) == 2:
        return geo[0], geo[1]
    return None


def build_caption(record: dict) -> str:
    """Builds the Instagram caption in French."""
    fields = record.get("fields", record)

    titre      = fields.get("titre") or fields.get("title") or ""
    pays       = fields.get("pays") or fields.get("country") or fields.get("localisation") or ""
    date_prise = fields.get("date_de_prise_de_vue") or fields.get("date") or fields.get("annee") or ""
    operateur  = fields.get("operateur") or fields.get("photographe") or ""
    technique  = fields.get("technique") or fields.get("procede") or ""
    description = fields.get("description") or fields.get("legende") or fields.get("caption") or ""

    parts = []

    # Main title
    if titre:
        parts.append(f"📸 {titre}")

    # Description if available and different from title
    if description and description != titre:
        parts.append(f"\n{description}")

    # Contextual metadata
    meta = []
    if pays:
        meta.append(f"📍 {pays}")
    if date_prise:
        meta.append(f"🗓 {date_prise}")
    if operateur:
        meta.append(f"👤 Opérateur : {operateur}")
    if technique:
        meta.append(f"🎨 Technique : {technique}")
    if meta:
        parts.append("\n" + "\n".join(meta))

    # Editorial context
    parts.append(
        "\n🌍 Les Archives de la Planète, initiées par le banquier et philanthrope "
        "Albert Kahn entre 1909 et 1931, constituent la plus grande collection "
        "mondiale d'autochromes — première photographie couleur — avec plus de "
        "72 000 images capturant la diversité des peuples et cultures du début du XXe siècle."
    )

    # Hashtags
    parts.append(f"\n{HASHTAGS}")

    return "\n".join(parts)


# ─── STEP 2: post to Instagram via the Graph API ────────────────────────────

def create_container(image_url: str, caption: str) -> str:
    """Step 1/2: creates the media container and returns the creation_id."""
    url = f"{GRAPH_URL}/{IG_USER_ID}/media"
    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN,
    }
    log("Creating Instagram media container…")
    r = requests.post(url, data=payload, timeout=30)
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"Graph API error (container): {body['error']}")
    creation_id = body.get("id")
    if not creation_id:
        raise RuntimeError(f"No creation_id in response: {body}")
    log(f"Container created: {creation_id}")
    return creation_id


def publish_container(creation_id: str) -> str:
    """Step 2/2: publishes the container and returns the media_id."""
    url = f"{GRAPH_URL}/{IG_USER_ID}/media_publish"
    payload = {
        "creation_id": creation_id,
        "access_token": IG_ACCESS_TOKEN,
    }
    log("Publishing post…")
    r = requests.post(url, data=payload, timeout=30)
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"Graph API error (publish): {body['error']}")
    media_id = body.get("id")
    log(f"✅ Post published successfully! media_id={media_id}")
    return media_id


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    log("=== Archives de la Planète Bot — starting ===")

    # 1. Fetch today's record
    record = fetch_record()
    log(f"Record fetched. Fields: {list(record.keys())}")

    # 2. Extract the required data
    image_url = extract_image_url(record)
    log(f"Image URL: {image_url}")

    geo = extract_geo(record)
    if geo:
        log(f"Geolocation: lat={geo[0]}, lon={geo[1]}")
    else:
        log("⚠️  No geolocation available for this record.")

    caption = build_caption(record)
    log(f"Caption ({len(caption)} chars):\n{caption[:200]}…")

    # Instagram accepts a maximum of 2200 characters
    if len(caption) > 2200:
        caption = caption[:2197] + "…"

    # 3. Post to Instagram (2-step process)
    creation_id = create_container(image_url, caption)
    time.sleep(5)  # Recommended delay by Meta before publishing
    media_id = publish_container(creation_id)

    log(f"=== Done. Instagram post ID: {media_id} ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ ERROR: {e}")
        sys.exit(1)
