import re
import unicodedata
from app.core.logging import get_logger

logger = get_logger(__name__)


def normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[^\w\s]", "", name)
    return " ".join(name.split())


def _expand_name_tokens(display_name: str) -> set[str]:
    parts = [p.strip() for p in display_name.split(",")]
    tokens: set[str] = set()
    if len(parts) >= 2:
        surname = parts[0]
        firstname = parts[1]
        tokens.add(normalize_name(f"{firstname} {surname}"))
        tokens.add(normalize_name(surname))
        tokens.add(normalize_name(firstname))
        surname_parts = surname.split()
        firstname_parts = firstname.split()
        tokens.add(normalize_name(firstname_parts[0] if firstname_parts else firstname))
        tokens.add(normalize_name(surname_parts[-1] if surname_parts else surname))
    else:
        tokens.add(normalize_name(display_name))
    return tokens


def resolve_player_from_roster(user_input: str, roster: list[dict]) -> list[dict]:
    needle = normalize_name(user_input)
    if not needle:
        return []

    matches = []

    for player in roster:
        display = player.get("preferred_name", player.get("preferredName", player.get("name", "")))
        if not display:
            continue

        variants = _expand_name_tokens(display)
        norm_display = normalize_name(display)

        score = 0

        if needle == norm_display:
            score = 100
        elif any(needle == v for v in variants):
            score = 90
        elif needle in norm_display:
            score = 70
        elif any(needle in v and len(needle) >= 3 for v in variants):
            score = 60
        elif any(v.startswith(needle) and len(needle) >= 3 for v in variants):
            score = 50
        elif any(v in needle for v in variants if len(v) >= 3):
            score = 40
        elif norm_display.startswith(needle) and len(needle) >= 3:
            score = 35

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
