# YT Money Engine

A daily, hands-off YouTube agent for a faceless finance channel. Every day it:

1. **Finds the topic.** It reads the last 48 hours of Indian and global finance news (Google News), and what is getting views on YouTube right now. That covers this week's top finance videos in India, plus outlier hits from channels like Economics Explained, How Money Works, Warikoo and Labour Law Advisor.
2. **Researches it.** Claude (Opus) searches the web and builds a brief of 10–18 sourced facts, real headlines, reports and the real people involved.
3. **Writes the video.** It picks a different format each day (explainer, "you didn't know", top 10, money mistakes, case study, how X makes money, myth-busting, money moves) at 5, 8, 10 or 12 minutes. The script uses a retention structure: a hook in the first 5 seconds, open loops, a re-hook every 60–90 seconds, and concrete takeaways.
4. **Fact-checks it.** A second Claude pass searches the web again, flags wrong numbers, unproven allegations and promises of returns, and the script is revised.
5. **Records the voice.** ElevenLabs reads it expressively, with exact word timings.
6. **Pulls real footage and photos.** Licensed stock clips (Pixabay/Pexels) and real photos of the people, companies and places in the story (Wikimedia Commons / Wikipedia, free licences only).
7. **Edits the video.** 1080p30, in the Economics Explained style: full-bleed footage under a dark wash, report cards, newspaper-headline cards, photo cards, animated charts, count-up stats, people-icon grids, flow diagrams, timelines, chapter cards, film grain and karaoke captions. Background music is ducked under the voice, with a whoosh on each chapter.
8. **Makes two thumbnails.** The real person's face is cut out with a white outline, with 2–5 huge words and a number badge.
9. **Writes the packaging.** Title, alternative titles, a description with chapters, sources, credits and an AI disclosure, plus tags, a captions file (.srt) and a pinned-comment idea.
10. **Checks its own work (QA).** Duration, audio level, resolution and thumbnail size. A broken video is never uploaded.
11. **Uploads it.** The video goes up as Private, scheduled to go public at your India prime-time slot. It also sets the thumbnail, uploads captions and adds the video to your playlist.
12. **Emails you.** Subject "✅ Scheduled: <title>", with the link, the thumbnail and a contact sheet of frames. If anything fails you get "❌" plus the error.

Because the upload is **scheduled**, your PC only has to be on long enough to build the video (any time before the slot). YouTube publishes it at the viral time even if the PC is off by then. The engine keeps **one day queued ahead**, so a missed day doesn't break the daily streak.

---

## What you need

| Item | Where | Notes |
|---|---|---|
| Anthropic API key | console.anthropic.com | Model set in `config.yaml` (`claude-opus-5-5`). Each run's exact token use is saved in `runs/<date>/llm_usage.json`. |
| ElevenLabs API key | elevenlabs.io → API keys | A 10-minute video is about 8–9k characters, so daily uploads need roughly **250k characters a month**. Check that your plan covers this. |
| Pixabay API key | pixabay.com/api/docs | Free. Already filled in your `.env`. |
| Pexels API key (optional) | pexels.com/api | Free. Adds more footage variety. |
| Google Cloud OAuth client | console.cloud.google.com | Free. Needed to upload to your channel (Step 3). |
| Gmail App Password (optional) | myaccount.google.com/apppasswords | For the daily email. |
| Windows 10/11 PC | | 8+ CPU cores renders a 10-minute video in roughly 15–25 minutes. |

Your channel must be **phone-verified** (youtube.com/verify) to use custom thumbnails.

---

## Setup (Windows, about 20 minutes, once)

**Step 1: Unzip** this folder somewhere permanent, e.g. `C:\YTEngine`.

**Step 2: Get your keys** from the table above.

**Step 3: Connect YouTube (Google Cloud)**
1. Open https://console.cloud.google.com and create a project, e.g. "YT Engine".
2. Go to APIs & Services → Library and **enable "YouTube Data API v3"**.
3. Set up the Google Auth Platform (OAuth consent screen):
   - User type: **External**.
   - App name: anything. Use your email.
   - Under Audience, add your own Google account as a test user. Then click **Publish app** (set it to *In production*). If you leave it in Testing, the login expires every 7 days.
4. Go to Clients → Create client → **Desktop app** → Download JSON.
5. Save the file as **`client_secret.json`** in the engine folder.

**Step 4: Run the installer.** Right-click `setup_windows.ps1` → *Run with PowerShell*. It:
- installs Python 3.12 and ffmpeg;
- installs the packages;
- opens Notepad so you can paste your keys into `.env`;
- opens your browser to log in to YouTube. Pick the channel's account. Google will show "unverified app"; click Advanced → Continue, since it's your own app;
- runs a health check;
- registers the daily Windows task, which runs at the time you choose plus a catch-up run at log-on.

**Step 5: Test once without uploading.**
```
.\.venv\Scripts\python.exe run_daily.py --no-upload
```
Watch `runs\<date>\final.mp4`, then look at `thumbnail_A.jpg`, `metadata.json` and `research_brief.json`. When you're happy, the scheduled task takes over.

Tip: in Windows Power Options, enable **"Allow wake timers"** so the task can wake a sleeping PC.

---

## Daily routine (2 minutes, optional but recommended)

When the ✅ email arrives:
- Open the Studio link and skim the video.
- Paste the pinned comment from `pinned_comment.txt`.
- Optionally set up **Test & Compare** with `thumbnail_B.jpg`. YouTube's API can't start thumbnail A/B tests, so that one step stays manual.
- To stop a video, set it back to Private (or delete it) before its publish time.

---

## Commands

```
run_daily.py                    build + upload the next slot (what the task runs)
run_daily.py --no-upload        build only → runs\<date>\final.mp4
run_daily.py --preview          research + script + voice, then a few still frames per chapter (fast check)
run_daily.py --format top_list --minutes 12
run_daily.py --slot "2026-11-02 18:30"
run_daily.py --storyboard samples\demo_storyboard.json --no-upload     render a hand-written script
run_daily.py --check            keys, ffmpeg, YouTube connection, next slot
run_daily.py --auth             reconnect YouTube
```

## Customise (`config.yaml`)
- `schedule.publish_times`: the slot for each weekday, IST. Defaults are 6:30 PM on weekdays and 11:30 AM at weekends, just before India's evening peak.
- `content.formats`: format mix, weights and lengths.
- `channel.persona`, `channel.audience` (`india` / `global` / `mix`).
- `voice.elevenlabs`:
  - `voice_id`: any voice from your ElevenLabs Voice Library.
  - `stability`: lower means more emotion.
  - `style`: more delivery.
- `research.benchmark_channels`: the channels to learn from.
- `render.workers`, `render.burn_captions`.
- `music/`: drop royalty-free tracks here, e.g. from the YouTube Audio Library. They're picked automatically.
- `engine/prompts.py`: the full editorial playbook (hooks, structure, honesty rules, visual rules). Edit it to change the voice of the channel.

## Files per run (`runs/<date>_<time>/`)
- `research_brief.json`: facts with sources.
- `storyboard.json`: script plus visuals.
- `voice/`
- `sec*.mp4`
- `final.mp4`
- `thumbnail_A.jpg` / `thumbnail_B.jpg`
- `captions.srt`
- `metadata.json`
- `qa.json`
- `contact_sheet.jpg`
- `run.log`

Every stage is cached, so re-running after a crash resumes where it stopped.

---

## Important: monetisation, AI and copyright (read this)

- **AI disclosure is on, and should stay on.** YouTube requires creators to disclose realistic synthetic content such as an AI voice. The engine sets the API's `containsSyntheticMedia` flag and adds one line to the description. Hiding it risks penalties. It does **not** cost you reach or monetisation.
- **What actually gets AI channels demonetised** is YouTube's "inauthentic content" policy (July 2025): mass-produced, repetitive, low-value videos. This engine is built against that:
  - a new researched topic every day, rotating formats and lengths;
  - real sourced facts and a fact-check pass;
  - real footage and photos;
  - a consistent persona.

  Your 2-minute daily review also helps.
- **Footage and photos come only from licensed sources:** Pixabay, Pexels, and Wikimedia Commons under PD/CC0/CC BY/CC BY-SA. Credits are written into every description. It does **not** scrape Google Images, news photos or YouTube clips, because those trigger Content ID claims and copyright strikes that can kill a channel.
- **Real faces on thumbnails:** only people who are actually in that day's story, from freely licensed photos. They are never shown as endorsing the channel.
- **Headlines and report cards:** the writer is told to use only real, verified headlines and real report titles. Each card is labelled "Stylised for illustration".

## Troubleshooting
- **❌ email "QA failed".** Open `runs\<date>\run.log`. Re-run `run_daily.py` and it resumes from where it stopped.
- **"YouTube not authorised".** Run `run_daily.py --auth`. If this happens weekly, publish your OAuth app (Step 3.3).
- **Thumbnail didn't upload.** Phone-verify the channel.
- **ElevenLabs quota exceeded.** Upgrade the plan, or set `voice.fallback: kokoro` to use a free local voice. It's lower quality: run `pip install kokoro-onnx` and put the model files in `data\kokoro\`.
- **Slow renders.** Set `render.workers` to your core count, and close other heavy apps during the build window.
