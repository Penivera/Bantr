"""Player resolution and matching for BanterBot.

Since TxLINE devnet does not expose a dedicated /fixtures/players endpoint,
we resolve player bets using:
  1. AI-driven team mapping (resolve_player_team in NLU)
  2. Stream event Participant field (1 or 2) + Action types
  3. Stored fixture_player_id when available from event payload
"""
import re
import unicodedata
from app.core.logging import get_logger

logger = get_logger(__name__)


def normalize_name(name: str) -> str:
    """Case-insensitive, accent-insensitive, punctuation-free normalization."""
    name = name.lower().strip()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[^\w\s]", "", name)
    return " ".join(name.split())


def resolve_player_from_roster(user_input: str, roster: list[dict]) -> list[dict]:
    """Match user-provided player name against a roster of {name, fixturePlayerId, normativeId, ...} entries.
    Returns a list of matches sorted by confidence."""
    needle = normalize_name(user_input)
    matches = []

    for player in roster:
        display = player.get("preferredName", player.get("name", ""))
        norm = normalize_name(display)
        first = norm.split()[-1] if norm.split() else ""
        last = norm.split()[0] if norm.split() else ""
        full = norm

        score = 0
        if needle == full:
            score = 100
        elif needle == first:
            score = 80
        elif needle == last:
            score = 80
        elif needle in full:
            score = 60
        elif first.startswith(needle) or last.startswith(needle):
            score = 40

        if score > 0:
            matches.append({**player, "match_score": score, "match_display": display})

    matches.sort(key=lambda x: -x["match_score"])
    return matches


PLAYER_ACTION_TYPES = {
    "shot": "shot",
    "goal": "goal",
    "penalty": "penalty",
    "free_kick": "free_kick",
    "card": "card",
    "yellow_card": "card",
    "red_card": "card",
    "substitution": "substitution",
    "var": "var",
    "assist": "assist",
}

PARTICIPANT_TO_TEAM: dict[int, str] = {
    1: "team_1",
    2: "team_2",
}
