"""
Fetch USL League Two match results from Sofascore's public API (via the
`datafc` package) and save them to data/matches.csv.

Sofascore has no official public docs for this, but the endpoints are
widely used and documented in open-source projects (e.g. LanusStats,
sofascore-api). `datafc` wraps them cleanly and returns a tidy DataFrame
per match, which avoids the ambiguity you get scraping rendered text
(team names like "Loudoun United FC 2" collide with score digits when
you regex flattened text -- structured JSON avoids that entirely).

Strategy: USL2 has no unified matchday numbering (each of its ~20
divisions runs its own schedule), so Sofascore's round-based endpoint
doesn't return the full season -- round 1 comes back as a single
oddly-sized bucket and every other round number 404s. Instead, we:
  1. Do one round-1 pull just to discover every team_id in the league.
  2. Fetch each team's COMPLETE match history (a separate, properly
     paginated endpoint), filtered down to USL League Two games.
  3. Dedupe by game_id (every match appears in two teams' histories).

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
from datafc import match_data, seasons_data, team_match_history_data
from datafc.exceptions import DataNotAvailableError, APIError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetch_data")

# Sofascore's unique-tournament id for USL League Two. Confirmed via
# https://www.sofascore.com/football/tournament/usa/usl-league-two/13546
TOURNAMENT_ID = 13546

# The tournament name Sofascore actually returns is "USL, League Two"
# (yes, with a comma) -- confirmed by inspecting real team history data.
# Rather than hardcode that one exact string and risk missing another
# punctuation/spacing variant, we normalize away punctuation before
# matching. We keep anything that's USL + "league two" in some form,
# and explicitly exclude the league's old PDL branding (Premier
# Development League) even though it's the same competition lineage,
# since PDL-era results predate the modern USL2 format.
import re


def _normalize_tournament_name(name) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def _is_usl2(name) -> bool:
    norm = _normalize_tournament_name(name)
    if "premier development" in norm or re.search(r"\bpdl\b", norm):
        return False
    return "usl" in norm and "league two" in norm

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


def discover_team_ids(tournament_id: int, season_id: int, data_source: str) -> set[int]:
    """One bulk pull, just to get every team_id in the league -- not used
    as the actual match source, since it's known to be incomplete."""
    df = match_data(tournament_id, season_id, week_number=1, data_source=data_source)
    ids = set(df["home_team_id"].dropna().astype(int)) | set(df["away_team_id"].dropna().astype(int))
    log.info("discovered %d teams from round-1 bulk pull", len(ids))
    return ids


def fetch_full_history_for_teams(team_ids: set[int], data_source: str) -> pd.DataFrame:
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

        usl2_df = df[df["tournament"].apply(_is_usl2)]
        frames.append(usl2_df)
        log.info("team %3d/%d (id=%s): %d USL2 matches in history", i, len(team_ids), team_id, len(usl2_df))

    if not frames:
        raise RuntimeError("No match data fetched at all -- check tournament/season id or team discovery.")

    all_matches = pd.concat(frames, ignore_index=True)
    all_matches = all_matches.drop_duplicates(subset=["game_id"]).reset_index(drop=True)
    return all_matches


def main():
    log.info("Checking which Sofascore endpoint is reachable from this machine...")
    data_source = pick_working_data_source(TOURNAMENT_ID)

    log.info("Looking up current USL League Two season...")
    season_id, season_name = get_current_season_id(TOURNAMENT_ID, data_source)
    log.info("Using season_id=%s (%s)", season_id, season_name)

    team_ids = discover_team_ids(TOURNAMENT_ID, season_id, data_source)

    log.info("Fetching complete match history for each of %d teams (this takes a few minutes)...", len(team_ids))
    df = fetch_full_history_for_teams(team_ids, data_source)
    log.info("Fetched %d total USL2 matches (all statuses) after dedup", len(df))

    out_csv = DATA_DIR / "matches.csv"
    df.to_csv(out_csv, index=False)
    log.info("Wrote %s", out_csv)

    meta = {
        "tournament_id": TOURNAMENT_ID,
        "season_id": season_id,
        "season_name": season_name,
        "data_source": data_source,
        "team_count": len(team_ids),
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
