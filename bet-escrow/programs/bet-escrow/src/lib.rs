pub mod constants;
pub mod error;
pub mod instructions;
pub mod state;

use anchor_lang::prelude::*;

pub use constants::*;
#[allow(ambiguous_glob_reexports)]
pub use instructions::*;
pub use state::*;

declare_id!("vaFdYpqXffc1QXpL1AauMpvAknBNjrdZYExMQg6wvgM");

#[program]
pub mod bet_escrow {
    use super::*;

    pub fn initialize_bet(
        ctx: Context<InitializeBet>,
        bet_id: u64,
        fixture_id: String,
        market: u8,
        amount: u64,
        resolve_deadline: i64,
    ) -> Result<()> {
        initialize::handler(ctx, bet_id, fixture_id, market, amount, resolve_deadline)
    }

    pub fn join_bet(ctx: Context<JoinBet>, bet_id: u64) -> Result<()> {
        join::handler(ctx, bet_id)
    }

    pub fn resolve_bet(ctx: Context<ResolveBet>, bet_id: u64, winner: Pubkey) -> Result<()> {
        resolve::handler(ctx, bet_id, winner)
    }

    pub fn refund_expired(ctx: Context<RefundExpired>, bet_id: u64) -> Result<()> {
        refund::handler(ctx, bet_id)
    }

    pub fn cancel_bet(ctx: Context<CancelBet>, bet_id: u64) -> Result<()> {
        cancel::handler(ctx, bet_id)
    }
}
