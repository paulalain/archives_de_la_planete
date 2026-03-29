"""
Refreshes the Meta long-lived access token (valid for 60 days).
Run manually or schedule as a monthly workflow.

Usage:
  META_APP_ID=xxx META_APP_SECRET=xxx IG_ACCESS_TOKEN=xxx python refresh_token.py
"""

import os
import requests

token = os.environ["IG_ACCESS_TOKEN"]
r = requests.get(
    "https://graph.facebook.com/v21.0/oauth/access_token",
    params={
        "grant_type": "fb_exchange_token",
        "client_id": os.environ["META_APP_ID"],
        "client_secret": os.environ["META_APP_SECRET"],
        "fb_exchange_token": token,
    },
    timeout=15,
)
data = r.json()
if "access_token" in data:
    print("✅ New token:")
    print(data["access_token"])
    print(f"Expires in: {data.get('expires_in', '?')} seconds")
else:
    print("❌ Error:", data)
