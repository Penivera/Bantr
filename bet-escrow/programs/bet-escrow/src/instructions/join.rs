use crate::constants::*;
use crate::error::ErrorCode;
use crate::state::*;
use anchor_lang::prelude::*;
use anchor_spl::token::{Mint, Token, TokenAccount};

#[derive(Accounts)]
#[instruction(bet_id: u64)]
pub struct JoinBet<'info> {
    #[account(mut)]
    pub opponent: Signer<'info>,

    #[account(
        mut,
        seeds = [BET_SEED, bet_id.to_le_bytes().as_ref()],
        bump = bet.bump,
        constraint = bet.status == BetStatus::Open @ ErrorCode::BetNotOpen,
    )]
    pub bet: Account<'info, BetEscrow>,

    #[account(
        mut,
        seeds = [BET_VAULT_SEED, bet.key().as_ref()],
        bump = bet.vault_bump,
    )]
    pub bet_vault: Account<'info, TokenAccount>,

    #[account(
        mut,
        associated_token::mint = stake_mint,
        associated_token::authority = opponent,
    )]
    pub opponent_token_account: Account<'info, TokenAccount>,

    pub stake_mint: Account<'info, Mint>,

    pub system_program: Program<'info, System>,
    pub token_program: Program<'info, Token>,
    pub rent: Sysvar<'info, Rent>,
}

pub fn handler(ctx: Context<JoinBet>, _bet_id: u64) -> Result<()> {
    let bet = &mut ctx.accounts.bet;

    require!(bet.opponent.is_none(), ErrorCode::AlreadyJoined);

    let opponent_amount = bet.creator_amount;

    let cpi_accounts = anchor_spl::token::TransferChecked {
        from: ctx.accounts.opponent_token_account.to_account_info(),
        to: ctx.accounts.bet_vault.to_account_info(),
        authority: ctx.accounts.opponent.to_account_info(),
        mint: ctx.accounts.stake_mint.to_account_info(),
    };

    let cpi_context = CpiContext::new(
        ctx.accounts.token_program.key(),
        cpi_accounts,
    );

    anchor_spl::token::transfer_checked(
        cpi_context,
        opponent_amount,
        ctx.accounts.stake_mint.decimals,
    )?;

    bet.opponent = Some(ctx.accounts.opponent.key());
    bet.opponent_amount = opponent_amount;
    bet.status = BetStatus::Funded;

    msg!(
        "Bet {} joined by {}. Status: Funded",
        bet.bet_id,
        ctx.accounts.opponent.key()
    );
    Ok(())
}
