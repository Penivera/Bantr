import json
import os
from dotenv import load_dotenv
from solders.keypair import Keypair
from solders.pubkey import Pubkey

load_dotenv()


def load_wallet() -> Keypair:
    raw = os.environ.get("SOLANA_WALLET_SECRET_KEY", "[]")
    secret_bytes = bytes(json.loads(raw))
    return Keypair.from_bytes(secret_bytes)


def pubkey_to_string(pk: Pubkey | str) -> str:
    return str(pk) if isinstance(pk, Pubkey) else pk


WALLET = load_wallet()
WALLET_PUBKEY = str(WALLET.pubkey())
