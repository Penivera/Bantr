from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Telegram
    telegram_bot_token: str = Field(..., description="Telegram bot API token")
    telegram_bot_username: str = Field(default="bantersol_bot", description="Telegram bot username")

    # Solana
    solana_wallet_secret_key: str = Field(..., description="Solana wallet secret key")
    solana_rpc_url: str = Field(default="https://api.devnet.solana.com", description="Solana RPC URL")

    # TxLINE
    txline_rpc_url: str = Field(default="https://api.devnet.solana.com", description="TxLINE RPC URL")
    txline_api_origin: str = Field(default="https://txline-dev.txodds.com", description="TxLINE API origin")
    txline_program_id: str = Field(default="6pW64gN1s2uqjHkn1unFeEjAwJkPGHoppGvS715wyP2J", description="TxLINE Program ID")
    txline_txl_token_mint: str = Field(default="4Zao8ocPhmMgq7PdsYWyxvqySMGx7xb9cMftPMkEokRG", description="TxLINE Token Mint")
    txline_service_level_id: int = Field(default=1, description="TxLINE Service Level ID")
    txline_duration_weeks: int = Field(default=4, description="TxLINE Duration Weeks")

    # AI
    ai_deepseek_api_base: str = Field(default="https://opencode.ai/zen/v1/chat/completions", description="AI API Base")
    ai_deepseek_api_key: str = Field(..., description="AI API Key")
    ai_deepseek_model: str = Field(default="deepseek-v4-flash-free", description="AI Model")
    ai_fallback_models: str = Field(default="mimo-v2.5-free,north-mini-code-free,nemotron-3-ultra-free", description="AI Fallback Models")

    # BetEscrow
    bet_escrow_program_id: str = Field(default="vaFdYpqXffc1QXpL1AauMpvAknBNjrdZYExMQg6wvgM", description="Bet Escrow Program ID")
    bet_payment_token_mint: str = Field(default="Gh9ZwEmdLJ8DscKNTkTqPBbNwJFNjZ2DRcaaFbwVLaNc", description="Payment Token Mint")
    bet_payment_token_symbol: str = Field(default="USDC", description="Payment Token Symbol")

    # App
    app_web_port: int = Field(default=3000, description="App Web Port")
    app_log_level: str = Field(default="INFO", description="App Log Level")
    app_fixture_ids: str = Field(default="18257865,18257739", description="App Fixture IDs")
    app_debug: bool = Field(default=True, description="App Debug Mode")
    app_webhook_url: str = Field(default="https://usebantr.site", description="App Webhook URL")
    app_base_url: str = Field(default="https://usebantr.site", description="App Base URL")
    app_redis_url: str = Field(default="redis://localhost:6379", description="App Redis URL")


settings = Settings()
