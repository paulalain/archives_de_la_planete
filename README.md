# 📸 Archives de la Planète — Instagram Bot

An automated bot that posts a historical photograph every day to an Instagram account, sourced from the [Archives de la Planète](https://opendata.hauts-de-seine.fr/explore/dataset/archives-de-la-planete/) open dataset — a collection of over 72,000 autochromes (early colour photographs) captured between 1909 and 1931 by operators commissioned by philanthropist Albert Kahn.

**Completely free to run.** No server, no subscription.  
Powered by **GitHub Actions** (2,000 free minutes/month — the script runs in ~30 seconds).

---

## How it works

Each day, the bot:
1. Calls the open data API with a date-based seed to pick a unique, reproducible image
2. Extracts the image URL, geolocation, title, date, and photographer
3. Composes a French-language caption with editorial context and hashtags
4. Posts to Instagram via the Meta Graph API (two-step: create container → publish)

---

## Project structure

```
.
├── post.py                        # Main script — fetches image and posts to Instagram
├── refresh_token.py               # Helper to renew the Meta access token (run monthly)
├── requirements.txt
└── .github/
    └── workflows/
        └── daily_post.yml         # GitHub Actions schedule (runs daily at ~9am Paris time)
```

---

## Prerequisites

- A **GitHub account** (free)
- An **Instagram Business or Creator account** (cannot be a personal account)
- A **Facebook Page** linked to your Instagram account
- A **Meta developer app** with Instagram Graph API access

---

## Setup guide

### Part 1 — Prepare your Instagram account

**Step 1 — Switch to a Professional account**

1. Open Instagram on mobile
2. Go to your profile → ☰ → Settings → Account
3. Scroll to the bottom → **Switch to Professional Account**
4. Choose **Creator** or **Business** (both work)

**Step 2 — Link a Facebook Page**

The Instagram Graph API requires your account to be linked to a Facebook Page.

1. Go to [facebook.com](https://facebook.com) → **Create a Page**
2. Give it any name (e.g. `Archives de la Planète`)
3. In Instagram: Settings → **Linked Accounts** → Facebook → connect the page you just created

---

### Part 2 — Create a Meta developer app

**Step 3 — Create the app**

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Click **My Apps → Create App**
3. Type: **Business**
4. Give it a name (e.g. `ArchivesBot`)
5. Note down the **App ID** and **App Secret** (Settings → Basic)

**Step 4 — Add Instagram Graph API**

1. In your app dashboard → **Add a Product** → **Instagram Graph API** → Set Up
2. In the left menu: **Instagram → Basic Settings**

**Step 5 — Generate an access token**

1. Open the [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Select your app in the top-right dropdown
3. Click **Generate Access Token**
4. Grant the following permissions:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
5. Click **Generate Token** and copy it

**Step 6 — Exchange for a long-lived token (valid 60 days)**

Short-lived tokens expire in 1 hour. Exchange it for a long-lived one:

```bash
curl -i -X GET "https://graph.facebook.com/v21.0/oauth/access_token \
  ?grant_type=fb_exchange_token \
  &client_id=YOUR_APP_ID \
  &client_secret=YOUR_APP_SECRET \
  &fb_exchange_token=YOUR_SHORT_TOKEN"
```

Copy the `access_token` value from the response — this is your **long-lived token**.

**Step 7 — Get your Instagram User ID**

First, list your Facebook Pages:

```bash
curl "https://graph.facebook.com/v21.0/me/accounts?access_token=YOUR_LONG_TOKEN"
```

Then use your Page ID to get the linked Instagram Business account ID:

```bash
curl "https://graph.facebook.com/v21.0/YOUR_PAGE_ID?fields=instagram_business_account&access_token=YOUR_LONG_TOKEN"
```

The `id` value inside `instagram_business_account` is your **IG_USER_ID**.

---

### Part 3 — Set up the GitHub repository

**Step 8 — Fork or clone this repository**

```bash
git clone https://github.com/YOUR_USERNAME/archives-de-la-planete-bot.git
cd archives-de-la-planete-bot
```

Or click **Fork** at the top of this page to copy it into your own GitHub account.

**Step 9 — Add your secrets**

In your repository, go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name       | Value                                      |
|-------------------|--------------------------------------------|
| `IG_USER_ID`      | Your Instagram numeric user ID (Step 7)    |
| `IG_ACCESS_TOKEN` | Your long-lived Meta access token (Step 6) |

> ⚠️ Never commit tokens or credentials directly into the code.

---

### Part 4 — Test and activate

**Step 10 — Run a manual test**

1. Go to your repository → **Actions** tab
2. Select **"📸 Archives de la Planète — Daily Post"**
3. Click **Run workflow** → **Run workflow**
4. Watch the logs — if everything is configured correctly, a post will appear on Instagram within a minute

**Step 11 — Confirm the schedule is active**

The workflow runs automatically every day at ~9am Paris time (8am UTC).  
Note: GitHub Actions scheduled jobs can be delayed by up to 15–30 minutes during peak load.

---

### Part 5 — Maintenance

**Renew your token every 60 days**

Long-lived Meta tokens expire after 60 days. You have two options:

**Option A — Manual renewal**

Run `refresh_token.py` locally each month:

```bash
META_APP_ID=xxx META_APP_SECRET=xxx IG_ACCESS_TOKEN=xxx python refresh_token.py
```

Then update the `IG_ACCESS_TOKEN` secret in your GitHub repository.

**Option B — Automatic renewal**

Add a second GitHub Actions workflow that calls `refresh_token.py` monthly and updates the secret via the GitHub API. This requires a GitHub Personal Access Token (PAT) with `secrets:write` permission stored as an additional repository secret.

---

## Important notes

- **Publishing limit**: Instagram allows up to 25 API-published posts per day
- **Image requirements**: Images must be accessible via a public HTTPS URL (the open data API satisfies this)
- **Caption length**: Instagram caps captions at 2,200 characters — the bot handles this automatically
- **Account type**: You must use a Business or Creator account; personal accounts are not supported by the Graph API
- **Image rights**: The Archives de la Planète collection is published under an open licence by the musée Albert-Kahn — credit the source in your bio or captions

---

## Resources

- [Archives de la Planète API](https://opendata.hauts-de-seine.fr/explore/dataset/archives-de-la-planete/api/)
- [Meta Graph API Explorer](https://developers.facebook.com/tools/explorer/)
- [Instagram Content Publishing API docs](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/content-publishing)
- [GitHub Actions — schedule event](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule)
- [crontab.guru — cron expression helper](https://crontab.guru)
