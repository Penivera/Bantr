import struct
import base64
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from app.core.config import settings
from app.core.constants import default_deadline
from app.core.logging import get_logger

logger = get_logger(__name__)

PROGRAM_ID = Pubkey.from_string(settings.bet_escrow_program_id)

# Account discriminator for BetEscrow (first 8 bytes of sha256("account:BetEscrow"))
BET_ESCROW_DISCRIMINATOR = bytes([198, 247, 82, 132, 85, 253, 182, 140])


def derive_bet_pda(bet_id: str) -> tuple[Pubkey, int]:
    # Hash the bet ID string to a u64 for PDA derivation
    import hashlib
    bid = int(hashlib.sha256(bet_id.encode()).hexdigest()[:16], 16) % (2**64)
    buf = struct.pack("<Q", bid)
    return Pubkey.find_program_address([b"bet", buf], PROGRAM_ID)


def derive_vault_pda(bet_pda: Pubkey) -> tuple[Pubkey, int]:
    return Pubkey.find_program_address([b"bet_vault", bytes(bet_pda)], PROGRAM_ID)


SUPPORTED_TOKENS: dict[str, str] = {
    "USDC": "Gh9ZwEmdLJ8DscKNTkTqPBbNwJFNjZ2DRcaaFbwVLaNc",
    "USDT": "EJwZgeZrdC8TXTQbQBoL6bfuAnFUUy1PVCMB4DYPzVaS",
}


def build_transaction_request_url(
    instruction: str,
    params: dict[str, str],
) -> str:
    """Build a Solana Pay Transaction Request URL for the BetEscrow program."""
    from urllib.parse import urlencode, quote
    token = params.pop("token", settings.bet_payment_token_symbol)
    token_mint = SUPPORTED_TOKENS.get(token, SUPPORTED_TOKENS["USDC"])
    qs = urlencode({
        **params,
        "instruction": instruction,
        "programId": settings.bet_escrow_program_id,
        "tokenMint": token_mint,
        "tokenSymbol": token,
    })
    base = settings.app_base_url.rstrip("/")
    https_url = f"{base}/api/pay?{qs}"
    return f"solana:{quote(https_url, safe='')}"


def build_https_pay_url(
    instruction: str,
    params: dict[str, str],
) -> str:
    """Build the raw HTTPS URL (no solana: prefix) for wallets that fetch directly."""
    from urllib.parse import urlencode
    token = params.pop("token", settings.bet_payment_token_symbol)
    token_mint = SUPPORTED_TOKENS.get(token, SUPPORTED_TOKENS["USDC"])
    qs = urlencode({
        **params,
        "instruction": instruction,
        "programId": settings.bet_escrow_program_id,
        "tokenMint": token_mint,
        "tokenSymbol": token,
    })
    base = settings.app_base_url.rstrip("/")
    return f"{base}/api/pay?{qs}"


class SolanaPayService:
    program_id: str = settings.bet_escrow_program_id

    def derive_bet_pda(self, bet_id: str) -> str:
        pda, _ = derive_bet_pda(bet_id)
        return str(pda)

    def derive_vault_pda(self, bet_pda: str) -> str:
        pda, _ = derive_vault_pda(Pubkey.from_string(bet_pda))
        return str(pda)

    async def generate_payment_request(self, bet: dict, instruction: str = "initialize_bet") -> dict:
        market_map = {"next_goal": "1", "next_card": "2", "next_corner": "3", "match_winner": "4"}
        market = market_map.get(bet.get("market", "next_goal"), "1")
        deadline = default_deadline()

        solana_url = build_transaction_request_url(instruction, {
            "bet_id": bet["id"],
            "fixture_id": bet.get("fixture_id", ""),
            "market": market,
            "amount": str(bet.get("amount", 0)),
            "resolve_deadline": str(deadline),
        })

        https_url = build_https_pay_url(instruction, {
            "bet_id": bet["id"],
            "fixture_id": bet.get("fixture_id", ""),
            "market": market,
            "amount": str(bet.get("amount", 0)),
            "resolve_deadline": str(deadline),
        })

        bet_pda, _ = derive_bet_pda(bet["id"])

        qr_png_bytes = None
        try:
            import qrcode
            import io
            qr = qrcode.make(solana_url)
            buf = io.BytesIO()
            qr.save(buf, format="PNG")
            buf.seek(0)
            qr_png_bytes = buf.read()
        except ImportError:
            logger.warning("qrcode_not_installed")

        return {
            "transaction_request_url": solana_url,
            "https_url": https_url,
            "reference": str(bet_pda),
            "qr_png": qr_png_bytes,
        }

    def watch_for_deposit(self, reference: str, callback) -> None:
        import asyncio
        from solders.rpc.responses import GetAccountInfoResp
        import httpx

        async def _poll() -> None:
            bet_pda = Pubkey.from_string(reference)
            for _ in range(450):  # ~30 min timeout at 4s intervals
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(settings.solana_rpc_url, json={
                            "jsonrpc": "2.0", "id": 1,
                            "method": "getAccountInfo",
                            "params": [str(bet_pda), {"encoding": "base64"}]
                        })
                        result = resp.json().get("result", {}).get("value")
                        if result and result.get("data"):
                            raw_data = base64.b64decode(result["data"][0])
                            if raw_data[:8] == BET_ESCROW_DISCRIMINATOR and len(raw_data) > 9:
                                status_byte = raw_data[8 + 1 + 32 + 1 + 32 + 1 + 8 + 8 + 1]
                                status_map = {0: "Open", 1: "Funded", 2: "Resolved", 3: "Refunded"}
                                if status_map.get(status_byte) in ("Funded", "Resolved"):
                                    callback(True)
                                    return
                except Exception:
                    pass
                await asyncio.sleep(4)
            callback(False)

        asyncio.ensure_future(_poll())
