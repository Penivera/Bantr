from datetime import datetime, timezone, timedelta

BET_SEED: bytes = b"bet"
BET_VAULT_SEED: bytes = b"bet_vault"

STAT_KEY_GOAL_P1: int = 1
STAT_KEY_GOAL_P2: int = 2
STAT_KEY_YELLOW_P1: int = 3
STAT_KEY_YELLOW_P2: int = 4
STAT_KEY_RED_P1: int = 5
STAT_KEY_RED_P2: int = 6
STAT_KEY_CORNER_P1: int = 7
STAT_KEY_CORNER_P2: int = 8

MARKET_NEXT_GOAL: str = "next_goal"
MARKET_NEXT_CARD: str = "next_card"
MARKET_NEXT_CORNER: str = "next_corner"
MARKET_MATCH_WINNER: str = "match_winner"
VALID_MARKETS: tuple[str, ...] = (MARKET_NEXT_GOAL, MARKET_NEXT_CARD, MARKET_NEXT_CORNER, MARKET_MATCH_WINNER)

UPCOMING_FIXTURES: list[dict] = [
    {"id": "18257865", "home": "France", "away": "England", "time_utc": "2026-07-18T21:00:00Z", "stage": "3rd Place Final"},
    {"id": "18257739", "home": "Spain", "away": "Argentina", "time_utc": "2026-07-19T19:00:00Z", "stage": "Final"},
]

BET_STATUS_OPEN: str = "open"
BET_STATUS_CALLED: str = "called"
BET_STATUS_FUNDED: str = "funded"
BET_STATUS_RESOLVED: str = "resolved"
BET_STATUS_VOID: str = "void"

DEFAULT_BET_DEADLINE_DAYS: int = 7

FLAGS: dict[str, str] = {
    "France": "\U0001f1eb\U0001f1f7", "England": "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
    "Spain": "\U0001f1ea\U0001f1f8", "Argentina": "\U0001f1e6\U0001f1f7",
    "Brazil": "\U0001f1e7\U0001f1f7", "Japan": "\U0001f1ef\U0001f1f5",
    "Germany": "\U0001f1e9\U0001f1ea", "Paraguay": "\U0001f1f5\U0001f1fe",
    "Netherlands": "\U0001f1f3\U0001f1f1", "Morocco": "\U0001f1f2\U0001f1e6",
    "Norway": "\U0001f1f3\U0001f1f4", "Sweden": "\U0001f1f8\U0001f1ea",
    "Mexico": "\U0001f1f2\U0001f1fd", "Ecuador": "\U0001f1ea\U0001f1e8",
    "Belgium": "\U0001f1e7\U0001f1ea", "Senegal": "\U0001f1f8\U0001f1f3",
    "USA": "\U0001f1fa\U0001f1f8", "Austria": "\U0001f1e6\U0001f1f9",
    "Portugal": "\U0001f1f5\U0001f1f9", "Croatia": "\U0001f1ed\U0001f1f7",
    "Switzerland": "\U0001f1e8\U0001f1ed", "Algeria": "\U0001f1e9\U0001f1ff",
    "Australia": "\U0001f1e6\U0001f1fa", "Egypt": "\U0001f1ea\U0001f1ec",
    "Colombia": "\U0001f1e8\U0001f1f4", "Ghana": "\U0001f1ec\U0001f1ed",
    "Canada": "\U0001f1e8\U0001f1e6", "South Africa": "\U0001f1ff\U0001f1e6",
    "Ivory Coast": "\U0001f1e8\U0001f1ee", "Congo DR": "\U0001f1e8\U0001f1e9",
    "Bosnia & Herzegovina": "\U0001f1e7\U0001f1e6", "Cape Verde": "\U0001f1e8\U0001f1fb",
    "Jordan": "\U0001f1ef\U0001f1f4",
}


def flag_for(team: str) -> str:
    return FLAGS.get(team, "\U0001f3df\ufe0f")

HEARTBEAT_GRACE_SECONDS: int = 120

PLAYER_MARKETS: dict[str, str] = {
    "hat trick": "hat_trick", "hattrick": "hat_trick", "hat-trick": "hat_trick",
    "first scorer": "first_scorer", "first goal": "first_scorer", "scores first": "first_scorer",
    "two goals": "two_goals", "brace": "two_goals", "2 goals": "two_goals",
    "scores": "scores", "score": "scores", "goal": "scores",
    "card": "player_card", "booked": "player_card", "red card": "player_card",
    "clean sheet": "clean_sheet", "cleansheet": "clean_sheet",
}

PLAYER_MARKET_REQUIRED_EVENTS: dict[str, int] = {
    "hat_trick": 3, "two_goals": 2, "first_scorer": 1,
    "scores": 1, "player_card": 1, "clean_sheet": 0,
}

POLL_TIMEOUT_SECONDS: int = 90


def default_deadline() -> int:
    return int((datetime.now(timezone.utc) + timedelta(days=DEFAULT_BET_DEADLINE_DAYS)).timestamp())
