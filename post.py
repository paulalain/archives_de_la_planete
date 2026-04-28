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

GITHUB_TOKEN    = os.environ["GITHUB_TOKEN"]     # Provided automatically by GitHub Actions
GITHUB_REPO     = "paulalain/archives_de_la_planete"
GITHUB_API      = "https://api.github.com"

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
    Fetches a random geolocated record with an available image.
    Filters on geo_point (the confirmed field name) and photo_ftp (image field).
    Uses a date-based random seed so the same image is picked if re-run today.
    """
    seed = daily_seed()
    params = {
        "where": "geo_point is not null and photo_ftp is not null",
        "order_by": f"random({seed})",
        "limit": 1,
    }
    log(f"Calling API with seed={seed}…")
    r = requests.get(API_RECORDS, params=params, timeout=30)
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        raise ValueError("No records returned by the API.")
    return results[0]


def extract_image_url(record: dict) -> str:
    """
    Extracts the public image URL from the photo_ftp field.
    photo_ftp can be a string URL, a dict with a 'url' key,
    or a list of such dicts (Opendatasoft attachment format).
    """
    val = record.get("photo_ftp")
    if not val:
        raise ValueError(f"No photo_ftp field in record. Available fields: {list(record.keys())}")

    def normalise(url: str) -> str:
        if not url.startswith("http"):
            url = "https://opendata.hauts-de-seine.fr" + url
        return url

    if isinstance(val, str) and val.startswith("http"):
        return normalise(val)

    if isinstance(val, dict):
        url = val.get("url") or val.get("download_url")
        if url:
            return normalise(url)

    if isinstance(val, list) and val:
        first = val[0]
        if isinstance(first, dict):
            url = first.get("url") or first.get("download_url")
            if url:
                return normalise(url)
        if isinstance(first, str) and first.startswith("http"):
            return normalise(first)

    raise ValueError(f"Could not parse image URL from photo_ftp value: {val!r}")


def extract_geo(record: dict) -> tuple[float, float] | None:
    """
    Returns (lat, lon) from the geo_point field, or None.
    Handles dict shapes {"lat": x, "lon": y} and list shape [lat, lon].
    """
    geo = record.get("geo_point")
    if not geo:
        return None
    if isinstance(geo, dict):
        lat = geo.get("lat") or geo.get("latitude")
        lon = geo.get("lon") or geo.get("longitude")
        return (lat, lon) if lat and lon else None
    if isinstance(geo, list) and len(geo) == 2:
        return geo[0], geo[1]
    return None


def build_caption(record: dict) -> str:
    """Builds the Instagram caption in French using the confirmed field names."""
    titre       = record.get("legende_originale_titre") or record.get("legende_revisee") or ""
    description = record.get("legende_revisee") or ""
    pays        = record.get("pays") or record.get("lieu_actuel") or record.get("lieu") or ""
    date_prise  = record.get("date_de_prise_de_vue") or ""
    operateur   = record.get("operateur") or ""
    technique   = record.get("procede_technique") or ""
    themes      = record.get("themes") or ""
    ville       = record.get("ville") or ""
    region      = record.get("region") or ""

    parts = []

    # Main title
    if titre:
        parts.append(f"📸 {titre}")

    # Revised caption if different from title
    if description and description != titre:
        parts.append(f"\n{description}")

    # Contextual metadata
    meta = []
    location_parts = [v for v in [ville, region, pays] if v]
    if location_parts:
        meta.append(f"📍 {', '.join(location_parts)}")
    if date_prise:
        meta.append(f"🗓 {date_prise}")
    if operateur:
        meta.append(f"👤 Opérateur : {operateur}")
    if technique:
        meta.append(f"🎨 Technique : {technique}")
    if themes:
        # themes may be a list or a comma-separated string
        if isinstance(themes, list):
            themes = ", ".join(themes)
        meta.append(f"🏷 {themes}")
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

    caption = "\n".join(parts)

    # Instagram accepts a maximum of 2200 characters
    if len(caption) > 2200:
        caption = caption[:2197] + "…"

    return caption


# ─── IMAGE REHOSTING via GitHub Releases ─────────────────────────────────────

def rehost_image(source_url: str) -> str:
    """
    Downloads the image and uploads it as a GitHub Release asset.
    Returns a public URL with a .jpg extension that Meta can fetch.
    GitHub Actions provides GITHUB_TOKEN automatically — no extra secrets needed.
    """
    today = date.today().isoformat()
    tag = f"daily-image-{today}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Reuse the release if it already exists (e.g. script re-run today)
    r = requests.get(f"{GITHUB_API}/repos/{GITHUB_REPO}/releases/tags/{tag}", headers=headers, timeout=15)
    if r.status_code == 200:
        release_id = r.json()["id"]
        log(f"Reusing existing GitHub release {tag} (id={release_id})")
    else:
        log(f"Creating GitHub release {tag}…")
        body = requests.post(
            f"{GITHUB_API}/repos/{GITHUB_REPO}/releases",
            headers=headers,
            json={"tag_name": tag, "name": tag, "body": "Daily image for Instagram post."},
            timeout=15,
        )
        body.raise_for_status()
        release_id = body.json()["id"]

    # Delete existing photo.jpg asset if present (e.g. from a previous failed run)
    assets_r = requests.get(f"{GITHUB_API}/repos/{GITHUB_REPO}/releases/{release_id}/assets", headers=headers, timeout=15)
    assets_r.raise_for_status()
    for asset in assets_r.json():
        if asset["name"] == "photo.jpg":
            log(f"Deleting existing asset {asset['id']}…")
            requests.delete(f"{GITHUB_API}/repos/{GITHUB_REPO}/releases/assets/{asset['id']}", headers=headers, timeout=15)

    log("Downloading source image…")
    img_r = requests.get(source_url, timeout=30)
    img_r.raise_for_status()

    log("Uploading image to GitHub Release…")
    upload_url = f"https://uploads.github.com/repos/{GITHUB_REPO}/releases/{release_id}/assets?name=photo.jpg"
    up = requests.post(
        upload_url,
        headers={**headers, "Content-Type": "image/jpeg"},
        data=img_r.content,
        timeout=60,
    )
    up.raise_for_status()
    public_url = up.json()["browser_download_url"]

    # Resolve redirects — Meta doesn't follow them
    resolved = requests.head(public_url, allow_redirects=True, timeout=15).url
    log(f"Image hosted at: {resolved}")
    return resolved


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


def create_story_container(image_url: str) -> str:
    """Creates a Story media container from an image URL, returns the creation_id."""
    url = f"{GRAPH_URL}/{IG_USER_ID}/media"
    payload = {
        "image_url": image_url,
        "media_type": "STORIES",
        "link_sticker": '{"link_url":"https://www.instagram.com/archives_de_la_planete/"}',
        "access_token": IG_ACCESS_TOKEN,
    }
    log("Creating Instagram Story container…")
    r = requests.post(url, data=payload, timeout=30)
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"Graph API error (story container): {body['error']}")
    creation_id = body.get("id")
    if not creation_id:
        raise RuntimeError(f"No creation_id in story response: {body}")
    log(f"Story container created: {creation_id}")
    return creation_id


def publish_story(creation_id: str) -> str:
    """Publishes the Story container and returns the media_id."""
    url = f"{GRAPH_URL}/{IG_USER_ID}/media_publish"
    payload = {
        "creation_id": creation_id,
        "access_token": IG_ACCESS_TOKEN,
    }
    log("Publishing Story…")
    r = requests.post(url, data=payload, timeout=30)
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"Graph API error (story publish): {body['error']}")
    media_id = body.get("id")
    log(f"✅ Story published successfully! media_id={media_id}")
    return media_id


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    log("=== Archives de la Planète Bot — starting ===")

    # 1. Fetch today's record (filtered on geo_point + photo_ftp)
    record = fetch_record()
    log(f"Record fetched: {record.get('identifiant_fakir', '?')} — {record.get('legende_originale_titre', '')}")

    # 2. Extract image URL and rehost on GitHub Releases so Meta can fetch it
    image_url = extract_image_url(record)
    log(f"Source image URL: {image_url}")
    image_url = rehost_image(image_url)

    geo = extract_geo(record)
    if geo:
        log(f"Geolocation: lat={geo[0]}, lon={geo[1]}")
    else:
        log("⚠️  No geolocation for this record.")

    # 3. Build caption
    caption = build_caption(record)
    log(f"Caption ({len(caption)} chars):\n{caption[:300]}…")

    # 4. Post to Instagram (2-step process)
    creation_id = create_container(image_url, caption)
    time.sleep(5)  # Recommended delay by Meta before publishing
    media_id = publish_container(creation_id)

    # 5. Share the same image as a Story
    story_creation_id = create_story_container(image_url)
    time.sleep(5)
    story_media_id = publish_story(story_creation_id)

    log(f"=== Done. Post ID: {media_id} — Story ID: {story_media_id} ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ ERROR: {e}")
        sys.exit(1)
