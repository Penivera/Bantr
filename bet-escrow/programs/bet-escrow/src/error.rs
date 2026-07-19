use anchor_lang::prelude::*;

#[error_code]
pub enum ErrorCode {
    #[msg("Bet is not in Open status")]
    BetNotOpen,
    #[msg("Bet is not in Funded status")]
    BetNotFunded,
    #[msg("Bet is already resolved")]
    AlreadyResolved,
    #[msg("Only the resolver authority can resolve the bet")]
    NotResolverAuthority,
    #[msg("Winner must be either creator or opponent")]
    InvalidWinner,
    #[msg("Resolve deadline has not passed")]
    DeadlineNotPassed,
    #[msg("Only the opponent can join the bet")]
    NotOpponent,
    #[msg("Opponent has already joined")]
    AlreadyJoined,
    #[msg("Opponent must match the configured opponent")]
    OpponentMismatch,
    #[msg("Opponent stake must match creator stake")]
    StakeMismatch,
    #[msg("Only the bet creator can perform this action")]
    NotCreator,
}
