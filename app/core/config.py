from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Telegram
    telegram_bot_token: str = ""
    telegram_bot_username: str = "bantersol_bot"

    # Solana
    solana_wallet_secret_key: str = "[]"
    solana_rpc_url: str = "https://api.devnet.solana.com"

    # TxLINE
    txline_rpc_url: str = "https://api.devnet.solana.com"
    txline_api_origin: str = "https://txline-dev.txodds.com"
    txline_program_id: str = "6pW64gN1s2uqjHkn1unFeEjAwJkPGHoppGvS715wyP2J"
    txline_txl_token_mint: str = "4Zao8ocPhmMgq7PdsYWyxvqySMGx7xb9cMftPMkEokRG"
    txline_service_level_id: int = 1
    txline_duration_weeks: int = 4

    # AI
    ai_deepseek_api_base: str = "https://opencode.ai/zen/v1/chat/completions"
    ai_deepseek_api_key: str = "sk-vxOw6vyM8FDBZzgNl79WQ8OhunqBQiNNiGeXXOMeccsZ3p91afScgYo9dSvLJJtW"
    ai_deepseek_model: str = "deepseek-v4-flash-free"
    ai_fallback_models: str = "mimo-v2.5-free,north-mini-code-free,nemotron-3-ultra-free"

    # BetEscrow
    bet_escrow_program_id: str = "vaFdYpqXffc1QXpL1AauMpvAknBNjrdZYExMQg6wvgM"

    # App
    app_web_port: int = 3000
    app_log_level: str = "INFO"
    app_fixture_ids: str = "18257865,18257739"
    app_debug: bool = True
    app_webhook_url: str = ""


settings = Settings()
