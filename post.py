"""
Instagram Bot — Archives de la Planète
Posts a historical photo every day with a description and geolocation.
"""

import os
import sys
import time
import hashlib
import requests
from datetime import date, datetime


# ─── CONFIG ──────────────────────────────────────────────────────────────────

API_BASE    = "https://opendata.hauts-de-seine.fr/api/explore/v2.1/catalog/datasets/archives-de-la-planete"
API_RECORDS = f"{API_BASE}/records"

IG_USER_ID      = os.environ["IG_USER_ID"]       # Numeric ID of the Instagram Business account
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]  # Meta long-lived access token
GRAPH_URL       = "https://graph.facebook.com/v21.0"

# Candidate geo field names — probed at startup to find the real one
GEO_FIELD_CANDIDATES = ["geo_point_2d", "localisation_gps", "geolocalisation", "geopoint", "geo"]

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


# ─── STEP 0: discover the real geo field name ────────────────────────────────

def discover_geo_field() -> str | None:
    """
    Fetches one record with no filter and inspects the returned fields to find
    which geo field name the dataset actually uses.
    Falls back to trying each candidate in a filtered query if needed.
    """
    log("Discovering geo field name…")

    # First, grab one unrestricted record and check what fields exist
    r = requests.get(API_RECORDS, params={"limit": 1}, timeout=30)
    r.raise_for_status()
    sample = r.json().get("results", [{}])[0]
    log(f"Dataset fields: {list(sample.keys())}")

    for candidate in GEO_FIELD_CANDIDATES:
        if candidate in sample:
            log(f"Geo field found in schema: '{candidate}'")
            return candidate

    # If none matched by name, try each candidate in a WHERE clause
    # — catches renamed or aliased fields not obvious from a single record
    for candidate in GEO_FIELD_CANDIDATES:
        try:
            r = requests.get(
                API_RECORDS,
                params={"where": f"{candidate} is not null", "limit": 1},
                timeout=30,
            )
            if r.status_code == 200 and r.json().get("results"):
                log(f"Geo field confirmed via query: '{candidate}'")
                return candidate
        except Exception:
            continue

    log("⚠️  No geo field found — will fetch records without geo filter.")
    return None


# ─── STEP 1: fetch an image from the API ────────────────────────────────────

def fetch_record(geo_field: str | None) -> dict:
    """
    Fetches a random record for today. If a geo field was discovered,
    restricts results to geolocated records only.
    """
    seed = daily_seed()
    params = {
        "order_by": f"random({seed})",
        "limit": 1,
    }
    if geo_field:
        params["where"] = f"{geo_field} is not null"

    log(f"Calling API with seed={seed}…")
    r = requests.get(API_RECORDS, params=params, timeout=30)
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        raise ValueError("No records returned by the API.")
    return results[0]


def extract_image_url(record: dict) -> str:
    """Extracts the public image URL from known dataset fields."""
    # v2.1 returns fields at the root level (no nested 'fields' key)
    fields = record.get("fields", record)

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


def extract_geo(record: dict, geo_field: str | None) -> tuple[float, float] | None:
    """Returns (lat, lon) from the discovered geo field, or None."""
    if not geo_field:
        return None
    fields = record.get("fields", record)
    geo = fields.get(geo_field)
    if not geo:
        return None
    if isinstance(geo, dict):
        # Common shapes: {"lat": x, "lon": y} or {"latitude": x, "longitude": y}
        lat = geo.get("lat") or geo.get("latitude")
        lon = geo.get("lon") or geo.get("longitude")
        return (lat, lon) if lat and lon else None
    if isinstance(geo, list) and len(geo) == 2:
        return geo[0], geo[1]
    return None


def build_caption(record: dict) -> str:
    """Builds the Instagram caption in French."""
    fields = record.get("fields", record)

    titre       = fields.get("titre") or fields.get("title") or ""
    pays        = fields.get("pays") or fields.get("country") or fields.get("localisation") or ""
    date_prise  = fields.get("date_de_prise_de_vue") or fields.get("date") or fields.get("annee") or ""
    operateur   = fields.get("operateur") or fields.get("photographe") or ""
    technique   = fields.get("technique") or fields.get("procede") or ""
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

    # 0. Discover the real geo field name (avoids hardcoding assumptions)
    geo_field = discover_geo_field()

    # 1. Fetch today's record
    record = fetch_record(geo_field)
    log(f"Record fetched. Fields: {list(record.keys())}")

    # 2. Extract the required data
    image_url = extract_image_url(record)
    log(f"Image URL: {image_url}")

    geo = extract_geo(record, geo_field)
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
