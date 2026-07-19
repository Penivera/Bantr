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
from solders.sysvar import RENT
from app.core.config import settings
from app.core.logging import get_logger
from app.core.tokens import get_token_mint, get_token_decimals
from app.services.payments.solana_pay import derive_bet_pda, derive_vault_pda, IX_INITIALIZE_BET, IX_JOIN_BET
from spl.token.constants import TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID

logger = get_logger(__name__)

router = APIRouter()

PROGRAM_ID = Pubkey.from_string(settings.bet_escrow_program_id)


class TransactionRequestBody(BaseModel):
    account: str


def _derive_ata(owner: Pubkey, mint: Pubkey) -> Pubkey:
    return Pubkey.find_program_address(
        [bytes(owner), bytes(TOKEN_PROGRAM_ID), bytes(mint)],
        ASSOCIATED_TOKEN_PROGRAM_ID,
    )[0]


def _build_initialize_bet_ix(
    bet_pda: Pubkey,
    vault_pda: Pubkey,
    creator: Pubkey,
    creator_ata: Pubkey,
    stake_mint: Pubkey,
    bet_id: int,
    fixture_id: str,
    market: int,
    amount: int,
    resolve_deadline: int,
) -> Instruction:
    data = bytearray()
    data += IX_INITIALIZE_BET
    data += struct.pack("<Q", bet_id)
    fixture_bytes = fixture_id.encode("utf-8")
    data += struct.pack("<I", len(fixture_bytes))
    data += fixture_bytes
    data += struct.pack("<B", market)
    data += struct.pack("<Q", amount)
    data += struct.pack("<q", resolve_deadline)

    return Instruction(
        program_id=PROGRAM_ID,
        accounts=[
            AccountMeta(pubkey=creator, is_signer=True, is_writable=True),
            AccountMeta(pubkey=stake_mint, is_signer=False, is_writable=False),
            AccountMeta(pubkey=bet_pda, is_signer=False, is_writable=True),
            AccountMeta(pubkey=vault_pda, is_signer=False, is_writable=True),
            AccountMeta(pubkey=creator_ata, is_signer=False, is_writable=True),
            AccountMeta(pubkey=SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(pubkey=RENT, is_signer=False, is_writable=False),
        ],
        data=bytes(data),
    )


def _build_join_bet_ix(
    bet_pda: Pubkey,
    vault_pda: Pubkey,
    opponent: Pubkey,
    opponent_ata: Pubkey,
    stake_mint: Pubkey,
    bet_id: int,
) -> Instruction:
    data = bytearray()
    data += IX_JOIN_BET
    data += struct.pack("<Q", bet_id)

    return Instruction(
        program_id=PROGRAM_ID,
        accounts=[
            AccountMeta(pubkey=opponent, is_signer=True, is_writable=True),
            AccountMeta(pubkey=bet_pda, is_signer=False, is_writable=True),
            AccountMeta(pubkey=vault_pda, is_signer=False, is_writable=True),
            AccountMeta(pubkey=opponent_ata, is_signer=False, is_writable=True),
            AccountMeta(pubkey=stake_mint, is_signer=False, is_writable=False),
            AccountMeta(pubkey=SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(pubkey=RENT, is_signer=False, is_writable=False),
        ],
        data=bytes(data),
    )


@router.get("/api/pay")
async def solana_pay_preview(
    bet_id: str = Query(...),
):
    return JSONResponse({
        "label": "BanterBet",
        "icon": "https://usebantr.site/static/images/logo.png",
    })


@router.post("/api/pay")
async def solana_pay_transaction(
    bet_id: str = Query(...),
    fixture_id: str = Query(""),
    market: str = Query("1"),
    amount: str = Query("0"),
    resolve_deadline: str = Query("0"),
    instruction: str = Query("initialize_bet"),
    tokenMint: str = Query(""),
    tokenSymbol: str = Query("USDC"),
    body: TransactionRequestBody = None,
):
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
            raise HTTPException(status_code=400, detail="Account mismatch: bet is linked to a different wallet")
        container.store.update_bet(bet_id, {wallet_key: body.account})

    try:
        amount_display = float(amount)
    except (ValueError, TypeError):
        amount_display = 0

    decimals = get_token_decimals(tokenSymbol)
    amount_raw = int(amount_display * (10 ** decimals))

    try:
        market_val = int(market)
    except (ValueError, TypeError):
        market_val = 1

    try:
        deadline_val = int(resolve_deadline)
    except (ValueError, TypeError):
        deadline_val = 0

    bid_hash = int(hashlib.sha256(bet_id.encode()).hexdigest()[:16], 16) % (2**64)

    is_devnet = "devnet" in settings.solana_rpc_url
    stake_mint = get_token_mint(tokenSymbol, devnet=is_devnet)
    payer_ata = _derive_ata(payer, stake_mint)

    bet_pda, bump = derive_bet_pda(bet_id)
    vault_pda, _ = derive_vault_pda(bet_pda)

    try:
        recent_blockhash_resp = await _get_recent_blockhash()
        blockhash = Hash.from_string(recent_blockhash_resp["blockhash"])
    except Exception as e:
        logger.error("blockhash_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Unable to fetch blockhash")

    instructions = []

    instructions.append(
        Instruction(
            program_id=ASSOCIATED_TOKEN_PROGRAM_ID,
            accounts=[
                AccountMeta(pubkey=payer, is_signer=True, is_writable=True),
                AccountMeta(pubkey=payer_ata, is_signer=False, is_writable=True),
                AccountMeta(pubkey=payer, is_signer=False, is_writable=False),
                AccountMeta(pubkey=stake_mint, is_signer=False, is_writable=False),
                AccountMeta(pubkey=SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
                AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
            ],
            data=bytes([1]),
        )
    )

    if instruction == "join_bet":
        instructions.append(_build_join_bet_ix(
            bet_pda, vault_pda, payer, payer_ata, stake_mint, bid_hash,
        ))
    else:
        instructions.append(_build_initialize_bet_ix(
            bet_pda, vault_pda, payer, payer_ata, stake_mint, bid_hash,
            fixture_id, market_val, amount_raw, deadline_val,
        ))

    msg = SoldersMessage.new_with_blockhash(
        instructions=instructions,
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
