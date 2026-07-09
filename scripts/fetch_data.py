"""
Fetch USL League Two match results from Sofascore's public API (via the
`datafc` package) and save them to data/matches.csv.

Sofascore has no official public docs for this, but the endpoints are
widely used and documented in open-source projects (e.g. LanusStats,
sofascore-api). `datafc` wraps them cleanly and returns a tidy DataFrame
per match, which avoids the ambiguity you get scraping rendered text
(team names like "Loudoun United FC 2" collide with score digits when
you regex flattened text -- structured JSON avoids that entirely).

Usage:
    python scripts/fetch_data.py

Writes:
    data/matches.csv   -- one row per match (finished + scheduled)
    data/meta.json      -- tournament/season id + last-fetch timestamp
"""
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd
from datafc import match_data, seasons_data
from datafc.exceptions import DataNotAvailableError, APIError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetch_data")

# Sofascore's unique-tournament id for USL League Two. Confirmed via
# https://www.sofascore.com/football/tournament/usa/usl-league-two/13546
TOURNAMENT_ID = 13546

# USL2's regular season runs ~14 matchweeks (varies slightly by division)
# plus playoff rounds. We probe a generous range and stop early once we
# hit several consecutive empty/missing rounds, so this doesn't need to
# be updated by hand each season.
MAX_ROUND_PROBE = 30
CONSECUTIVE_MISS_STOP = 4

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# Sofascore's main API domain sometimes 403s requests from cloud/CI IP
# ranges (GitHub Actions runners, etc.) even though the same request works
# fine from a home connection -- it's an IP/ASN-level block, not a header
# or fingerprint issue (datafc already spoofs a real browser TLS
# fingerprint). `datafc` ships a mirror domain for exactly this case;
# we try the primary source first and fall back automatically.
DATA_SOURCE_CANDIDATES = ["sofascore", "sofavpn"]


def pick_working_data_source(tournament_id: int) -> str:
    last_err = None
    for source in DATA_SOURCE_CANDIDATES:
        try:
            seasons_data(tournament_id, data_source=source)
            log.info("using data_source=%r", source)
            return source
        except Exception as e:
            log.warning("data_source=%r failed (%s), trying next", source, e)
            last_err = e
    raise RuntimeError(f"All data sources failed. Last error: {last_err}")


def get_current_season_id(tournament_id: int, data_source: str) -> tuple[int, str]:
    """Sofascore returns seasons most-recent-first; take the first row,
    but prefer one whose name/year contains the current year if present."""
    seasons_df = seasons_data(tournament_id, data_source=data_source)
    if seasons_df.empty:
        raise RuntimeError("No seasons returned for USL League Two tournament id.")

    import datetime
    this_year = str(datetime.datetime.now().year)
    matches_year = seasons_df[
        seasons_df["season_year"].astype(str).str.contains(this_year, na=False)
        | seasons_df["season_name"].astype(str).str.contains(this_year, na=False)
    ]
    row = matches_year.iloc[0] if not matches_year.empty else seasons_df.iloc[0]
    return int(row["season_id"]), str(row["season_name"])


def fetch_all_rounds(tournament_id: int, season_id: int, data_source: str) -> pd.DataFrame:
    frames = []
    consecutive_misses = 0
    for week in range(1, MAX_ROUND_PROBE + 1):
        try:
            df = match_data(tournament_id, season_id, week_number=week, data_source=data_source)
            frames.append(df)
            consecutive_misses = 0
            log.info("round %2d: %d matches", week, len(df))
        except DataNotAvailableError:
            consecutive_misses += 1
            log.info("round %2d: no data (miss %d/%d)", week, consecutive_misses, CONSECUTIVE_MISS_STOP)
            if consecutive_misses >= CONSECUTIVE_MISS_STOP:
                log.info("stopping round probe after %d consecutive misses", CONSECUTIVE_MISS_STOP)
                break
        except APIError as e:
            log.warning("round %2d: API error, retrying once (%s)", week, e)
            time.sleep(3)
            try:
                df = match_data(tournament_id, season_id, week_number=week, data_source=data_source)
                frames.append(df)
                consecutive_misses = 0
            except Exception as e2:
                log.warning("round %2d: still failing, skipping (%s)", week, e2)
                consecutive_misses += 1
        time.sleep(0.5)  # be polite

    if not frames:
        raise RuntimeError("No match data fetched at all -- check tournament/season id.")

    all_matches = pd.concat(frames, ignore_index=True)
    all_matches = all_matches.drop_duplicates(subset=["game_id"]).reset_index(drop=True)
    return all_matches


def main():
    log.info("Checking which Sofascore endpoint is reachable from this machine...")
    data_source = pick_working_data_source(TOURNAMENT_ID)

    log.info("Looking up current USL League Two season...")
    season_id, season_name = get_current_season_id(TOURNAMENT_ID, data_source)
    log.info("Using season_id=%s (%s)", season_id, season_name)

    df = fetch_all_rounds(TOURNAMENT_ID, season_id, data_source)
    log.info("Fetched %d total matches (all statuses)", len(df))

    out_csv = DATA_DIR / "matches.csv"
    df.to_csv(out_csv, index=False)
    log.info("Wrote %s", out_csv)

    meta = {
        "tournament_id": TOURNAMENT_ID,
        "season_id": season_id,
        "season_name": season_name,
        "data_source": data_source,
        "fetched_at_utc": pd.Timestamp.now('UTC').isoformat(),
        "match_count": len(df),
    }
    (DATA_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    log.info("Wrote %s", DATA_DIR / "meta.json")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("fetch_data.py failed")
        sys.exit(1)
