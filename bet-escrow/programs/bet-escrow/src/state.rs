use anchor_lang::prelude::*;

#[derive(Debug, Clone, PartialEq, AnchorSerialize, AnchorDeserialize, InitSpace)]
pub enum BetStatus {
    Open,
    Funded,
    Resolved,
    Refunded,
}

#[account]
#[derive(InitSpace)]
pub struct BetEscrow {
    pub bet_id: u64,
    pub creator: Pubkey,
    pub opponent: Option<Pubkey>,
    pub stake_mint: Pubkey,
    pub creator_amount: u64,
    pub opponent_amount: u64,
    pub market: u8,
    #[max_len(12)]
    pub fixture_id: String,
    pub status: BetStatus,
    pub winner: Option<Pubkey>,
    pub resolve_deadline: i64,
    pub resolver_authority: Pubkey,
    pub bump: u8,
    pub vault_bump: u8,
}
