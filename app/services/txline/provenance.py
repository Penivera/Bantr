import httpx
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def get_proof_for_event(fixture_id: str, seq: int, stat_key: int, timestamp: int) -> str | None:
    from app.services.txline.auth import TxLineCredentials, get_guest_jwt
    from app.core.constants import STAT_KEY_GOAL_P1
    from solders.pubkey import Pubkey
    import struct

    jwt = await get_guest_jwt()
    api_base = f"{settings.txline_api_origin}/api"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{api_base}/scores/stat-validation",
            params={"fixtureId": fixture_id, "seq": seq, "statKey": stat_key},
            headers={"Authorization": f"Bearer {jwt}", "X-Api-Token": ""},
        )
        if resp.status_code != 200:
            return None
        val = resp.json()

    min_ts = val.get("summary", {}).get("updateStats", {}).get("minTimestamp", timestamp)
    epoch_day = int(min_ts / 86400000)
    program_id = Pubkey.from_string(settings.bet_escrow_program_id)
    pda, _ = Pubkey.find_program_address(
        [b"daily_scores_roots", struct.pack("<H", epoch_day)],
        program_id,
    )
    stat_value = val.get("statToProve", {}).get("value", "?")

    return (
        f"https://explorer.solana.com/address/{pda}?cluster=devnet"
        f" | fixture={fixture_id} seq={seq} statKey={stat_key}"
        f" | value={stat_value} program={settings.txline_program_id}"
    )
