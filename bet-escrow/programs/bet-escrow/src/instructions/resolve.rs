use crate::constants::*;
use crate::error::ErrorCode;
use crate::state::*;
use anchor_lang::prelude::*;
use anchor_spl::token::{Mint, Token, TokenAccount};

#[derive(Accounts)]
#[instruction(bet_id: u64, winner: Pubkey)]
pub struct ResolveBet<'info> {
    #[account(mut)]
    pub resolver: Signer<'info>,

    #[account(
        mut,
        seeds = [BET_SEED, bet_id.to_le_bytes().as_ref()],
        bump = bet.bump,
        constraint = bet.resolver_authority == resolver.key() @ ErrorCode::NotResolverAuthority,
        constraint = bet.status == BetStatus::Funded || bet.status == BetStatus::Open @ ErrorCode::BetNotFunded,
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
        associated_token::authority = winner,
    )]
    pub winner_token_account: Account<'info, TokenAccount>,

    pub stake_mint: Account<'info, Mint>,
    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<ResolveBet>, _bet_id: u64, winner: Pubkey) -> Result<()> {
    let bet = &mut ctx.accounts.bet;

    let valid_winner = bet.opponent.map_or(false, |o| winner == bet.creator || winner == o);
    require!(valid_winner, ErrorCode::InvalidWinner);

    let total_funds = bet.creator_amount.checked_add(bet.opponent_amount).unwrap();

    if total_funds > 0 {
        let bet_id_bytes = bet.bet_id.to_le_bytes();
        let seeds: &[&[u8]] = &[
            BET_SEED,
            bet_id_bytes.as_ref(),
            &[bet.bump],
        ];
        let signer_seeds = &[seeds];

        let cpi_accounts = anchor_spl::token::TransferChecked {
            from: ctx.accounts.bet_vault.to_account_info(),
            to: ctx.accounts.winner_token_account.to_account_info(),
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
            total_funds,
            ctx.accounts.stake_mint.decimals,
        )?;
    }

    bet.status = BetStatus::Resolved;
    bet.winner = Some(winner);

    msg!(
        "Bet {} resolved. Winner: {}. Payout: {}",
        bet.bet_id,
        winner,
        total_funds
    );
    Ok(())
}
