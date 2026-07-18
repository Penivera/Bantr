import httpx
import json
import re
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """Parse betting messages into JSON. Output ONLY JSON, no other text.

Intents: bet, call, fixtures, track, leaderboard, unknown.

For "bet": opponent(@user), market(next_goal/next_card/next_corner/match_winner/hat_trick/first_scorer/two_goals/scores/player_card/clean_sheet), amount(number), team(optional), player(optional).

Player markets: "hat trick" -> hat_trick, "first goal" / "scores first" -> first_scorer, "two goals" / "brace" -> two_goals, "scores" / "goal" -> scores, "card" / "booked" / "red card" -> player_card, "clean sheet" -> clean_sheet.
"win" or "will beat" = match_winner. Strip $ from amounts.

If a player name is mentioned (e.g. "Mbappe", "Messi"), set the player field.
If a team is mentioned without a player (e.g. "France", "Spain"), set the team field.

Example: {"intent":"bet","params":{"opponent":"@alice","market":"hat_trick","amount":"50","player":"Mbappe"},"confidence":0.95}
Example: {"intent":"bet","params":{"opponent":"@alice","market":"match_winner","amount":"10","team":"France"},"confidence":0.95}"""


class NLUParser:
    async def parse(self, text: str, fixture_context: list[dict] | None = None) -> dict:
        context_str = ""
        if fixture_context:
            lines = [f"  - {f['id']}: {f.get('home','?')} vs {f.get('away','?')} ({f.get('stage','?')})" for f in fixture_context]
            context_str = "\nKnown fixtures (use home/away for player_team):\n" + "\n".join(lines)

        system_msg = SYSTEM_PROMPT + context_str

        models = [settings.ai_deepseek_model] + [m.strip() for m in settings.ai_fallback_models.split(",") if m.strip()]

        for model in models:
            try:
                result = await self._call_model(model, system_msg, text)
                if result and result.get("confidence", 0) >= 0.4:
                    logger.info("nlu_parsed", model=model, intent=result.get("intent"))
                    return result
                logger.info("nlu_low_confidence", model=model, confidence=result.get("confidence", 0))
            except Exception as e:
                logger.warning("nlu_model_failed", model=model, error=str(e)[:60])

        return {"intent": "unknown", "params": {}, "confidence": 0}

    async def _call_model(self, model: str, system_msg: str, user_msg: str) -> dict:
        import re, json
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                settings.ai_deepseek_api_base,
                json={"model": model, "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ], "temperature": 0.1, "max_tokens": 2048},
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {settings.ai_deepseek_api_key}"})
            raw = resp.json()["choices"][0]["message"]["content"]
            if not raw:
                raw = resp.json()["choices"][0]["message"].get("reasoning_content", "")
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                return json.loads(match.group())
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
                        "max_tokens": 512,
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
