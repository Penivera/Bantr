from dataclasses import dataclass
from enum import StrEnum
from solders.pubkey import Pubkey


class SupportedToken(StrEnum):
    USDC = "USDC"


@dataclass(frozen=True)
class TokenConfig:
    symbol: SupportedToken
    decimals: int
    mint_devnet: Pubkey
    mint_mainnet: Pubkey

    def mint(self, devnet: bool = True) -> Pubkey:
        return self.mint_devnet if devnet else self.mint_mainnet


TOKENS: dict[SupportedToken, TokenConfig] = {
    SupportedToken.USDC: TokenConfig(
        symbol=SupportedToken.USDC,
        decimals=6,
        mint_devnet=Pubkey.from_string("Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr"),
        mint_mainnet=Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"),
    ),
}


def get_token(symbol: str) -> TokenConfig:
    try:
        return TOKENS[SupportedToken(symbol)]
    except (ValueError, KeyError):
        return TOKENS[SupportedToken.USDC]


def get_token_mint(symbol: str, devnet: bool = True) -> Pubkey:
    return get_token(symbol).mint(devnet)


def get_token_decimals(symbol: str) -> int:
    return get_token(symbol).decimals
