import httpx
from app.core.config import settings
from app.core.logging import get_logger
from app.services.txline.auth import TxLineCredentials

logger = get_logger(__name__)


async def fetch_fixture_roster(
    fixture_id: str, credentials: TxLineCredentials
) -> dict[str, list[dict]]:
    origin = settings.txline_api_origin
    headers = {
        "Authorization": f"Bearer {credentials.jwt}",
        "X-Api-Token": credentials.api_token,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{origin}/api/scores/snapshot/{fixture_id}", headers=headers)
        if resp.status_code != 200:
            logger.warning("roster_fetch_failed", fixture_id=fixture_id, status=resp.status_code)
            return {}

        data = resp.json()

    rosters: dict[str, list[dict]] = {}
    for item in data:
        if item.get("Action") != "lineups":
            continue
        for team in item.get("Lineups", []):
            team_name = team.get("preferredName", "?")
            players: list[dict] = []
            for entry in team.get("lineups", []):
                pl = entry.get("player", {})
                players.append({
                    "fixture_player_id": entry.get("fixturePlayerId"),
                    "normative_id": pl.get("normativeId"),
                    "preferred_name": pl.get("preferredName", ""),
                    "position_id": entry.get("positionId"),
                    "starter": entry.get("starter", False),
                    "roster_number": entry.get("rosterNumber", ""),
                    "country": pl.get("country", ""),
                })
            rosters[team_name] = players

    logger.info("roster_fetched", fixture_id=fixture_id, teams=list(rosters.keys()),
                counts={k: len(v) for k, v in rosters.items()})
    return rosters


def build_player_lookup(rosters: dict[str, list[dict]]) -> dict[int, dict]:
    lookup: dict[int, dict] = {}
    for team_name, players in rosters.items():
        for p in players:
            nid = p.get("normative_id")
            if nid is not None:
                lookup[nid] = {**p, "team_name": team_name}
    return lookup
