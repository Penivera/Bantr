use crate::constants::*;
use crate::error::ErrorCode;
use crate::state::*;
use anchor_lang::prelude::*;
use anchor_spl::token::{Mint, Token, TokenAccount};

#[derive(Accounts)]
#[instruction(bet_id: u64, fixture_id: String, market: u8, amount: u64, resolve_deadline: i64)]
pub struct InitializeBet<'info> {
    #[account(mut)]
    pub creator: Signer<'info>,

    pub stake_mint: Account<'info, Mint>,

    #[account(
        init,
        payer = creator,
        space = 8 + BetEscrow::INIT_SPACE,
        seeds = [BET_SEED, bet_id.to_le_bytes().as_ref()],
        bump,
    )]
    pub bet: Account<'info, BetEscrow>,

    #[account(
        init,
        payer = creator,
        seeds = [BET_VAULT_SEED, bet.key().as_ref()],
        bump,
        token::mint = stake_mint,
        token::authority = bet,
    )]
    pub bet_vault: Account<'info, TokenAccount>,

    #[account(
        mut,
        associated_token::mint = stake_mint,
        associated_token::authority = creator,
    )]
    pub creator_token_account: Account<'info, TokenAccount>,

    pub system_program: Program<'info, System>,
    pub token_program: Program<'info, Token>,
    pub rent: Sysvar<'info, Rent>,
}

pub fn handler(
    ctx: Context<InitializeBet>,
    bet_id: u64,
    fixture_id: String,
    market: u8,
    amount: u64,
    resolve_deadline: i64,
) -> Result<()> {
    let creator_amount = amount;
    let _bet_key = ctx.accounts.bet.key();

    if creator_amount > 0 {
        let cpi_accounts = anchor_spl::token::TransferChecked {
            from: ctx.accounts.creator_token_account.to_account_info(),
            to: ctx.accounts.bet_vault.to_account_info(),
            authority: ctx.accounts.creator.to_account_info(),
            mint: ctx.accounts.stake_mint.to_account_info(),
        };

        let cpi_context = CpiContext::new(
            ctx.accounts.token_program.key(),
            cpi_accounts,
        );

        anchor_spl::token::transfer_checked(
            cpi_context,
            creator_amount,
            ctx.accounts.stake_mint.decimals,
        )?;
    }

    let bet = &mut ctx.accounts.bet;
    bet.bet_id = bet_id;
    bet.creator = ctx.accounts.creator.key();
    bet.opponent = None;
    bet.stake_mint = ctx.accounts.stake_mint.key();
    bet.creator_amount = creator_amount;
    bet.opponent_amount = 0;
    bet.market = market;
    bet.fixture_id = fixture_id;
    bet.status = BetStatus::Open;
    bet.winner = None;
    bet.resolve_deadline = resolve_deadline;
    bet.resolver_authority = ctx.accounts.creator.key();
    bet.bump = ctx.bumps.bet;
    bet.vault_bump = ctx.bumps.bet_vault;

    msg!("Bet {} created by {}", bet_id, ctx.accounts.creator.key());
    Ok(())
}
