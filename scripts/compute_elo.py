"""
Compute Elo ratings for every league defined in leagues.py from
data/matches_<key>.csv.

Uses the "World Football Elo Ratings" formula (the same approach as
eloratings.net), which is the standard, well-documented way to Elo-rate
soccer specifically (plain chess-Elo ignores goal margin and draws
differently than soccer needs):

    dr = (rating_home + HOME_ADV) - rating_away
    We = 1 / (10^(-dr/400) + 1)                  # expected result for home team
    G  = goal-difference multiplier:
           1                    if draw or 1-goal win
           1.5                  if 2-goal win
           (11 + N) / 8         if win by 3+ goals (N = goal diff)
    change = K * G * (W - We)                    # W: 1 win / 0.5 draw / 0 loss
    new_rating_home = rating_home + change
    new_rating_away = rating_away - change

All teams start at 1500. Matches are processed in chronological order.
Only matches with status "Ended" are counted.

Produces two independent rating sets per league from the same match data:
  - "all-time": every match ever played, one continuous running rating.
  - "season": ratings reset to 1500 and recomputed using only matches
    from the most recent season present in that league's data.

Writes, per league key:
    docs/data/ratings_<key>.json          -- all-time ranking table
    docs/data/history_<key>.json          -- all-time rating trajectory
    docs/data/ratings_<key>_season.json   -- current-season-only ranking table
    docs/data/history_<key>_season.json   -- current-season-only trajectory
"""
import json
from pathlib import Path

import pandas as pd

from leagues import LEAGUES

# --- tunables -----------------------------------------------------------
STARTING_RATING = 1500.0
HOME_ADVANTAGE = 60.0     # rating points added to home side before Elo calc
K_FACTOR = 26.0           # domestic-league-appropriate; eloratings.net uses
                           # 20 (friendly) to 60 (World Cup); this sits in
                           # between since these leagues are competitive but
                           # squads/rosters can be fluid week to week.
RECENT_FORM_WINDOW = 5    # "recent movers" = rating change over each club's
                           # last N matches (or fewer, if they haven't played N yet)
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "docs" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def goal_diff_multiplier(goal_diff: int) -> float:
    n = abs(goal_diff)
    if n <= 1:
        return 1.0
    if n == 2:
        return 1.5
    return (11 + n) / 8.0


def run_elo_pass(matches: pd.DataFrame) -> tuple[list[dict], dict[str, list]]:
    """Replays `matches` (already filtered + chronologically sorted) and
    returns (ranking_rows, history_by_team_id)."""
    ratings: dict[int, float] = {}
    names: dict[int, str] = {}
    record: dict[int, dict] = {}   # team_id -> {wins, draws, losses, gp}
    history: dict[int, list] = {}  # team_id -> [{"t": timestamp, "rating": r}, ...]

    def ensure_team(team_id: int, name: str):
        if team_id not in ratings:
            ratings[team_id] = STARTING_RATING
            names[team_id] = name
            record[team_id] = {"wins": 0, "draws": 0, "losses": 0, "gp": 0}
            history[team_id] = [{"t": None, "rating": STARTING_RATING}]

    for _, row in matches.iterrows():
        hid, aid = int(row["home_team_id"]), int(row["away_team_id"])
        ensure_team(hid, row["home_team"])
        ensure_team(aid, row["away_team"])

        hs, as_ = int(row["home_score_current"]), int(row["away_score_current"])
        ts = row["start_timestamp"]

        if hs > as_:
            w_home = 1.0
        elif hs < as_:
            w_home = 0.0
        else:
            w_home = 0.5

        rh, ra = ratings[hid], ratings[aid]
        dr = (rh + HOME_ADVANTAGE) - ra
        we_home = 1.0 / (10 ** (-dr / 400.0) + 1.0)
        g = goal_diff_multiplier(hs - as_)
        change = K_FACTOR * g * (w_home - we_home)

        ratings[hid] = rh + change
        ratings[aid] = ra - change

        for tid, r in ((hid, ratings[hid]), (aid, ratings[aid])):
            history[tid].append({"t": None if pd.isna(ts) else int(ts), "rating": round(r, 1)})

        record[hid]["gp"] += 1
        record[aid]["gp"] += 1
        if w_home == 1.0:
            record[hid]["wins"] += 1
            record[aid]["losses"] += 1
        elif w_home == 0.0:
            record[hid]["losses"] += 1
            record[aid]["wins"] += 1
        else:
            record[hid]["draws"] += 1
            record[aid]["draws"] += 1

    rows = []
    for tid, rating in ratings.items():
        rec = record[tid]
        hist = history[tid]
        n = min(RECENT_FORM_WINDOW, rec["gp"])
        delta_recent = round(hist[-1]["rating"] - hist[-1 - n]["rating"], 1) if n > 0 else 0.0
        rows.append({
            "team_id": tid,
            "team": names[tid],
            "rating": round(rating, 1),
            "games_played": rec["gp"],
            "wins": rec["wins"],
            "draws": rec["draws"],
            "losses": rec["losses"],
            "delta_recent": delta_recent,
            "delta_recent_games": n,
        })

    rows.sort(key=lambda r: r["rating"], reverse=True)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i

    history_out = {str(tid): hist for tid, hist in history.items()}
    return rows, history_out


def write_output(rows, history_out, fetched_at, matches_used, path_prefix, extra_meta=None):
    ratings_out = {
        "generated_at_utc": pd.Timestamp.now('UTC').isoformat(),
        "data_fetched_at_utc": fetched_at,
        "matches_used": matches_used,
        "k_factor": K_FACTOR,
        "home_advantage": HOME_ADVANTAGE,
        "starting_rating": STARTING_RATING,
        "recent_form_window": RECENT_FORM_WINDOW,
        "teams": rows,
    }
    if extra_meta:
        ratings_out.update(extra_meta)

    ratings_path = OUT_DIR / f"ratings_{path_prefix}.json"
    ratings_path.write_text(json.dumps(ratings_out, indent=2))
    print(f"Wrote {ratings_path} ({len(rows)} teams, {matches_used} matches)")

    history_path = OUT_DIR / f"history_{path_prefix}.json"
    history_path.write_text(json.dumps(history_out))
    print(f"Wrote {history_path}")


def compute_league(key: str, cfg: dict):
    matches_path = DATA_DIR / f"matches_{key}.csv"
    if not matches_path.exists():
        print(f"Skipping {cfg['label']} ({key}): {matches_path} not found -- run fetch_data.py first.")
        return

    print(f"=== {cfg['label']} ({key}) ===")
    df = pd.read_csv(matches_path)

    finished = df[df["status"] == "Ended"].copy()
    finished = finished.dropna(subset=["home_score_current", "away_score_current"])
    finished["start_timestamp"] = pd.to_numeric(finished["start_timestamp"], errors="coerce")
    finished = finished.sort_values("start_timestamp", kind="stable")

    meta_path = DATA_DIR / f"meta_{key}.json"
    fetched_at = None
    if meta_path.exists():
        fetched_at = json.loads(meta_path.read_text()).get("fetched_at_utc")

    # --- all-time pass: every match ever played, one continuous rating ---
    rows_all, history_all = run_elo_pass(finished)
    write_output(rows_all, history_all, fetched_at, len(finished), key)

    # --- current-season pass: reset to 1500, only this season's matches ---
    if "season" in finished.columns and finished["season"].notna().any():
        current_season_year = int(finished["season"].dropna().max())
        season_matches = finished[finished["season"] == current_season_year]
        rows_season, history_season = run_elo_pass(season_matches)
        write_output(
            rows_season, history_season, fetched_at, len(season_matches),
            f"{key}_season",
            extra_meta={"season_year": current_season_year},
        )
    else:
        print(f"No 'season' column found for {key} -- skipping season-only output.")


def main():
    for key, cfg in LEAGUES.items():
        compute_league(key, cfg)


if __name__ == "__main__":
    main()
