import { useMemo, useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ConnectionProvider, WalletProvider } from '@solana/wallet-adapter-react';
import { WalletModalProvider, WalletMultiButton } from '@solana/wallet-adapter-react-ui';
import { PhantomWalletAdapter, SolflareWalletAdapter } from '@solana/wallet-adapter-wallets';
import { useConnection, useWallet } from '@solana/wallet-adapter-react';
import { Transaction, PublicKey } from '@solana/web3.js';
import { clusterApiUrl } from '@solana/web3.js';

import '@solana/wallet-adapter-react-ui/styles.css';

interface RefundInfo {
  payment_id: string;
  bet_id: string;
  amount: number;
  token_symbol: string;
  token_mint: string;
  status: string;
  eligible: boolean;
  reason: string;
  chain_status: string | null;
  creator_wallet: string | null;
  instruction: string;
}

function RefundContent({ refundId }: { refundId: string }) {
  const { connection } = useConnection();
  const { publicKey, signTransaction, connected } = useWallet();
  const [refund, setRefund] = useState<RefundInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [claiming, setClaiming] = useState(false);
  const [done, setDone] = useState(false);
  const [txSig, setTxSig] = useState('');

  useEffect(() => {
    if (!refundId) { setError('No refund ID'); setLoading(false); return; }
    fetch(`/api/refunds/${refundId}`)
      .then(r => { if (!r.ok) throw new Error('Refund not found'); return r.json(); })
      .then(d => { setRefund(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [refundId]);

  const handleClaim = useCallback(async () => {
    if (!publicKey || !signTransaction || !refund) return;
    setClaiming(true); setError('');
    try {
      const params = new URLSearchParams({
        bet_id: refund.bet_id, amount: String(refund.amount),
        tokenMint: refund.token_mint, tokenSymbol: refund.token_symbol,
        instruction: refund.instruction || 'cancel_bet', fixture_id: '0', market: '1',
        resolve_deadline: '0', programId: '',
      });
      const resp = await fetch(`/api/pay?${params}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account: publicKey.toBase58() }),
      });
      if (!resp.ok) throw new Error('Failed to build refund transaction');
      const { transaction: txBase64 } = await resp.json();

      const tx = Transaction.from(Buffer.from(txBase64, 'base64'));
      tx.feePayer = publicKey;
      const { blockhash } = await connection.getLatestBlockhash('confirmed');
      tx.recentBlockhash = blockhash;

      const signed = await signTransaction(tx);
      const sig = await connection.sendRawTransaction(signed.serialize(), { skipPreflight: true });
      await connection.confirmTransaction(sig, 'confirmed');

      const claimResp = await fetch(`/api/refunds/${refund.payment_id}/claim`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tx_signature: sig, payer_wallet: publicKey.toBase58() }),
      });
      if (!claimResp.ok) throw new Error('Refund verification failed');

      setTxSig(sig); setDone(true);
    } catch (e: any) {
      setError(e.message || 'Refund failed');
    } finally {
      setClaiming(false);
    }
  }, [publicKey, signTransaction, refund, connection]);

  if (loading) return <Card><p style={{ textAlign: 'center', color: '#9ca3af' }}>Loading refund...</p></Card>;
  if (error && !refund) return <Card><p style={{ textAlign: 'center', color: '#ef4444' }}>{error}</p></Card>;
  if (done) return (
    <Card>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '48px', marginBottom: '12px' }}>✅</div>
        <h2 style={{ color: '#22c55e', marginBottom: '8px' }}>Refund Claimed</h2>
        <p style={{ color: '#9ca3af', fontSize: '14px', wordBreak: 'break-all' }}>Tx: {txSig.slice(0, 24)}...</p>
        <p style={{ marginTop: '8px' }}>
          <a href={`https://explorer.solana.com/tx/${txSig}?cluster=devnet`}
             target="_blank" rel="noopener noreferrer" style={{ color: '#7c3aed' }}>
            View on Explorer
          </a>
        </p>
      </div>
    </Card>
  );

  const claimed = refund?.status !== 'pending';
  const walletAuthorized = !refund?.creator_wallet || (connected && publicKey && refund?.creator_wallet === publicKey.toBase58());

  return (
    <Card>
      <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '16px' }}>Refund Summary</h2>
      <Row label="Amount" value={`${refund?.amount} ${refund?.token_symbol}`} />
      <Row label="Source" value={`Cancelled Bet ${refund?.bet_id?.slice(0, 4)}`} />
      <Row label="Status" value={claimed ? 'Claimed' : 'Ready to Claim'}
           color={claimed ? '#22c55e' : '#f59e0b'} />
      {!refund?.eligible && (
        <div style={{ background: '#450a0a', color: '#ef4444', padding: '10px', borderRadius: '8px', marginTop: '12px', fontSize: '13px' }}>
          This refund is no longer available. {refund?.reason ? `(${refund.reason})` : ''}
        </div>
      )}
      {connected && !walletAuthorized && refund?.creator_wallet && !claimed && (
        <div style={{ background: '#450a0a', color: '#ef4444', padding: '10px', borderRadius: '8px', marginTop: '12px', fontSize: '13px' }}>
          This wallet is not authorized to claim this refund.
        </div>
      )}
      {error && (
        <div style={{ background: '#450a0a', color: '#ef4444', padding: '10px', borderRadius: '8px', marginTop: '12px', fontSize: '13px' }}>
          {error}
        </div>
      )}
      {!claimed && refund?.eligible && walletAuthorized && (
        <button onClick={handleClaim} disabled={!connected || claiming}
          style={{ width: '100%', marginTop: '20px', padding: '14px',
            background: 'linear-gradient(135deg, #7c3aed, #a855f7)', color: '#fff',
            border: 'none', borderRadius: '12px', fontSize: '16px', fontWeight: 700,
            cursor: connected && !claiming ? 'pointer' : 'default',
            opacity: connected && !claiming ? 1 : 0.5 }}>
          {claiming ? 'Processing...' : connected ? 'Claim Refund' : 'Connect wallet above to claim'}
        </button>
      )}
    </Card>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ maxWidth: '420px', margin: '0 auto', background: 'rgba(255,255,255,0.05)',
      backdropFilter: 'blur(12px)', borderRadius: '16px', padding: '24px',
      border: '1px solid rgba(255,255,255,0.1)' }}>
      {children}
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0',
      borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
      <span style={{ color: '#9ca3af', fontSize: '14px' }}>{label}</span>
      <span style={{ color: color || '#f0f0f0', fontWeight: 600, fontSize: '14px' }}>{value}</span>
    </div>
  );
}

export default function RefundPage() {
  const [searchParams] = useSearchParams();
  const refundId = searchParams.get('refund_id') || '';
  const endpoint = useMemo(() => clusterApiUrl('devnet'), []);
  const wallets = useMemo(() => [new PhantomWalletAdapter(), new SolflareWalletAdapter()], []);

  return (
    <ConnectionProvider endpoint={endpoint}>
      <WalletProvider wallets={wallets} autoConnect>
        <WalletModalProvider>
          <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #0a0a2e 0%, #1a1a4e 50%, #0a0a0a 100%)', padding: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 20px', marginBottom: '32px' }}>
              <div style={{ fontSize: '24px', fontWeight: 800, color: '#7c3aed' }}>BanterBet</div>
              <WalletMultiButton />
            </div>
            <RefundContent refundId={refundId} />
          </div>
        </WalletModalProvider>
      </WalletProvider>
    </ConnectionProvider>
  );
}
