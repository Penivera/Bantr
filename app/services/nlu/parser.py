import httpx
import json
import re
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a betting bot command parser for a Telegram group. Users place wagers on live football matches.

Parse the user's message into a JSON object with:
- "intent": one of "bet", "call", "fixtures", "track", "leaderboard", "unknown"
- "params": a flat key→string map of extracted parameters
- "confidence": 0.0–1.0

Intent rules:
- "bet": Extract opponent (@user or name), market (next_goal/next_card/next_corner), amount (number). If a player name is mentioned, extract it as "player". Important: if a player is mentioned and the known fixture teams include that player's known national team, set "player_team" to the corresponding side ("home" or "away").
- "call": Extract betId
- "fixtures": User wants to see matches
- "track": Extract fixtureId
- "leaderboard": User wants rankings
- "unknown": Cannot determine intent

Output ONLY valid JSON, no other text."""


class NLUParser:
    async def parse(self, text: str, fixture_context: list[dict] | None = None) -> dict:
        context_str = ""
        if fixture_context:
            lines = [
                f"  - {f['id']}: {f.get('home', '?')} vs {f.get('away', '?')} ({f.get('stage', '?')})"
                for f in fixture_context
            ]
            context_str = "\nKnown fixtures (use home/away for player_team):\n" + "\n".join(lines)

        system_msg = SYSTEM_PROMPT + context_str

        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.post(
                    settings.ai_deepseek_api_base,
                    json={
                        "model": settings.ai_deepseek_model,
                        "messages": [
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": text},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 256,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {settings.ai_deepseek_api_key}",
                    },
                )
                raw = resp.json()["choices"][0]["message"]["content"]
                match = re.search(r"\{[\s\S]*\}", raw)
                if match:
                    return json.loads(match.group())
        except Exception as e:
            logger.warning("nlu_parse_failed", error=str(e))

        return {"intent": "unknown", "params": {}, "confidence": 0}

    async def resolve_player_team(self, player_name: str, fixture_info: dict) -> str | None:
        """Ask the model which team a player belongs to, given the fixture context."""
        home = fixture_info.get("home", "?")
        away = fixture_info.get("away", "?")
        prompt = (
            f"Which national team does the football player '{player_name}' play for? "
            f"Reply with ONLY the country/team name and nothing else. "
        )

        try:
            async with httpx.AsyncClient(timeout=6) as client:
                resp = await client.post(
                    settings.ai_deepseek_api_base,
                    json={
                        "model": settings.ai_deepseek_model,
                        "messages": [
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.0,
                        "max_tokens": 256,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {settings.ai_deepseek_api_key}",
                    },
                )
                raw = resp.json()["choices"][0]["message"]["content"].strip().lower()
                home_lower = home.lower()
                away_lower = away.lower()
                if raw == home_lower or home_lower in raw:
                    return "home"
                elif raw == away_lower or away_lower in raw:
                    return "away"
        except Exception as e:
            logger.warning("resolve_player_team_failed", player=player_name, error=str(e))

        return None
