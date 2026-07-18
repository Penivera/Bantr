use {
    anchor_lang::{
        prelude::{Pubkey, Rent, sysvar::SysvarId},
        solana_program::{instruction::Instruction, system_instruction, system_program},
        AccountDeserialize, InstructionData, ToAccountMetas,
    },
    litesvm::LiteSVM,
    solana_keypair::Keypair,
    solana_message::{Message, VersionedMessage},
    solana_signer::Signer,
    solana_transaction::versioned::VersionedTransaction,
    bet_escrow::state::*,
};

fn setup_mint(svm: &mut LiteSVM, payer: &Keypair, mint: &Keypair, authority: &Pubkey) {
    let rent = svm.minimum_balance_for_rent_exemption(82);
    let create_idx = system_instruction::create_account(
        &payer.pubkey(),
        &mint.pubkey(),
        rent,
        82,
        &anchor_spl::token::ID,
    );
    let blockhash = svm.latest_blockhash();
    let msg = Message::new_with_blockhash(&[create_idx], Some(&payer.pubkey()), &blockhash);
    let tx = VersionedTransaction::try_new(VersionedMessage::Legacy(msg), &[payer, mint]).unwrap();
    svm.send_transaction(tx).unwrap();

    let init_mint_idx = anchor_spl::token::spl_token::instruction::initialize_mint(
        &anchor_spl::token::ID,
        &mint.pubkey(),
        authority,
        None,
        6,
    ).unwrap();
    let blockhash = svm.latest_blockhash();
    let msg = Message::new_with_blockhash(&[init_mint_idx], Some(&payer.pubkey()), &blockhash);
    let tx = VersionedTransaction::try_new(VersionedMessage::Legacy(msg), &[payer]).unwrap();
    svm.send_transaction(tx).unwrap();
}

fn setup_token_account(svm: &mut LiteSVM, payer: &Keypair, owner: &Pubkey, mint: &Pubkey) -> Pubkey {
    let ata = anchor_spl::associated_token::get_associated_token_address(owner, mint);
    let create_ata_idx = anchor_spl::associated_token::spl_associated_token_account::instruction::create_associated_token_account(
        &payer.pubkey(),
        owner,
        mint,
        &anchor_spl::token::ID,
    );
    let blockhash = svm.latest_blockhash();
    let msg = Message::new_with_blockhash(&[create_ata_idx], Some(&payer.pubkey()), &blockhash);
    let tx = VersionedTransaction::try_new(VersionedMessage::Legacy(msg), &[payer]).unwrap();
    svm.send_transaction(tx).unwrap();
    ata
}

fn mint_to(svm: &mut LiteSVM, payer: &Keypair, mint: &Pubkey, mint_authority: &Keypair, recipient: &Pubkey, amount: u64) {
    let mint_to_idx = anchor_spl::token::spl_token::instruction::mint_to(
        &anchor_spl::token::ID,
        mint,
        recipient,
        &mint_authority.pubkey(),
        &[],
        amount,
    ).unwrap();
    let blockhash = svm.latest_blockhash();
    let msg = Message::new_with_blockhash(&[mint_to_idx], Some(&payer.pubkey()), &blockhash);
    let tx = if payer.pubkey() == mint_authority.pubkey() {
        VersionedTransaction::try_new(VersionedMessage::Legacy(msg), &[payer]).unwrap()
    } else {
        VersionedTransaction::try_new(VersionedMessage::Legacy(msg), &[payer, mint_authority]).unwrap()
    };
    svm.send_transaction(tx).unwrap();
}

fn setup_svm() -> (LiteSVM, Pubkey, Keypair) {
    let program_id = bet_escrow::id();
    let mut svm = LiteSVM::new();
    let bytes = include_bytes!(concat!(
        env!("CARGO_TARGET_TMPDIR"),
        "/../deploy/bet_escrow.so"
    ));
    svm.add_program(program_id, bytes).unwrap();
    let payer = Keypair::new();
    svm.airdrop(&payer.pubkey(), 10_000_000_000).unwrap();
    (svm, program_id, payer)
}

fn derive_bet_pda(program_id: &Pubkey, bet_id: u64) -> Pubkey {
    Pubkey::find_program_address(
        &[bet_escrow::constants::BET_SEED, &bet_id.to_le_bytes()],
        program_id,
    ).0
}

fn derive_vault_pda(program_id: &Pubkey, bet_pda: &Pubkey) -> Pubkey {
    Pubkey::find_program_address(
        &[bet_escrow::constants::BET_VAULT_SEED, bet_pda.as_ref()],
        program_id,
    ).0
}

// --- Test 1: Full happy path ---
#[test]
fn test_happy_path() {
    let (mut svm, program_id, admin) = setup_svm();

    let mint = Keypair::new();
    setup_mint(&mut svm, &admin, &mint, &admin.pubkey());

    let creator = Keypair::new();
    svm.airdrop(&creator.pubkey(), 1_000_000_000).unwrap();
    let creator_ata = setup_token_account(&mut svm, &admin, &creator.pubkey(), &mint.pubkey());
    mint_to(&mut svm, &admin, &mint.pubkey(), &admin, &creator_ata, 1000);

    let opponent = Keypair::new();
    svm.airdrop(&opponent.pubkey(), 1_000_000_000).unwrap();
    let opponent_ata = setup_token_account(&mut svm, &admin, &opponent.pubkey(), &mint.pubkey());
    mint_to(&mut svm, &admin, &mint.pubkey(), &admin, &opponent_ata, 1000);

    let bet_id: u64 = 1;
    let amount: u64 = 100;
    let deadline = 9999999999i64;

    let bet_pda = derive_bet_pda(&program_id, bet_id);
    let vault_pda = derive_vault_pda(&program_id, &bet_pda);

    // 1. initialize_bet
    let init_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::InitializeBet {
            bet_id,
            fixture_id: "18257865".to_string(),
            market: 1,
            amount,
            resolve_deadline: deadline,
        }.data(),
        bet_escrow::accounts::InitializeBet {
            creator: creator.pubkey(),
            stake_mint: mint.pubkey(),
            bet: bet_pda,
            bet_vault: vault_pda,
            creator_token_account: creator_ata,
            system_program: system_program::ID,
            token_program: anchor_spl::token::ID,
            rent: Rent::id(),
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[init_ix], Some(&creator.pubkey()), &svm.latest_blockhash())),
        &[&creator],
    ).unwrap();
    svm.send_transaction(tx).unwrap();

    let bet_acc = svm.get_account(&bet_pda).unwrap();
    let bet = BetEscrow::try_deserialize(&mut &bet_acc.data[..]).unwrap();
    assert_eq!(bet.status, BetStatus::Open);
    assert_eq!(bet.creator, creator.pubkey());
    assert_eq!(bet.creator_amount, amount);
    assert_eq!(bet.opponent_amount, 0);

    // Verify creator balance: 1000 - 100 = 900
    let creator_bal = svm.get_account(&creator_ata).unwrap();
    let creator_ata_data = anchor_spl::token::TokenAccount::try_deserialize(&mut &creator_bal.data[..]).unwrap();
    assert_eq!(creator_ata_data.amount, 900);

    // Verify vault: 100
    let vault_bal = svm.get_account(&vault_pda).unwrap();
    let vault_data = anchor_spl::token::TokenAccount::try_deserialize(&mut &vault_bal.data[..]).unwrap();
    assert_eq!(vault_data.amount, amount);

    // 2. join_bet
    let join_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::JoinBet { bet_id }.data(),
        bet_escrow::accounts::JoinBet {
            opponent: opponent.pubkey(),
            bet: bet_pda,
            bet_vault: vault_pda,
            opponent_token_account: opponent_ata,
            stake_mint: mint.pubkey(),
            system_program: system_program::ID,
            token_program: anchor_spl::token::ID,
            rent: Rent::id(),
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[join_ix], Some(&opponent.pubkey()), &svm.latest_blockhash())),
        &[&opponent],
    ).unwrap();
    svm.send_transaction(tx).unwrap();

    let bet_acc = svm.get_account(&bet_pda).unwrap();
    let bet = BetEscrow::try_deserialize(&mut &bet_acc.data[..]).unwrap();
    assert_eq!(bet.status, BetStatus::Funded);
    assert_eq!(bet.opponent, Some(opponent.pubkey()));
    assert_eq!(bet.opponent_amount, amount);

    // Verify opponent balance: 1000 - 100 = 900
    let opp_bal = svm.get_account(&opponent_ata).unwrap();
    let opp_ata_data = anchor_spl::token::TokenAccount::try_deserialize(&mut &opp_bal.data[..]).unwrap();
    assert_eq!(opp_ata_data.amount, 900);

    // Verify vault: 200 (both stakes)
    let vault_bal = svm.get_account(&vault_pda).unwrap();
    let vault_data = anchor_spl::token::TokenAccount::try_deserialize(&mut &vault_bal.data[..]).unwrap();
    assert_eq!(vault_data.amount, 200);

    // 3. resolve_bet (creator wins)
    let resolve_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::ResolveBet {
            bet_id,
            winner: creator.pubkey(),
        }.data(),
        bet_escrow::accounts::ResolveBet {
            resolver: creator.pubkey(),
            bet: bet_pda,
            bet_vault: vault_pda,
            winner_token_account: creator_ata,
            stake_mint: mint.pubkey(),
            token_program: anchor_spl::token::ID,
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[resolve_ix], Some(&creator.pubkey()), &svm.latest_blockhash())),
        &[&creator],
    ).unwrap();
    svm.send_transaction(tx).unwrap();

    let bet_acc = svm.get_account(&bet_pda).unwrap();
    let bet = BetEscrow::try_deserialize(&mut &bet_acc.data[..]).unwrap();
    assert_eq!(bet.status, BetStatus::Resolved);
    assert_eq!(bet.winner, Some(creator.pubkey()));

    // Creator gets full 200 back: 900 + 200 = 1100
    let creator_bal = svm.get_account(&creator_ata).unwrap();
    let creator_ata_data = anchor_spl::token::TokenAccount::try_deserialize(&mut &creator_bal.data[..]).unwrap();
    assert_eq!(creator_ata_data.amount, 1100);

    // Vault should be 0
    let vault_bal = svm.get_account(&vault_pda).unwrap();
    let vault_data = anchor_spl::token::TokenAccount::try_deserialize(&mut &vault_bal.data[..]).unwrap();
    assert_eq!(vault_data.amount, 0);
}

// --- Test 2: Resolve by non-authority (must fail) ---
#[test]
fn test_resolve_by_non_authority() {
    let (mut svm, program_id, admin) = setup_svm();

    let mint = Keypair::new();
    setup_mint(&mut svm, &admin, &mint, &admin.pubkey());

    let creator = Keypair::new();
    svm.airdrop(&creator.pubkey(), 1_000_000_000).unwrap();
    let creator_ata = setup_token_account(&mut svm, &admin, &creator.pubkey(), &mint.pubkey());
    mint_to(&mut svm, &admin, &mint.pubkey(), &admin, &creator_ata, 1000);

    let attacker = Keypair::new();
    svm.airdrop(&attacker.pubkey(), 1_000_000_000).unwrap();
    let attacker_ata = setup_token_account(&mut svm, &admin, &attacker.pubkey(), &mint.pubkey());
    mint_to(&mut svm, &admin, &mint.pubkey(), &admin, &attacker_ata, 100);

    let bet_id: u64 = 10;
    let bet_pda = derive_bet_pda(&program_id, bet_id);
    let vault_pda = derive_vault_pda(&program_id, &bet_pda);

    let init_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::InitializeBet {
            bet_id,
            fixture_id: "test".to_string(),
            market: 1,
            amount: 50,
            resolve_deadline: 9999999999i64,
        }.data(),
        bet_escrow::accounts::InitializeBet {
            creator: creator.pubkey(),
            stake_mint: mint.pubkey(),
            bet: bet_pda,
            bet_vault: vault_pda,
            creator_token_account: creator_ata,
            system_program: system_program::ID,
            token_program: anchor_spl::token::ID,
            rent: Rent::id(),
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[init_ix], Some(&creator.pubkey()), &svm.latest_blockhash())),
        &[&creator],
    ).unwrap();
    svm.send_transaction(tx).unwrap();

    // Attacker tries to resolve (original creator is resolver_authority)
    let resolve_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::ResolveBet {
            bet_id,
            winner: attacker.pubkey(),
        }.data(),
        bet_escrow::accounts::ResolveBet {
            resolver: attacker.pubkey(),
            bet: bet_pda,
            bet_vault: vault_pda,
            winner_token_account: attacker_ata,
            stake_mint: mint.pubkey(),
            token_program: anchor_spl::token::ID,
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[resolve_ix], Some(&attacker.pubkey()), &svm.latest_blockhash())),
        &[&attacker],
    ).unwrap();
    assert!(svm.send_transaction(tx).is_err());

    // Status must remain Open
    let bet_acc = svm.get_account(&bet_pda).unwrap();
    let bet = BetEscrow::try_deserialize(&mut &bet_acc.data[..]).unwrap();
    assert_eq!(bet.status, BetStatus::Open);
}

// --- Test 3: Refund before deadline (must fail) ---
#[test]
fn test_refund_before_deadline() {
    let (mut svm, program_id, admin) = setup_svm();

    let mint = Keypair::new();
    setup_mint(&mut svm, &admin, &mint, &admin.pubkey());

    let creator = Keypair::new();
    svm.airdrop(&creator.pubkey(), 1_000_000_000).unwrap();
    let creator_ata = setup_token_account(&mut svm, &admin, &creator.pubkey(), &mint.pubkey());
    mint_to(&mut svm, &admin, &mint.pubkey(), &admin, &creator_ata, 1000);

    let bet_id: u64 = 20;
    let bet_pda = derive_bet_pda(&program_id, bet_id);
    let vault_pda = derive_vault_pda(&program_id, &bet_pda);

    let init_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::InitializeBet {
            bet_id,
            fixture_id: "test".to_string(),
            market: 1,
            amount: 50,
            resolve_deadline: 9999999999i64, // far future
        }.data(),
        bet_escrow::accounts::InitializeBet {
            creator: creator.pubkey(),
            stake_mint: mint.pubkey(),
            bet: bet_pda,
            bet_vault: vault_pda,
            creator_token_account: creator_ata,
            system_program: system_program::ID,
            token_program: anchor_spl::token::ID,
            rent: Rent::id(),
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[init_ix], Some(&creator.pubkey()), &svm.latest_blockhash())),
        &[&creator],
    ).unwrap();
    svm.send_transaction(tx).unwrap();

    // Try refund - deadline hasn't passed (current clock time is small)
    let refund_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::RefundExpired { bet_id }.data(),
        bet_escrow::accounts::RefundExpired {
            caller: creator.pubkey(),
            bet: bet_pda,
            bet_vault: vault_pda,
            creator_token_account: creator_ata,
            opponent_token_account: creator_ata, // dummy - same for test
            creator_token_owner: creator.pubkey(),
            opponent_token_owner: creator.pubkey(),
            stake_mint: mint.pubkey(),
            token_program: anchor_spl::token::ID,
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[refund_ix], Some(&creator.pubkey()), &svm.latest_blockhash())),
        &[&creator],
    ).unwrap();
    assert!(svm.send_transaction(tx).is_err());

    // Status must remain Open
    let bet_acc = svm.get_account(&bet_pda).unwrap();
    let bet = BetEscrow::try_deserialize(&mut &bet_acc.data[..]).unwrap();
    assert_eq!(bet.status, BetStatus::Open);
}

// --- Test 4: Refund after deadline (must succeed) ---
#[test]
fn test_refund_after_deadline() {
    let (mut svm, program_id, admin) = setup_svm();

    let mint = Keypair::new();
    setup_mint(&mut svm, &admin, &mint, &admin.pubkey());

    let creator = Keypair::new();
    svm.airdrop(&creator.pubkey(), 1_000_000_000).unwrap();
    let creator_ata = setup_token_account(&mut svm, &admin, &creator.pubkey(), &mint.pubkey());
    mint_to(&mut svm, &admin, &mint.pubkey(), &admin, &creator_ata, 1000);

    let opponent = Keypair::new();
    svm.airdrop(&opponent.pubkey(), 1_000_000_000).unwrap();
    let opponent_ata = setup_token_account(&mut svm, &admin, &opponent.pubkey(), &mint.pubkey());
    mint_to(&mut svm, &admin, &mint.pubkey(), &admin, &opponent_ata, 1000);

    let bet_id: u64 = 30;
    let bet_pda = derive_bet_pda(&program_id, bet_id);
    let vault_pda = derive_vault_pda(&program_id, &bet_pda);

    // Use deadline = 0 (immediately expired in LiteSVM, clock starts at 0)
    let init_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::InitializeBet {
            bet_id,
            fixture_id: "test".to_string(),
            market: 1,
            amount: 50,
            resolve_deadline: 0,
        }.data(),
        bet_escrow::accounts::InitializeBet {
            creator: creator.pubkey(),
            stake_mint: mint.pubkey(),
            bet: bet_pda,
            bet_vault: vault_pda,
            creator_token_account: creator_ata,
            system_program: system_program::ID,
            token_program: anchor_spl::token::ID,
            rent: Rent::id(),
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[init_ix], Some(&creator.pubkey()), &svm.latest_blockhash())),
        &[&creator],
    ).unwrap();
    svm.send_transaction(tx).unwrap();

    // Join
    let join_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::JoinBet { bet_id }.data(),
        bet_escrow::accounts::JoinBet {
            opponent: opponent.pubkey(),
            bet: bet_pda,
            bet_vault: vault_pda,
            opponent_token_account: opponent_ata,
            stake_mint: mint.pubkey(),
            system_program: system_program::ID,
            token_program: anchor_spl::token::ID,
            rent: Rent::id(),
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[join_ix], Some(&opponent.pubkey()), &svm.latest_blockhash())),
        &[&opponent],
    ).unwrap();
    svm.send_transaction(tx).unwrap();

    let bet_acc = svm.get_account(&bet_pda).unwrap();
    let bet = BetEscrow::try_deserialize(&mut &bet_acc.data[..]).unwrap();
    assert_eq!(bet.status, BetStatus::Funded);

    // Creator balance before refund: 1000 - 50 = 950
    let creator_bal = svm.get_account(&creator_ata).unwrap();
    let c = anchor_spl::token::TokenAccount::try_deserialize(&mut &creator_bal.data[..]).unwrap();
    assert_eq!(c.amount, 950);

    // Refund
    let refund_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::RefundExpired { bet_id }.data(),
        bet_escrow::accounts::RefundExpired {
            caller: admin.pubkey(), // anyone can call refund
            bet: bet_pda,
            bet_vault: vault_pda,
            creator_token_account: creator_ata,
            opponent_token_account: opponent_ata,
            creator_token_owner: creator.pubkey(),
            opponent_token_owner: opponent.pubkey(),
            stake_mint: mint.pubkey(),
            token_program: anchor_spl::token::ID,
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[refund_ix], Some(&admin.pubkey()), &svm.latest_blockhash())),
        &[&admin],
    ).unwrap();
    svm.send_transaction(tx).unwrap();

    // Status: Refunded
    let bet_acc = svm.get_account(&bet_pda).unwrap();
    let bet = BetEscrow::try_deserialize(&mut &bet_acc.data[..]).unwrap();
    assert_eq!(bet.status, BetStatus::Refunded);

    // Creator gets their 50 back: 950 + 50 = 1000
    let creator_bal = svm.get_account(&creator_ata).unwrap();
    let c = anchor_spl::token::TokenAccount::try_deserialize(&mut &creator_bal.data[..]).unwrap();
    assert_eq!(c.amount, 1000);

    // Opponent gets their 50 back: 1000 - 50 + 50 = 1000
    let opp_bal = svm.get_account(&opponent_ata).unwrap();
    let o = anchor_spl::token::TokenAccount::try_deserialize(&mut &opp_bal.data[..]).unwrap();
    assert_eq!(o.amount, 1000);

    // Vault empty
    let vault_bal = svm.get_account(&vault_pda).unwrap();
    let v = anchor_spl::token::TokenAccount::try_deserialize(&mut &vault_bal.data[..]).unwrap();
    assert_eq!(v.amount, 0);
}

// --- Test 5: Double join (must fail) ---
#[test]
fn test_double_join() {
    let (mut svm, program_id, admin) = setup_svm();

    let mint = Keypair::new();
    setup_mint(&mut svm, &admin, &mint, &admin.pubkey());

    let creator = Keypair::new();
    svm.airdrop(&creator.pubkey(), 1_000_000_000).unwrap();
    let creator_ata = setup_token_account(&mut svm, &admin, &creator.pubkey(), &mint.pubkey());
    mint_to(&mut svm, &admin, &mint.pubkey(), &admin, &creator_ata, 1000);

    let opponent = Keypair::new();
    svm.airdrop(&opponent.pubkey(), 1_000_000_000).unwrap();
    let opponent_ata = setup_token_account(&mut svm, &admin, &opponent.pubkey(), &mint.pubkey());
    mint_to(&mut svm, &admin, &mint.pubkey(), &admin, &opponent_ata, 1000);

    let opponent2 = Keypair::new();
    svm.airdrop(&opponent2.pubkey(), 1_000_000_000).unwrap();
    let opponent2_ata = setup_token_account(&mut svm, &admin, &opponent2.pubkey(), &mint.pubkey());
    mint_to(&mut svm, &admin, &mint.pubkey(), &admin, &opponent2_ata, 1000);

    let bet_id: u64 = 40;
    let bet_pda = derive_bet_pda(&program_id, bet_id);
    let vault_pda = derive_vault_pda(&program_id, &bet_pda);

    let init_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::InitializeBet {
            bet_id,
            fixture_id: "test".to_string(),
            market: 1,
            amount: 50,
            resolve_deadline: 9999999999i64,
        }.data(),
        bet_escrow::accounts::InitializeBet {
            creator: creator.pubkey(),
            stake_mint: mint.pubkey(),
            bet: bet_pda,
            bet_vault: vault_pda,
            creator_token_account: creator_ata,
            system_program: system_program::ID,
            token_program: anchor_spl::token::ID,
            rent: Rent::id(),
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[init_ix], Some(&creator.pubkey()), &svm.latest_blockhash())),
        &[&creator],
    ).unwrap();
    svm.send_transaction(tx).unwrap();

    // First join succeeds
    let join_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::JoinBet { bet_id }.data(),
        bet_escrow::accounts::JoinBet {
            opponent: opponent.pubkey(),
            bet: bet_pda,
            bet_vault: vault_pda,
            opponent_token_account: opponent_ata,
            stake_mint: mint.pubkey(),
            system_program: system_program::ID,
            token_program: anchor_spl::token::ID,
            rent: Rent::id(),
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[join_ix], Some(&opponent.pubkey()), &svm.latest_blockhash())),
        &[&opponent],
    ).unwrap();
    svm.send_transaction(tx).unwrap();

    let bet_acc = svm.get_account(&bet_pda).unwrap();
    let bet = BetEscrow::try_deserialize(&mut &bet_acc.data[..]).unwrap();
    assert_eq!(bet.status, BetStatus::Funded);
    assert_eq!(bet.opponent, Some(opponent.pubkey()));

    // Second join MUST FAIL (AlreadyJoined)
    let join2_ix = Instruction::new_with_bytes(
        program_id,
        &bet_escrow::instruction::JoinBet { bet_id }.data(),
        bet_escrow::accounts::JoinBet {
            opponent: opponent2.pubkey(),
            bet: bet_pda,
            bet_vault: vault_pda,
            opponent_token_account: opponent2_ata,
            stake_mint: mint.pubkey(),
            system_program: system_program::ID,
            token_program: anchor_spl::token::ID,
            rent: Rent::id(),
        }.to_account_metas(None),
    );
    let tx = VersionedTransaction::try_new(
        VersionedMessage::Legacy(Message::new_with_blockhash(&[join2_ix], Some(&opponent2.pubkey()), &svm.latest_blockhash())),
        &[&opponent2],
    ).unwrap();
    assert!(svm.send_transaction(tx).is_err());

    // Status must still be Funded, opponent unchanged
    let bet_acc = svm.get_account(&bet_pda).unwrap();
    let bet = BetEscrow::try_deserialize(&mut &bet_acc.data[..]).unwrap();
    assert_eq!(bet.status, BetStatus::Funded);
    assert_eq!(bet.opponent, Some(opponent.pubkey()));

    // Opponent2 should still have all their tokens
    let opp2_bal = svm.get_account(&opponent2_ata).unwrap();
    let o2 = anchor_spl::token::TokenAccount::try_deserialize(&mut &opp2_bal.data[..]).unwrap();
    assert_eq!(o2.amount, 1000);
}
