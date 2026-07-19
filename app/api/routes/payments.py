import uuid
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PaymentRecord:
    payment_id: str
    bet_id: str
    amount: float
    token_symbol: str
    token_mint: str
    recipient: str
    status: str = "pending"
    tx_signature: str | None = None
    payer_wallet: str | None = None
    instruction: str = "initialize_bet"
    created_at: int = field(default_factory=lambda: int(time.time()))
    expires_at: int = field(default_factory=lambda: int(time.time()) + 3600)

    def to_dict(self) -> dict:
        return {
            "payment_id": self.payment_id,
            "bet_id": self.bet_id,
            "amount": self.amount,
            "token_symbol": self.token_symbol,
            "token_mint": self.token_mint,
            "recipient": self.recipient,
            "status": self.status,
            "tx_signature": self.tx_signature,
            "payer_wallet": self.payer_wallet,
            "instruction": self.instruction,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


def create_payment_id() -> str:
    return uuid.uuid4().hex[:12]


# In-memory payment store (backed by Redis in production)
_payment_store: dict[str, PaymentRecord] = {}


def store_payment(record: PaymentRecord) -> None:
    _payment_store[record.payment_id] = record
    from app.core.dependencies import get_container
    container = get_container()
    if container.store.redis:
        import asyncio, json
        asyncio.ensure_future(container.store.redis.client.hset(
            f"banter:payment:{record.payment_id}",
            mapping={k: json.dumps(v) if not isinstance(v, (str, int, float, bool, type(None))) else str(v) if v is not None else ""
                     for k, v in record.to_dict().items()}))


def get_payment(payment_id: str) -> PaymentRecord | None:
    return _payment_store.get(payment_id)


def update_payment(payment_id: str, **kwargs) -> PaymentRecord | None:
    record = _payment_store.get(payment_id)
    if not record:
        return None
    for k, v in kwargs.items():
        setattr(record, k, v)
    from app.core.dependencies import get_container
    container = get_container()
    if container.store.redis:
        import asyncio, json
        asyncio.ensure_future(container.store.redis.client.hset(
            f"banter:payment:{payment_id}",
            mapping={k: json.dumps(v) if not isinstance(v, (str, int, float, bool, type(None))) else str(v) if v is not None else ""
                     for k, v in kwargs.items()}))
    return record


from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

payments_router = APIRouter()


class SubmitPaymentBody(BaseModel):
    tx_signature: str
    payer_wallet: str


@payments_router.get("/api/payments/{payment_id}")
async def get_payment_info(payment_id: str):
    record = get_payment(payment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Payment not found")
    if record.is_expired():
        raise HTTPException(status_code=410, detail="Payment expired")
    return JSONResponse(record.to_dict())


@payments_router.post("/api/payments/{payment_id}/submit")
async def submit_payment(payment_id: str, body: SubmitPaymentBody):
    record = get_payment(payment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Payment not found")
    if record.is_expired():
        raise HTTPException(status_code=410, detail="Payment expired")
    if record.status != "pending":
        raise HTTPException(status_code=409, detail="Payment already processed")

    import httpx, base64
    from app.core.config import settings
    from app.services.payments.solana_pay import PROGRAM_ID

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(settings.solana_rpc_url, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getTransaction",
            "params": [body.tx_signature, {"commitment": "confirmed", "encoding": "jsonParsed"}],
        })
        tx_data = resp.json().get("result")
        if not tx_data:
            raise HTTPException(status_code=400, detail="Transaction not found")

        meta = tx_data.get("meta", {})
        if meta.get("err"):
            raise HTTPException(status_code=400, detail=f"Transaction failed: {meta['err']}")

        message = tx_data.get("transaction", {}).get("message", {})
        account_keys = message.get("accountKeys", [])

        def _pubkey(ak) -> str:
            return ak.get("pubkey", "") if isinstance(ak, dict) else str(ak)

        fee_payer = _pubkey(account_keys[0]) if account_keys else ""
        if fee_payer != body.payer_wallet:
            raise HTTPException(status_code=400, detail="Payer wallet mismatch")

    update_payment(payment_id, status="confirmed", tx_signature=body.tx_signature, payer_wallet=body.payer_wallet)

    from app.core.dependencies import get_container
    container = get_container()
    if container.bot and record.bet_id:
        bet = container.store.get_bet(record.bet_id)
        if bet:
            chat_id = bet.get("chat_id", 0)
            import asyncio
            asyncio.ensure_future(
                container.bot.send_message(chat_id,
                    f"\u2705 Payment confirmed!\nAmount: {record.amount} {record.token_symbol}\nTx: {body.tx_signature[:16]}..."))

    return JSONResponse({"status": "confirmed", "tx_signature": body.tx_signature})


# ── Refund records ──

_refund_store: dict[str, PaymentRecord] = {}

def store_refund(record: PaymentRecord) -> None:
    _refund_store[record.payment_id] = record
    import asyncio
    asyncio.ensure_future(_persist_refund(record))


async def _persist_refund(record: PaymentRecord) -> None:
    try:
        from app.db.session import async_session
        from app.db.models import Refund
        async with async_session() as s:
            s.add(Refund(
                refund_id=record.payment_id,
                bet_id=record.bet_id,
                amount=record.amount,
                token_symbol=record.token_symbol,
                status=record.status,
            ))
            await s.commit()
    except Exception:
        pass


def get_refund(refund_id: str) -> PaymentRecord | None:
    return _refund_store.get(refund_id)


async def load_refund(refund_id: str) -> PaymentRecord | None:
    record = _refund_store.get(refund_id)
    if record:
        return record
    try:
        from app.db.session import async_session
        from app.db.models import Refund
        from sqlalchemy import select
        async with async_session() as s:
            row = (await s.execute(select(Refund).where(Refund.refund_id == refund_id))).scalar_one_or_none()
            if row:
                record = PaymentRecord(
                    payment_id=row.refund_id,
                    bet_id=row.bet_id,
                    amount=row.amount or 0,
                    token_symbol=row.token_symbol or "USDC",
                    token_mint="",
                    recipient="",
                    status=row.status or "pending",
                    instruction="refund_expired",
                )
                _refund_store[row.refund_id] = record
                return record
    except Exception:
        pass
    return None


@payments_router.get("/api/refunds/{refund_id}")
async def get_refund_info(refund_id: str):
    record = await load_refund(refund_id)
    if not record:
        raise HTTPException(status_code=404, detail="Refund not found")
    eligible = True
    reason = ""
    chain_status = None
    chain_creator = None
    try:
        from app.services.payments.solana_pay import fetch_bet_from_chain
        chain = await fetch_bet_from_chain(record.bet_id)
        if chain:
            chain_status = chain.get("status")
            chain_creator = chain.get("creator")
            if chain_status in ("resolved", "refunded"):
                eligible = False
                reason = "Already resolved on-chain"
            elif chain_status == "open" and chain.get("opponent"):
                eligible = False
                reason = "Bet has been accepted — cannot refund"
    except Exception:
        pass
    if not chain_creator:
        from app.core.dependencies import get_container
        bet = get_container().store.get_bet(record.bet_id)
        if bet:
            chain_creator = bet.get("creator_wallet") or bet.get("payment_reference")
    if record.status != "pending":
        eligible = False
        reason = "Already claimed"
    return JSONResponse({
        **record.to_dict(),
        "eligible": eligible,
        "reason": reason,
        "chain_status": chain_status,
        "creator_wallet": chain_creator,
    })


class ClaimRefundBody(BaseModel):
    tx_signature: str
    payer_wallet: str


@payments_router.post("/api/refunds/{refund_id}/claim")
async def claim_refund(refund_id: str, body: ClaimRefundBody):
    record = await load_refund(refund_id)
    if not record:
        raise HTTPException(status_code=404, detail="Refund not found")
    if record.status != "pending":
        raise HTTPException(status_code=409, detail="Refund already claimed")

    import httpx
    from app.core.config import settings
    from app.services.payments.solana_pay import fetch_bet_from_chain

    chain = await fetch_bet_from_chain(record.bet_id)
    if not chain:
        from app.core.dependencies import get_container
        bet = get_container().store.get_bet(record.bet_id)
        if bet and bet.get("creator_wallet") and bet["creator_wallet"] != body.payer_wallet:
            raise HTTPException(status_code=403, detail="Only the bet creator can claim this refund")
    elif chain.get("creator") != body.payer_wallet:
        raise HTTPException(status_code=403, detail="Only the bet creator can claim this refund")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(settings.solana_rpc_url, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getTransaction",
            "params": [body.tx_signature, {"commitment": "confirmed", "encoding": "jsonParsed"}],
        })
        tx_data = resp.json().get("result")
        if not tx_data:
            raise HTTPException(status_code=400, detail="Transaction not found")
        meta = tx_data.get("meta", {})
        if meta.get("err"):
            raise HTTPException(status_code=400, detail=f"Transaction failed: {meta['err']}")
        account_keys = tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [])
        def _pk(ak): return ak.get("pubkey", "") if isinstance(ak, dict) else str(ak)
        if account_keys and _pk(account_keys[0]) != body.payer_wallet:
            raise HTTPException(status_code=400, detail="Payer wallet mismatch")

    record.status = "claimed"
    record.tx_signature = body.tx_signature
    record.payer_wallet = body.payer_wallet

    return JSONResponse({"status": "claimed", "tx_signature": body.tx_signature})
