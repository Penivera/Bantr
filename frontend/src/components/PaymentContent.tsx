import { useState, useEffect, useCallback } from 'react';
import { useConnection, useWallet } from '@solana/wallet-adapter-react';
import { Transaction, PublicKey } from '@solana/web3.js';

interface PaymentInfo {
  payment_id: string;
  bet_id: string;
  amount: number;
  token_symbol: string;
  token_mint: string;
  recipient: string;
  status: string;
  instruction: string;
  created_at: number;
  expires_at: number;
}

export default function PaymentContent({ paymentId }: { paymentId: string }) {
  const { connection } = useConnection();
  const { publicKey, signTransaction, connected } = useWallet();
  const [payment, setPayment] = useState<PaymentInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [paying, setPaying] = useState(false);
  const [done, setDone] = useState(false);
  const [txSig, setTxSig] = useState('');

  useEffect(() => {
    if (!paymentId) {
      setError('No payment ID provided');
      setLoading(false);
      return;
    }
    fetch(`/api/payments/${paymentId}`)
      .then(r => { if (!r.ok) throw new Error(r.status === 410 ? 'Payment expired' : 'Payment not found'); return r.json(); })
      .then(d => { setPayment(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [paymentId]);

  const handlePay = useCallback(async () => {
    if (!publicKey || !signTransaction || !payment) return;
    setPaying(true);
    setError('');

    try {
      const params = new URLSearchParams({
        bet_id: payment.bet_id,
        amount: String(payment.amount),
        tokenMint: payment.token_mint,
        tokenSymbol: payment.token_symbol,
        instruction: payment.instruction,
        fixture_id: '0',
        market: '1',
        resolve_deadline: String(payment.expires_at),
        programId: '',
      });

      const resp = await fetch(`/api/pay?${params}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account: publicKey.toBase58() }),
      });
      if (!resp.ok) throw new Error('Failed to build transaction');
      const { transaction: txBase64 } = await resp.json();

      const tx = Transaction.from(Buffer.from(txBase64, 'base64'));
      tx.feePayer = publicKey;
      const { blockhash } = await connection.getLatestBlockhash('confirmed');
      tx.recentBlockhash = blockhash;

      const signed = await signTransaction(tx);
      const sig = await connection.sendRawTransaction(signed.serialize(), { skipPreflight: true });
      const confirmation = await connection.confirmTransaction(sig, 'confirmed');

      const submitResp = await fetch(`/api/payments/${payment.payment_id}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tx_signature: sig, payer_wallet: publicKey.toBase58() }),
      });
      if (!submitResp.ok) throw new Error('Payment verification failed');

      setTxSig(sig);
      setDone(true);
    } catch (e: any) {
      const msg = e?.message || String(e);
      if (msg.includes('debit') || msg.includes('insufficient') || msg.includes('0x1')) {
        setError('Insufficient USDC or SOL balance. Get devnet tokens from <a href="https://faucet.solana.com" target="_blank">faucet</a>.');
      } else {
        setError(msg || 'Payment failed');
      }
    } finally {
      setPaying(false);
    }
  }, [publicKey, signTransaction, payment, connection]);

  if (loading) return <div style={styles.card}><p style={{ textAlign: 'center' }}>Loading payment...</p></div>;
  if (error && !payment) return <div style={styles.card}><p style={{ textAlign: 'center', color: '#ef4444' }}>{error}</p></div>;

  if (done) {
    return (
      <div style={styles.card}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '48px', marginBottom: '12px' }}>✅</div>
          <h2 style={{ color: '#22c55e', marginBottom: '8px' }}>Payment Confirmed</h2>
          <p style={{ color: '#9ca3af', fontSize: '14px', wordBreak: 'break-all' }}>
            Tx: {txSig.slice(0, 24)}... → View on Explorer
          </p>
          <p style={{ color: '#9ca3af', marginTop: '8px' }}>
            <a href={`https://explorer.solana.com/tx/${txSig}?cluster=devnet`}
               target="_blank" rel="noopener noreferrer"
               style={{ color: '#7c3aed' }}>View on Explorer</a>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.card}>
      <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '16px' }}>
        Payment Summary
      </h2>
      <div style={styles.row}>
        <span style={styles.label}>Amount</span>
        <span style={styles.value}>{payment?.amount} {payment?.token_symbol}</span>
      </div>
      <div style={styles.row}>
        <span style={styles.label}>Recipient</span>
        <span style={{ ...styles.value, fontSize: '12px', fontFamily: 'monospace' }}>
          {payment?.recipient?.slice(0, 12)}...
        </span>
      </div>
      <div style={styles.row}>
        <span style={styles.label}>Network</span>
        <span style={styles.value}>Solana Devnet</span>
      </div>
      <div style={styles.row}>
        <span style={styles.label}>Status</span>
        <span style={{ ...styles.value, color: payment?.status === 'pending' ? '#f59e0b' : '#22c55e' }}>
          {payment?.status}
        </span>
      </div>
      {error && (
        <div style={{ background: '#450a0a', color: '#ef4444', padding: '10px', borderRadius: '8px', marginTop: '12px', fontSize: '13px' }}>
          {error}
        </div>
      )}
      <button
        onClick={handlePay}
        disabled={!connected || paying}
        style={{
          ...styles.payButton,
          opacity: connected && !paying ? 1 : 0.5,
        }}
      >
        {paying ? 'Processing...' : connected ? 'Make Payment' : 'Connect wallet above to pay'}
      </button>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    maxWidth: '420px',
    margin: '0 auto',
    background: 'rgba(255,255,255,0.05)',
    backdropFilter: 'blur(12px)',
    borderRadius: '16px',
    padding: '24px',
    border: '1px solid rgba(255,255,255,0.1)',
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '10px 0',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  label: { color: '#9ca3af', fontSize: '14px' },
  value: { color: '#f0f0f0', fontWeight: 600, fontSize: '14px' },
  payButton: {
    width: '100%',
    marginTop: '20px',
    padding: '14px',
    background: 'linear-gradient(135deg, #7c3aed, #a855f7)',
    color: '#fff',
    border: 'none',
    borderRadius: '12px',
    fontSize: '16px',
    fontWeight: 700,
    cursor: 'pointer',
  },
};
