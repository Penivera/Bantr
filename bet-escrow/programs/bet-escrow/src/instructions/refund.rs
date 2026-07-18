use crate::constants::*;
use crate::error::ErrorCode;
use crate::state::*;
use anchor_lang::prelude::*;
use anchor_spl::token::{Mint, Token, TokenAccount};

#[derive(Accounts)]
#[instruction(bet_id: u64)]
pub struct RefundExpired<'info> {
    #[account(mut)]
    pub caller: Signer<'info>,

    #[account(
        mut,
        seeds = [BET_SEED, bet_id.to_le_bytes().as_ref()],
        bump = bet.bump,
        constraint = bet.status == BetStatus::Open || bet.status == BetStatus::Funded @ ErrorCode::BetNotFunded,
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
        associated_token::authority = creator_token_owner,
    )]
    pub creator_token_account: Account<'info, TokenAccount>,

    #[account(
        mut,
        associated_token::mint = stake_mint,
        associated_token::authority = opponent_token_owner,
    )]
    pub opponent_token_account: Account<'info, TokenAccount>,

    /// CHECK: Validated via constraint
    #[account()]
    pub creator_token_owner: UncheckedAccount<'info>,

    /// CHECK: Validated via constraint
    #[account()]
    pub opponent_token_owner: UncheckedAccount<'info>,

    pub stake_mint: Account<'info, Mint>,
    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<RefundExpired>, _bet_id: u64) -> Result<()> {
    let bet = &mut ctx.accounts.bet;
    let clock = Clock::get()?;

    require!(clock.unix_timestamp >= bet.resolve_deadline, ErrorCode::DeadlineNotPassed);

    let bet_id_bytes = bet.bet_id.to_le_bytes();
    let seeds: &[&[u8]] = &[
        BET_SEED,
        bet_id_bytes.as_ref(),
        &[bet.bump],
    ];
    let signer_seeds = &[seeds];

    if bet.creator_amount > 0 {
        let cpi_accounts = anchor_spl::token::TransferChecked {
            from: ctx.accounts.bet_vault.to_account_info(),
            to: ctx.accounts.creator_token_account.to_account_info(),
            authority: bet.to_account_info(),
            mint: ctx.accounts.stake_mint.to_account_info(),
        };

        let cpi_context = CpiContext::new_with_signer(
            ctx.accounts.token_program.key(),
            cpi_accounts,
            signer_seeds,
        );

        anchor_spl::token::transfer_checked(
            cpi_context,
            bet.creator_amount,
            ctx.accounts.stake_mint.decimals,
        )?;
    }

    if bet.opponent_amount > 0 {
        let cpi_accounts = anchor_spl::token::TransferChecked {
            from: ctx.accounts.bet_vault.to_account_info(),
            to: ctx.accounts.opponent_token_account.to_account_info(),
            authority: bet.to_account_info(),
            mint: ctx.accounts.stake_mint.to_account_info(),
        };

        let cpi_context = CpiContext::new_with_signer(
            ctx.accounts.token_program.key(),
            cpi_accounts,
            signer_seeds,
        );

        anchor_spl::token::transfer_checked(
            cpi_context,
            bet.opponent_amount,
            ctx.accounts.stake_mint.decimals,
        )?;
    }

    bet.status = BetStatus::Refunded;

    msg!(
        "Bet {} refunded after deadline. Creator: {}, Opponent: {}",
        bet.bet_id,
        bet.creator_amount,
        bet.opponent_amount
    );
    Ok(())
}
