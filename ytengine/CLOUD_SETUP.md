# Run it in the cloud (works while your laptop is OFF)

The engine runs on **GitHub Actions**: GitHub's free servers start it at 10:00 AM IST every day. It researches, renders, and uploads the video to your channel, scheduled for 6:30 PM IST (11:30 AM on weekends). Your laptop is needed **once**, for about 10 minutes, to log in to YouTube.

---

## Step 1: Create the GitHub repo (5 min)
1. Sign up or log in at https://github.com.
2. Click **+ → New repository**. Name it `yt-engine` and choose **Public**.
   - **Why Public:** Actions minutes are unlimited and free on public repos. Private repos get ~2,000 free minutes a month, which daily 10-minute renders use up.
   - **Your keys stay secret either way:** they go into GitHub *Secrets*, which nobody can see. The code itself is public.
3. On the new repo page, click **uploading an existing file**.
4. Drag in **everything inside** the `ytengine` folder you unzipped.
5. Click **Commit changes**.
6. Check that the folder **`.github/workflows`** appears in the repo. Windows sometimes skips folders that start with a dot.
   - If it's missing: click **Add file → Create new file** and name it `.github/workflows/daily.yml`.
   - Paste the contents of `ytengine\.github\workflows\daily.yml` (open it in Notepad), then click **Commit**.

## Step 2: Google Cloud (YouTube permission, 10 min, free)
1. Go to https://console.cloud.google.com and create a project called `YT Engine`.
2. Go to **APIs & Services → Library**, search **YouTube Data API v3**, and click **Enable**.
3. Go to **Google Auth Platform (OAuth consent screen)**:
   - Set up External, using your email.
   - Under **Audience**, add your Gmail as a test user. Then click **Publish app** (set it to "In production"). If you skip this, your login expires every 7 days.
4. Go to **Clients → Create client → Desktop app → Create → Download JSON**.
5. Rename the file to **`client_secret.json`** and put it in your unzipped `ytengine` folder on your PC. Do **not** upload it to GitHub.

## Step 3: Log in to YouTube once (on your PC)
1. Double-click **`connect_youtube.bat`** in the `ytengine` folder.
   - If it installs Python first, double-click it again afterwards.
2. Your browser opens. Choose the Google account and the **channel**.
   - "Google hasn't verified this app" → **Advanced → Go to YT Engine** (it's your own app) → **Allow**.
3. When it says **SUCCESS**, the token is copied to your clipboard (and saved as `youtube_token.json`).

## Step 4: Add your secrets on GitHub (5 min)
Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**, and add each of these:

| Name | Value |
|---|---|
| `YT_TOKEN_JSON` | Paste from your clipboard (the whole text of `youtube_token.json`) |
| `CLAUDE_CODE_OAUTH_TOKEN` **or** `ANTHROPIC_API_KEY` | **Use your Claude Pro/Max plan:** double-click `get_claude_token.bat`, log in, copy the `sk-ant-oat...` token. **Or** pay-as-you-go API: a key from console.anthropic.com. Add only one. |
| `ELEVENLABS_API_KEY` | From elevenlabs.io → API keys |
| `PIXABAY_API_KEY` | Your Pixabay key (pixabay.com/api/docs, shown when logged in) |
| `PEXELS_API_KEY` | Optional, free at pexels.com/api |
| `SMTP_USER` | Optional: your Gmail address (for the daily "✅ Scheduled" email) |
| `SMTP_PASS` | Optional: a Gmail **App Password** (myaccount.google.com/apppasswords) |
| `NOTIFY_EMAIL_TO` | Optional: where the email goes |

## Step 5: Test run (no upload)
1. In the repo, go to **Actions**. If asked, click "I understand my workflows, enable them".
2. Click **Daily video → Run workflow**.
3. Tick **"Build only, do not upload"** → **Run workflow**.
4. Wait about 30–60 minutes. Open the run, scroll to **Artifacts**, and download **video-1**. It contains the video, thumbnails, title and description, and the research.
5. Happy with it? You're done: it runs by itself every day at 10:00 AM IST and uploads. Each day you get an email, and you can watch the run under **Actions**.

---

## Everyday use
- **Nothing to do.** Check the email or YouTube Studio. Optionally pin the comment from the email, and add thumbnail B in Test & Compare.
- **Make one now:** Actions → Daily video → Run workflow. You can choose a format and length.
- **Stop a video:** set it to Private in Studio before its publish time.
- **Pause the agent:** Actions → Daily video → **⋯ → Disable workflow**.
- **Change times or formats:** edit `config.yaml` in the repo (pencil icon).
  - The build time is the `cron` line in `.github/workflows/daily.yml`, which uses UTC. `30 4 * * *` means 10:00 IST.
- **If a run fails:** GitHub emails you. Open the run → read the log → fix → **Re-run jobs**.
