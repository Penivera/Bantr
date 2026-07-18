# BanterBot

Any Telegram watch-party group becomes a stakes room. `/bet @rival next_goal 50` posts a public callout; TxLINE's live World Cup feed resolves it the moment the event happens; the bot settles bragging rights (and optionally real stakes) automatically, citing an on-chain data reference so the result is provably fair.

**Track:** Consumer & Fan Experiences — TxODDS World Cup Hackathon (Superteam Earn)
**Stack:** Python 3.12+, FastAPI, Anchor (Rust), TxLINE API, python-telegram-bot, Solana Pay

---

## Architecture

```
Telegram group chat
      |  /fixtures  /track  /bet  /call  /leaderboard  NL text
      v
Telegram Bot (python-telegram-bot)
      |
      +-- BetEngine (resolution wiring + BetStore)
      |       |
      |       +-- TxLINE SSE stream (live scores)
      |       +-- NLU parser (DeepSeek V4 Flash Free)
      |       +-- Provenance (on-chain proofs)
      |
      +-- SolanaPayService (transaction requests + PDA watcher)
      |
      v
Chat message: result + leaderboard + on-chain proof reference
```

---

## Quickstart

```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install deps and run
uv sync
cp .env.example .env
# Edit .env with TELEGRAM_BOT_TOKEN and SOLANA_WALLET_SECRET_KEY
uv run app/main.py
```

## Env

| Variable | Required | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token from @BotFather |
| `SOLANA_WALLET_SECRET_KEY` | Yes | JSON-encoded Solana keypair (funded with ~0.05 devnet SOL) |
| `APP_WEB_PORT` | No | Web dashboard port (default: 3000) |
| `AI_DEEPSEEK_API_KEY` | No | DeepSeek API key (free tier embedded) |
| `BET_ESCROW_PROGRAM_ID` | No | Anchor program ID |

## Commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/fixtures` | List available upcoming matches |
| `/track <id>` | Set active fixture for betting |
| `/bet @user <market> <amount>` | Challenge someone (markets: next_goal, next_card, next_corner) |
| `/call <betId>` | Accept a bet |
| `/leaderboard` | See rankings |
| Natural language | AI-powered: "I bet @alice 50 on next goal", "show me matches" |

## Project structure

```
app/
  core/           config, logging, security, exceptions, constants, dependencies
  services/
    txline/       auth (credential bootstrap), stream (SSE), provenance (proofs)
    telegram/     bot handlers + NLU integration
    payments/     Solana Pay transaction requests + PDA watcher
    nlu/          DeepSeek V4 Flash Free intent parser
    betting/      BetStore + BetEngine (resolution)
  api/routes/     FastAPI dashboard
  main.py         Entry point
bet-escrow/       Anchor escrow program (Rust)
```
