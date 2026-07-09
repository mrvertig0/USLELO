"""
Fetch match results for every league defined in leagues.py from
Sofascore's public API (via the `datafc` package).

Sofascore has no official public docs for this, but the endpoints are
widely used and documented in open-source projects (e.g. LanusStats,
sofascore-api). `datafc` wraps them cleanly and returns a tidy DataFrame
per match, which avoids the ambiguity you get scraping rendered text
(team names like "Loudoun United FC 2" collide with score digits when
you regex flattened text -- structured JSON avoids that entirely).

Strategy per league: these leagues have no unified matchday numbering
(each division runs its own schedule), so Sofascore's round-based
endpoint doesn't return the full season -- round 1 comes back as a
single oddly-sized bucket and every other round number 404s. Instead:
  1. Do one round-1 pull just to discover every team_id in the league.
  2. Fetch each team's COMPLETE match history (a separate, properly
     paginated endpoint), filtered down to that league's games.
  3. Dedupe by game_id (every match appears in two teams' histories).

Usage:
    python scripts/fetch_data.py                # all leagues
    python scripts/fetch_data.py --league usl2   # just one (for testing)

Writes, per league key:
    data/matches_<key>.csv   -- one row per match (finished + scheduled)
    data/meta_<key>.json      -- tournament/season id + last-fetch timestamp
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd
from datafc import match_data, seasons_data, team_match_history_data
from datafc.exceptions import DataNotAvailableError, APIError

from leagues import LEAGUES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetch_data")

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
        raise RuntimeError(f"No seasons returned for tournament_id={tournament_id}.")

    import datetime
    this_year = str(datetime.datetime.now().year)
    matches_year = seasons_df[
        seasons_df["season_year"].astype(str).str.contains(this_year, na=False)
        | seasons_df["season_name"].astype(str).str.contains(this_year, na=False)
    ]
    row = matches_year.iloc[0] if not matches_year.empty else seasons_df.iloc[0]
    return int(row["season_id"]), str(row["season_name"])


def discover_team_ids(tournament_id: int, season_id: int, data_source: str) -> set[int]:
    """One bulk pull, just to get every team_id in the league -- not used
    as the actual match source, since it's known to be incomplete."""
    df = match_data(tournament_id, season_id, week_number=1, data_source=data_source)
    ids = set(df["home_team_id"].dropna().astype(int)) | set(df["away_team_id"].dropna().astype(int))
    log.info("discovered %d teams from round-1 bulk pull", len(ids))
    return ids


def fetch_full_history_for_teams(team_ids: set[int], data_source: str, name_filter) -> pd.DataFrame:
    frames = []
    for i, team_id in enumerate(sorted(team_ids), start=1):
        try:
            df = team_match_history_data(team_id, data_source=data_source)
        except DataNotAvailableError:
            log.warning("team_id=%s: no history data", team_id)
            continue
        except APIError as e:
            log.warning("team_id=%s: API error, retrying once (%s)", team_id, e)
            time.sleep(3)
            try:
                df = team_match_history_data(team_id, data_source=data_source)
            except Exception as e2:
                log.warning("team_id=%s: still failing, skipping (%s)", team_id, e2)
                continue

        league_df = df[df["tournament"].apply(name_filter)]
        frames.append(league_df)
        log.info("team %3d/%d (id=%s): %d matches in history", i, len(team_ids), team_id, len(league_df))

    if not frames:
        raise RuntimeError("No match data fetched at all -- check tournament/season id or team discovery.")

    all_matches = pd.concat(frames, ignore_index=True)
    all_matches = all_matches.drop_duplicates(subset=["game_id"]).reset_index(drop=True)

    discovered_ids = set(all_matches["home_team_id"].dropna().astype(int)) | set(all_matches["away_team_id"].dropna().astype(int))
    extra = len(discovered_ids) - len(team_ids)
    if extra > 0:
        log.info(
            "note: %d additional clubs appear in history beyond the %d seed teams -- "
            "these are past-season opponents (promoted/relegated/rebranded clubs) pulled "
            "in via all-time match history. This is expected, not a data gap.",
            extra, len(team_ids),
        )

    return all_matches


def fetch_league(key: str, cfg: dict):
    log.info("=== %s (%s) ===", cfg["label"], key)
    tournament_id = cfg["tournament_id"]

    log.info("Checking which Sofascore endpoint is reachable from this machine...")
    data_source = pick_working_data_source(tournament_id)

    log.info("Looking up current season...")
    season_id, season_name = get_current_season_id(tournament_id, data_source)
    log.info("Using season_id=%s (%s)", season_id, season_name)

    team_ids = discover_team_ids(tournament_id, season_id, data_source)

    log.info("Fetching complete match history for each of %d teams (this takes a few minutes)...", len(team_ids))
    df = fetch_full_history_for_teams(team_ids, data_source, cfg["name_filter"])
    log.info("Fetched %d total matches (all statuses) after dedup", len(df))

    out_csv = DATA_DIR / f"matches_{key}.csv"
    df.to_csv(out_csv, index=False)
    log.info("Wrote %s", out_csv)

    meta = {
        "league": key,
        "label": cfg["label"],
        "tournament_id": tournament_id,
        "season_id": season_id,
        "season_name": season_name,
        "data_source": data_source,
        "team_count": len(team_ids),
        "fetched_at_utc": pd.Timestamp.now('UTC').isoformat(),
        "match_count": len(df),
    }
    meta_path = DATA_DIR / f"meta_{key}.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    log.info("Wrote %s", meta_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", choices=list(LEAGUES.keys()), default=None,
                         help="Fetch just one league (default: all leagues in leagues.py)")
    args = parser.parse_args()

    keys = [args.league] if args.league else list(LEAGUES.keys())
    for key in keys:
        fetch_league(key, LEAGUES[key])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("fetch_data.py failed")
        sys.exit(1)
