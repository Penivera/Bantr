import base64
import struct
import hashlib
from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.transaction import Transaction
from solders.message import Message as SoldersMessage
from solders.hash import Hash
from solders.system_program import ID as SYSTEM_PROGRAM_ID
from app.core.config import settings
from app.core.logging import get_logger
from app.services.payments.solana_pay import derive_bet_pda, derive_vault_pda, BET_ESCROW_DISCRIMINATOR

logger = get_logger(__name__)

router = APIRouter()

PROGRAM_ID = Pubkey.from_string(settings.bet_escrow_program_id)

USDC_DECIMALS = 6


class TransactionRequestBody(BaseModel):
    account: str


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
    signer: Pubkey,
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
            AccountMeta(pubkey=signer, is_signer=True, is_writable=False),
            AccountMeta(pubkey=SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
        ],
        data=bytes(data),
    )


@router.get("/api/pay")
async def solana_pay_preview(
    bet_id: str = Query(...),
):
    """GET returns the label and icon for wallet preview. No transaction built yet."""
    from app.core.dependencies import get_container
    container = get_container()
    bet = container.store.get_bet(bet_id)
    if not bet:
        bet = {"id": bet_id, "amount": 0}

    token_symbol = settings.bet_payment_token_symbol
    amount_display = bet.get("amount", 0)

    return JSONResponse({
        "label": "BanterBet",
        "icon": "https://usebantr.site/static/images/logo.png",
        "message": f"Place bet {bet_id[:4]} — {amount_display:.1f} {token_symbol}",
    })


@router.post("/api/pay")
async def solana_pay_transaction(
    bet_id: str = Query(...),
    fixture_id: str = Query(""),
    market: str = Query("1"),
    amount: str = Query("0"),
    resolve_deadline: str = Query("0"),
    instruction: str = Query("initialize_bet"),
    programId: str = Query(""),
    tokenMint: str = Query(""),
    tokenSymbol: str = Query("USDC"),
    body: TransactionRequestBody = None,
):
    """POST with { "account": "<base58 pubkey>" } builds and returns the transaction."""
    if body is None or not body.account:
        raise HTTPException(status_code=400, detail="Missing 'account' field in request body")

    try:
        payer = Pubkey.from_string(body.account)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid account pubkey")

    from app.core.dependencies import get_container
    container = get_container()
    bet = container.store.get_bet(bet_id)

    wallet_key = "creator_wallet" if instruction != "join_bet" else "opponent_wallet"
    if bet:
        existing = bet.get(wallet_key)
        if existing and existing != body.account:
            raise HTTPException(status_code=400, detail=f"Account mismatch: bet is linked to a different wallet")
        container.store.update_bet(bet_id, {wallet_key: body.account})

    try:
        amount_display = float(amount)
    except (ValueError, TypeError):
        amount_display = 0

    amount_raw = int(amount_display * (10 ** USDC_DECIMALS))

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

    try:
        recent_blockhash_resp = await _get_recent_blockhash()
        blockhash = Hash.from_string(recent_blockhash_resp["blockhash"])
    except Exception as e:
        logger.error("blockhash_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Unable to fetch blockhash")

    if instruction == "join_bet":
        ix = _build_join_bet_ix(bet_pda, vault_pda, payer, bid_hash, amount_raw)
    else:
        ix = _build_initialize_bet_ix(
            bet_pda, vault_pda, payer, bid_hash,
            fixture_id_num, market_val, amount_raw,
            deadline_val, token_mint_pk,
        )

    msg = SoldersMessage.new_with_blockhash(
        instructions=[ix],
        payer=payer,
        blockhash=blockhash,
    )
    tx = Transaction.new_unsigned(msg)
    serialized_tx = base64.b64encode(bytes(tx)).decode()

    return JSONResponse({
        "transaction": serialized_tx,
        "message": f"Place bet {bet_id[:4]} on BanterBot\n{amount_display} {tokenSymbol}",
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
