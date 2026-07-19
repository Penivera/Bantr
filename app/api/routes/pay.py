import base64
import struct
import hashlib
from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import JSONResponse
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.transaction import Transaction
from solders.message import Message as SoldersMessage
from solders.hash import Hash
from solders.system_program import ID as SYSTEM_PROGRAM_ID
from app.core.config import settings
from app.core.security import WALLET
from app.core.logging import get_logger
from app.services.payments.solana_pay import derive_bet_pda, derive_vault_pda, BET_ESCROW_DISCRIMINATOR

logger = get_logger(__name__)

router = APIRouter()

PROGRAM_ID = Pubkey.from_string(settings.bet_escrow_program_id)


def _build_initialize_bet_ix(
    bet_pda: Pubkey,
    vault_pda: Pubkey,
    creator: Pubkey,
    bet_id: int,
    fixture_id: int,
    market: int,
    amount: int,
    resolve_deadline: int,
    token_mint: Pubkey,
) -> Instruction:
    data = bytearray()
    data += BET_ESCROW_DISCRIMINATOR
    data += struct.pack("<Q", 0)
    data += struct.pack("<Q", bet_id)
    data += struct.pack("<Q", fixture_id)
    data += struct.pack("<Q", market)
    data += struct.pack("<Q", amount)
    data += struct.pack("<Q", resolve_deadline)
    data += bytes(token_mint)

    return Instruction(
        program_id=PROGRAM_ID,
        accounts=[
            AccountMeta(pubkey=bet_pda, is_signer=False, is_writable=True),
            AccountMeta(pubkey=vault_pda, is_signer=False, is_writable=True),
            AccountMeta(pubkey=creator, is_signer=True, is_writable=False),
            AccountMeta(pubkey=SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
        ],
        data=bytes(data),
    )


def _build_join_bet_ix(
    bet_pda: Pubkey,
    vault_pda: Pubkey,
    opponent: Pubkey,
    bet_id: int,
    amount: int,
) -> Instruction:
    data = bytearray()
    data += BET_ESCROW_DISCRIMINATOR
    data += struct.pack("<Q", 1)
    data += struct.pack("<Q", bet_id)
    data += struct.pack("<Q", amount)

    return Instruction(
        program_id=PROGRAM_ID,
        accounts=[
            AccountMeta(pubkey=bet_pda, is_signer=False, is_writable=True),
            AccountMeta(pubkey=vault_pda, is_signer=False, is_writable=True),
            AccountMeta(pubkey=opponent, is_signer=True, is_writable=False),
            AccountMeta(pubkey=SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
        ],
        data=bytes(data),
    )


@router.get("/api/pay")
async def solana_pay_request(
    bet_id: str = Query(...),
    fixture_id: str = Query(""),
    market: str = Query("1"),
    amount: str = Query("0"),
    resolve_deadline: str = Query("0"),
    instruction: str = Query("initialize_bet"),
    programId: str = Query(""),
    tokenMint: str = Query(""),
    tokenSymbol: str = Query("USDC"),
):
    try:
        amount_val = int(float(amount) * 1_000_000)
    except (ValueError, TypeError):
        amount_val = 0

    try:
        market_val = int(market)
    except (ValueError, TypeError):
        market_val = 1

    try:
        deadline_val = int(resolve_deadline)
    except (ValueError, TypeError):
        deadline_val = 0

    try:
        fixture_id_num = int(fixture_id) if fixture_id else 0
    except (ValueError, TypeError):
        fixture_id_num = 0

    bid_hash = int(hashlib.sha256(bet_id.encode()).hexdigest()[:16], 16) % (2**64)

    try:
        token_mint_pk = Pubkey.from_string(tokenMint) if tokenMint else Pubkey.from_bytes(bytes(32))
    except Exception:
        token_mint_pk = Pubkey.from_bytes(bytes(32))

    bet_pda, bump = derive_bet_pda(bet_id)
    vault_pda, _ = derive_vault_pda(bet_pda)
    creator = WALLET.pubkey()

    try:
        recent_blockhash_resp = await _get_recent_blockhash()
        blockhash = Hash.from_string(recent_blockhash_resp["blockhash"])
    except Exception as e:
        logger.error("blockhash_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Unable to fetch blockhash")

    if instruction == "join_bet":
        ix = _build_join_bet_ix(bet_pda, vault_pda, creator, bid_hash, amount_val)
    else:
        ix = _build_initialize_bet_ix(
            bet_pda, vault_pda, creator, bid_hash,
            fixture_id_num, market_val, amount_val,
            deadline_val, token_mint_pk,
        )

    msg = SoldersMessage.new_with_blockhash(
        instructions=[ix],
        payer=creator,
        blockhash=blockhash,
    )
    tx = Transaction.new_unsigned(msg)

    serialized_tx = base64.b64encode(bytes(tx)).decode()

    return JSONResponse({
        "label": "BanterBet",
        "icon": "https://usebantr.site/static/images/logo.png",
        "transaction": serialized_tx,
        "message": f"Place bet {bet_id[:4]} on BanterBot\n{amount} {tokenSymbol}",
    })


async def _get_recent_blockhash() -> dict:
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(settings.solana_rpc_url, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "processed"}],
        })
        result = resp.json()["result"]["value"]
        return result
