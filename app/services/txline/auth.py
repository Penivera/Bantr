import json
import base64
import httpx
from nacl.signing import SigningKey
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import ID as SYSTEM_PROGRAM_ID
from solders.instruction import Instruction, AccountMeta
from app.core.config import settings
from app.core.exceptions import TxLineAuthError
from app.core.logging import get_logger

logger = get_logger(__name__)

TOKEN_2022_PROGRAM_ID = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
SYSVAR_RENT = Pubkey.from_string("SysvarRent111111111111111111111111111111111")


def get_associated_token_address(owner: Pubkey, mint: Pubkey, token_program_id: Pubkey = TOKEN_PROGRAM_ID) -> Pubkey:
    seeds = [bytes(owner), bytes(token_program_id), bytes(mint)]
    ata, _ = Pubkey.find_program_address(seeds, ASSOCIATED_TOKEN_PROGRAM_ID)
    return ata


def create_associated_token_account_ix(
    payer: Pubkey, owner: Pubkey, mint: Pubkey, token_program_id: Pubkey = TOKEN_2022_PROGRAM_ID,
) -> Instruction:
    ata = get_associated_token_address(owner, mint, token_program_id)
    keys = [
        AccountMeta(pubkey=payer, is_signer=True, is_writable=True),
        AccountMeta(pubkey=ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=owner, is_signer=False, is_writable=False),
        AccountMeta(pubkey=mint, is_signer=False, is_writable=False),
        AccountMeta(pubkey=SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=token_program_id, is_signer=False, is_writable=False),
        AccountMeta(pubkey=SYSVAR_RENT, is_signer=False, is_writable=False),
    ]
    return Instruction(program_id=ASSOCIATED_TOKEN_PROGRAM_ID, accounts=keys, data=b"")


class TxLineCredentials:
    jwt: str
    api_token: str
    tx_sig: str

    def __init__(self, jwt: str = "", api_token: str = "", tx_sig: str = ""):
        self.jwt = jwt
        self.api_token = api_token
        self.tx_sig = tx_sig


def _find_pda(seeds: list[bytes], program_id: Pubkey) -> tuple[Pubkey, int]:
    return Pubkey.find_program_address(seeds, program_id)


async def get_guest_jwt() -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{settings.txline_api_origin}/auth/guest/start")
        resp.raise_for_status()
        return resp.json()["token"]


async def _ensure_token_account(keypair: Keypair) -> None:
    from solders.transaction import Transaction
    from solders.message import MessageV0
    from solders.hash import Hash

    mint = Pubkey.from_string(settings.txline_txl_token_mint)
    user_pubkey = keypair.pubkey()
    ata = get_associated_token_address(user_pubkey, mint, TOKEN_2022_PROGRAM_ID)

    async with httpx.AsyncClient() as client:
        resp = await client.post(settings.solana_rpc_url, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getAccountInfo",
            "params": [str(ata), {"encoding": "base64"}]
        })
        result = resp.json().get("result", {}).get("value")
        if result is not None:
            return

        ix = create_associated_token_account_ix(
            payer=user_pubkey, owner=user_pubkey, mint=mint,
        )
        tx = Transaction.new_with_payer([ix], user_pubkey)
        blockhash_resp = await client.post(settings.solana_rpc_url, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "confirmed"}]
        })
        blockhash_str = blockhash_resp.json()["result"]["value"]["blockhash"]
        blockhash = Hash.from_string(blockhash_str)
        msg = MessageV0.try_compile(
            payer=user_pubkey,
            instructions=[ix],
            address_lookup_table_accounts=[],
            recent_blockhash=blockhash,
        )
        tx.sign([keypair], blockhash)

        await client.post(settings.solana_rpc_url, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "sendTransaction",
            "params": [base64.b64encode(bytes(tx)).decode(), {"encoding": "base64", "preflightCommitment": "confirmed"}]
        })
        logger.info("token_account_created", ata=str(ata))


async def subscribe_on_chain(keypair: Keypair) -> str:
    from solders.transaction import Transaction
    from solders.message import MessageV0
    from solders.hash import Hash
    import struct

    program_id = Pubkey.from_string(settings.txline_program_id)
    mint = Pubkey.from_string(settings.txline_txl_token_mint)
    user_pubkey = keypair.pubkey()

    token_treasury_pda, _ = _find_pda([b"token_treasury_v2"], program_id)
    pricing_matrix_pda, _ = _find_pda([b"pricing_matrix"], program_id)

    token_treasury_vault = get_associated_token_address(
        token_treasury_pda, mint, TOKEN_2022_PROGRAM_ID
    )
    user_ata = get_associated_token_address(
        user_pubkey, mint, TOKEN_2022_PROGRAM_ID
    )

    await _ensure_token_account(keypair)

    discriminator = bytes([254, 28, 191, 138, 156, 179, 183, 53])
    service_level = struct.pack("<H", settings.txline_service_level_id)
    weeks = struct.pack("<B", settings.txline_duration_weeks)
    data = discriminator + service_level + weeks

    accounts = [
        AccountMeta(pubkey=user_pubkey, is_signer=True, is_writable=True),
        AccountMeta(pubkey=pricing_matrix_pda, is_signer=False, is_writable=False),
        AccountMeta(pubkey=mint, is_signer=False, is_writable=False),
        AccountMeta(pubkey=user_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_treasury_vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_treasury_pda, is_signer=False, is_writable=False),
        AccountMeta(pubkey=TOKEN_2022_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=ASSOCIATED_TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    ix = Instruction(program_id=program_id, accounts=accounts, data=data)

    async with httpx.AsyncClient() as client:
        blockhash_resp = await client.post(settings.solana_rpc_url, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "confirmed"}]
        })
        blockhash_str = blockhash_resp.json()["result"]["value"]["blockhash"]
        blockhash = Hash.from_string(blockhash_str)

    msg = MessageV0.try_compile(
        payer=user_pubkey,
        instructions=[ix],
        address_lookup_table_accounts=[],
        recent_blockhash=blockhash,
    )
    tx = Transaction.new_with_payer([ix], user_pubkey)
    tx.sign([keypair], blockhash)

    async with httpx.AsyncClient(timeout=30) as client:
        send_resp = await client.post(settings.solana_rpc_url, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "sendTransaction",
            "params": [base64.b64encode(bytes(tx)).decode(), {"encoding": "base64", "preflightCommitment": "confirmed"}]
        })
        resp_json = send_resp.json()
        if "result" not in resp_json:
            raise Exception(f"sendTransaction failed: {resp_json}")
        tx_sig = resp_json["result"]

    logger.info("subscribed_on_chain", tx_sig=tx_sig)
    return tx_sig


async def activate_api_token(tx_sig: str, keypair: Keypair) -> str:
    jwt = await get_guest_jwt()
    message_str = f"{tx_sig}::{jwt}"
    message_bytes = message_str.encode("utf-8")
    signing_key = SigningKey(bytes(keypair)[:32])
    signed = signing_key.sign(message_bytes)
    wallet_signature = base64.b64encode(signed.signature).decode()

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.txline_api_origin}/api/token/activate",
            json={"txSig": tx_sig, "walletSignature": wallet_signature, "leagues": []},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        resp.raise_for_status()
        try:
            data = resp.json()
            api_token = data.get("token") if isinstance(data, dict) else data
        except Exception:
            api_token = resp.text.strip()
        logger.info("api_token_activated")
        return api_token


async def bootstrap_credentials(keypair: Keypair) -> TxLineCredentials:
    jwt = await get_guest_jwt()
    tx_sig = await subscribe_on_chain(keypair)
    api_token = await activate_api_token(tx_sig, keypair)
    return TxLineCredentials(jwt=jwt, api_token=api_token, tx_sig=tx_sig)
