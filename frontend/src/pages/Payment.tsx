import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ConnectionProvider, WalletProvider } from '@solana/wallet-adapter-react';
import { WalletModalProvider, WalletMultiButton } from '@solana/wallet-adapter-react-ui';
import { PhantomWalletAdapter, SolflareWalletAdapter } from '@solana/wallet-adapter-wallets';
import { clusterApiUrl } from '@solana/web3.js';
import PaymentContent from '../components/PaymentContent';

import '@solana/wallet-adapter-react-ui/styles.css';

export default function PaymentPage() {
  const [searchParams] = useSearchParams();
  const paymentId = searchParams.get('payment_id') || '';

  const endpoint = useMemo(() => {
    const url = new URL(window.location.origin);
    if (url.hostname.includes('devnet') || url.hostname.includes('localhost')) {
      return clusterApiUrl('devnet');
    }
    return 'https://api.devnet.solana.com';
  }, []);

  const wallets = useMemo(
    () => [new PhantomWalletAdapter(), new SolflareWalletAdapter()],
    [],
  );

  return (
    <ConnectionProvider endpoint={endpoint}>
      <WalletProvider wallets={wallets} autoConnect>
        <WalletModalProvider>
          <div style={styles.container}>
            <div style={styles.header}>
              <div style={styles.logo}>BanterBet</div>
              <WalletMultiButton />
            </div>
            <PaymentContent paymentId={paymentId} />
          </div>
        </WalletModalProvider>
      </WalletProvider>
    </ConnectionProvider>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    background: 'linear-gradient(135deg, #0a0a2e 0%, #1a1a4e 50%, #0a0a0a 100%)',
    padding: '16px',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 20px',
    marginBottom: '32px',
  },
  logo: {
    fontSize: '24px',
    fontWeight: 800,
    color: '#7c3aed',
  },
};
