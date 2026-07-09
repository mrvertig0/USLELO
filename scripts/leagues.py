"""
Shared league configuration for fetch_data.py and compute_elo.py.

Each entry defines a Sofascore tournament_id and a name_filter function
that decides whether a given "tournament" name string (as returned by
team_match_history_data) belongs to that league. Add a new league by
adding a new entry here -- fetch_data.py and compute_elo.py both loop
over LEAGUES automatically, no other code changes needed.
"""
import re


def _normalize(name) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def _usl2_filter(name) -> bool:
    norm = _normalize(name)
    # Exclude the league's old PDL branding (Premier Development League) --
    # same competition lineage, but PDL-era results predate the modern
    # USL League Two format and shouldn't be folded into these ratings.
    if "premier development" in norm or re.search(r"\bpdl\b", norm):
        return False
    return "usl" in norm and "league two" in norm


def _wleague_filter(name) -> bool:
    norm = _normalize(name)
    # Not to be confused with "USL Super League Women" -- a separate,
    # newer top-flight pro women's league. This matches "USL W League"
    # specifically (the amateur/college-age summer league).
    if "super league" in norm:
        return False
    return "usl" in norm and "w league" in norm


LEAGUES = {
    "usl2": {
        "label": "USL League Two",
        "short_label": "League Two",
        # https://www.sofascore.com/football/tournament/usa/usl-league-two/13546
        "tournament_id": 13546,
        "name_filter": _usl2_filter,
    },
    "wleague": {
        "label": "USL W League",
        "short_label": "W League",
        # https://www.sofascore.com/football/tournament/usa/usl-w-league/18890
        "tournament_id": 18890,
        "name_filter": _wleague_filter,
    },
}
