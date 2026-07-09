"""
Compute Elo ratings for USL League Two teams from data/matches.csv.

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

Writes:
    docs/data/ratings.json  -- current ranking table
    docs/data/history.json  -- rating trajectory per team (for sparklines)
"""
import json
from pathlib import Path

import pandas as pd

# --- tunables -----------------------------------------------------------
STARTING_RATING = 1500.0
HOME_ADVANTAGE = 60.0     # rating points added to home side before Elo calc
K_FACTOR = 26.0           # domestic-league-appropriate; eloratings.net uses
                           # 20 (friendly) to 60 (World Cup); this sits in
                           # between since USL2 results are competitive but
                           # squads/rosters can be fluid week to week.
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


def main():
    matches_path = DATA_DIR / "matches.csv"
    if not matches_path.exists():
        raise SystemExit(f"{matches_path} not found -- run fetch_data.py first.")

    df = pd.read_csv(matches_path)

    finished = df[df["status"] == "Ended"].copy()
    finished = finished.dropna(subset=["home_score_current", "away_score_current"])
    finished["start_timestamp"] = pd.to_numeric(finished["start_timestamp"], errors="coerce")
    finished = finished.sort_values("start_timestamp", kind="stable")

    ratings: dict[int, float] = {}
    names: dict[int, str] = {}
    record: dict[int, dict] = {}   # team_id -> {wins, draws, losses, gp}
    history: dict[int, list] = {}  # team_id -> [{"t": timestamp, "rating": r}]

    def ensure_team(team_id: int, name: str):
        if team_id not in ratings:
            ratings[team_id] = STARTING_RATING
            names[team_id] = name
            record[team_id] = {"wins": 0, "draws": 0, "losses": 0, "gp": 0}
            history[team_id] = [{"t": None, "rating": STARTING_RATING}]

    for _, row in finished.iterrows():
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
        rows.append({
            "team_id": tid,
            "team": names[tid],
            "rating": round(rating, 1),
            "games_played": rec["gp"],
            "wins": rec["wins"],
            "draws": rec["draws"],
            "losses": rec["losses"],
        })

    rows.sort(key=lambda r: r["rating"], reverse=True)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i

    meta_path = DATA_DIR / "meta.json"
    fetched_at = None
    if meta_path.exists():
        fetched_at = json.loads(meta_path.read_text()).get("fetched_at_utc")

    ratings_out = {
        "generated_at_utc": pd.Timestamp.now('UTC').isoformat(),
        "data_fetched_at_utc": fetched_at,
        "matches_used": len(finished),
        "k_factor": K_FACTOR,
        "home_advantage": HOME_ADVANTAGE,
        "starting_rating": STARTING_RATING,
        "teams": rows,
    }
    (OUT_DIR / "ratings.json").write_text(json.dumps(ratings_out, indent=2))
    print(f"Wrote {OUT_DIR / 'ratings.json'} ({len(rows)} teams, {len(finished)} matches)")

    history_out = {str(tid): hist for tid, hist in history.items()}
    (OUT_DIR / "history.json").write_text(json.dumps(history_out))
    print(f"Wrote {OUT_DIR / 'history.json'}")


if __name__ == "__main__":
    main()
