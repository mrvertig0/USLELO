# USL2 Elo

An unofficial, auto-updating Elo power ranking for every club in USL League Two.

**Live site:** enable GitHub Pages (see setup below) and it'll be at
`https://<your-username>.github.io/<repo-name>/`

## How it works

```
scripts/leagues.py       -> config: one entry per league (Sofascore
                             tournament_id + a name filter). Add a new
                             league here -- both scripts below loop over
                             it automatically.
scripts/fetch_data.py    -> pulls match results from Sofascore's public API
                             (via the `datafc` package) for every league in
                             leagues.py -> data/matches_<key>.csv
scripts/compute_elo.py   -> replays every finished match chronologically,
                             computes Elo per club, per league ->
                             docs/data/ratings_<key>.json
                             docs/data/history_<key>.json
                             docs/data/ratings_<key>_season.json
                             docs/data/history_<key>_season.json
scripts/run_update.ps1  -> runs the two scripts above, then commits + pushes
                            if anything changed. Run this from YOUR computer
                            (see "Automating the daily update" below) --
                            Sofascore blocks GitHub's cloud IPs, so the fetch
                            can't run inside GitHub Actions itself.
docs/                    -> static site (plain HTML/CSS/JS) that reads
                            those two JSON files and renders the table
.github/workflows/       -> republishes docs/ to GitHub Pages every time
update.yml                  main changes (including when run_update.ps1
                             pushes new data)
```

No server, no database, no API keys. Everything lives in the repo.

### Data source

USL League Two doesn't publish a public API. `uslleaguetwo.com` itself
blocks scripted requests, and text-scraping mirror sites is fragile
because club names containing numbers (e.g. "Loudoun United FC 2")
collide with score digits once you flatten a page to text. Sofascore
runs USL2 through the same structured match-events API it uses for
every other league it covers, and the [`datafc`](https://pypi.org/project/datafc/)
package wraps that cleanly, so `fetch_data.py` uses it instead.

This is an unofficial API and could change or rate-limit without
notice — if `fetch_data.py` starts failing, that's the first place to
look (check for a new `datafc` release before rewriting anything by
hand).

**Important:** Sofascore sits behind Cloudflare, which blocks GitHub
Actions' IP ranges outright — this isn't fixable with better headers,
it's an IP-reputation block. That's why the fetch step has to run from
a normal residential connection (your computer) rather than inside
GitHub's cloud. See "Automating the daily update" below.

### The Elo formula

Standard "World Football Elo" method (same one used by eloratings.net),
not plain chess Elo — soccer needs it because chess Elo has no concept
of a draw scaling or goal margin:

- All clubs start at **1500**.
- Home side gets a **+60** rating bump before the expected-result
  calculation (`HOME_ADVANTAGE` in `compute_elo.py`).
- Rating swings scale with margin of victory: a 3–0 moves the needle
  more than a 1–0, capped by a goal-difference multiplier.
- **K-factor 26** — this controls how fast ratings move. Lower =
  smoother/slower, higher = more reactive to recent form. eloratings.net
  uses 20 for friendlies up to 60 for World Cup finals; 26 is a
  reasonable middle ground for a semi-pro league with rosters that
  shift week to week.

All three constants live at the top of `scripts/compute_elo.py` if you
want to tune them.

## Setup

1. **Create a GitHub repo** and push this folder to it.
2. **Enable Pages**: repo Settings → Pages → Source: **GitHub Actions**.
3. **Do the first data pull from your own computer** (see "Running
   locally" below) and push it. That first push will trigger the
   "Publish USL2 Elo site" workflow automatically and put the site live.

## Running locally

```bash
pip3 install -r requirements.txt
python3 scripts/fetch_data.py      # writes data/matches_<key>.csv for every league
python3 scripts/compute_elo.py     # writes docs/data/ratings_<key>.json + history files
python3 -m http.server 8000 --directory docs   # open http://localhost:8000
```

Add `--league usl2` (or `--league wleague`) to `fetch_data.py` to pull just
one league while testing -- `compute_elo.py` always processes whatever
`data/matches_*.csv` files it finds.

To add another league entirely, add one entry to `scripts/leagues.py`
(Sofascore tournament_id + a name-matching function) and add a matching
tab in `docs/index.html`'s `#league-tabs` + `LEAGUES` object in
`docs/app.js` -- everything else picks it up automatically.

**If `pip3 install` fails with an "externally-managed-environment"
error** (common on newer Macs with Homebrew Python): either add
`--break-system-packages` to the pip3 command, or set up a virtual
environment first:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
If you use a venv, `run_update.sh` will need `source venv/bin/activate`
added near the top so the scheduled job can find the installed packages too.

Once you're happy with the result:

```bash
git add data docs/data
git commit -m "Update ratings"
git push
```

That push republishes the live site automatically.

## Automating the daily update

Since the fetch has to run from your computer, "automatic" here means
"scheduled on your Mac" rather than "in the cloud." These instructions
use `cron`, which is built into macOS.

1. **Confirm `run_update.sh` works manually first.** Open Terminal,
   `cd` into the repo folder, and run:
   ```bash
   chmod +x scripts/run_update.sh   # only needed once
   ./scripts/run_update.sh
   ```
   It should pull, fetch, compute, and push, printing progress as it
   goes. Fix any errors here before scheduling it — a broken scheduled
   job fails silently and you won't notice until the site goes stale.

2. **Find the full paths you'll need**, since cron doesn't understand
   `~` or relative paths the way Terminal does:
   ```bash
   pwd                    # full path to the repo, e.g. /Users/zac/usl2-elo
   which python3          # full path to python3, e.g. /usr/bin/python3
   which git               # full path to git, e.g. /usr/bin/git
   ```
   Note all three down.

3. **Open your crontab for editing**:
   ```bash
   crontab -e
   ```
   This opens a text editor in Terminal (likely `vi` — if you've never
   used it: press `i` to start typing, `Esc` when done, then type `:wq`
   and press Enter to save and quit).

4. **Add this line**, substituting your actual repo path from step 2.
   This runs the update every day at 8:00 AM:
   ```
   0 8 * * * cd /Users/zac/usl2-elo && /bin/bash scripts/run_update.sh >> /tmp/usl2-elo-update.log 2>&1
   ```
   The `>> /tmp/usl2-elo-update.log 2>&1` part saves the output to a log
   file, since cron jobs run silently in the background — that log is
   how you'll check whether a run succeeded.

5. **Grant Terminal (or cron) permission if macOS asks.** Recent macOS
   versions sometimes prompt for "Full Disk Access" the first time a
   background job touches files — if the scheduled run fails but the
   manual one works, check System Settings → Privacy & Security → Full
   Disk Access and make sure Terminal is allowed.

6. **Test it without waiting until 8 AM**: temporarily add a line for a
   couple minutes from now (e.g. if it's 3:14 PM, use `16 15 * * *`),
   wait, then check:
   ```bash
   cat /tmp/usl2-elo-update.log
   ```
   Once confirmed working, edit the crontab again (`crontab -e`) and
   remove the test line, leaving just the real 8 AM one.

If your Mac is asleep or off at the scheduled time, that day's update
just gets skipped — the site stays at its last-fetched ratings until
the next successful run. (If your Mac is usually asleep at 8 AM, pick a
time you know it'll be awake — cron doesn't wake a sleeping Mac.)

## Known limitations / next steps

- **No conference/division filter yet.** The site currently ranks all
  158 clubs in one flat table. Sofascore's standings endpoint does
  expose division groupings; adding a filter is a matter of pulling
  `standings_data()` once per division and joining it onto the ratings
  by `team_id`.
- **Round-probing.** `fetch_data.py` walks matchweek numbers 1–30 and
  stops after a few consecutive misses, since USL2's schedule length
  varies slightly by division and Sofascore's "round" numbering isn't
  published anywhere. This is a reasonable way to catch the full
  season without hardcoding a week count, but if a division ever plays
  more than 30 matchweeks (unlikely) or has a big schedule gap early on
  that looks like the end of season, adjust `MAX_ROUND_PROBE` /
  `CONSECUTIVE_MISS_STOP` at the top of the script.
- **First season has no prior-year seed.** Every club starts at 1500
  regardless of previous-season strength, so early-season ratings are
  noisier than they'll be by mid-season. Carrying over end-of-season
  ratings (decayed toward 1500) as next year's starting point is a
  natural follow-up once there's a full season of history.
