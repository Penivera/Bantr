export default function LandingPage() {
  return (
    <div style={styles.container}>
      <div style={styles.hero}>
        <h1 style={styles.title}>BanterBet</h1>
        <p style={styles.subtitle}>On-chain World Cup betting. Challenge friends. Verify on Solana.</p>
        <div style={styles.buttons}>
          <a href="https://t.me/bantersol_bot" target="_blank" rel="noopener noreferrer" style={styles.primaryBtn}>
            Open in Telegram
          </a>
        </div>
      </div>
      <div style={styles.features}>
        {[
          { icon: '⚽', title: 'Live World Cup Markets', desc: 'Bet on goals, cards, corners, match winners and more' },
          { icon: '🔗', title: 'On-Chain Escrow', desc: 'USDC held in audited Solana program escrow' },
          { icon: '🤝', title: 'Challenge Friends', desc: 'Create bets and challenge others in your group chat' },
          { icon: '🏆', title: 'Leaderboards', desc: 'Compete for top spot across fixtures' },
        ].map((f, i) => (
          <div key={i} style={styles.featureCard}>
            <div style={styles.featureIcon}>{f.icon}</div>
            <h3 style={styles.featureTitle}>{f.title}</h3>
            <p style={styles.featureDesc}>{f.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    background: 'linear-gradient(135deg, #0a0a2e 0%, #1a1a4e 50%, #0a0a0a 100%)',
  },
  hero: {
    textAlign: 'center',
    padding: '80px 20px 40px',
  },
  title: {
    fontSize: 'clamp(32px, 8vw, 64px)',
    fontWeight: 900,
    background: 'linear-gradient(135deg, #7c3aed, #a855f7, #ec4899)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    marginBottom: '16px',
  },
  subtitle: {
    color: '#9ca3af',
    fontSize: '18px',
    maxWidth: '500px',
    margin: '0 auto',
    lineHeight: 1.6,
  },
  buttons: { marginTop: '32px' },
  primaryBtn: {
    display: 'inline-block',
    padding: '14px 40px',
    background: 'linear-gradient(135deg, #7c3aed, #a855f7)',
    color: '#fff',
    borderRadius: '12px',
    fontSize: '18px',
    fontWeight: 700,
    textDecoration: 'none',
  },
  features: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
    gap: '20px',
    maxWidth: '1000px',
    margin: '0 auto',
    padding: '40px 20px 80px',
  },
  featureCard: {
    background: 'rgba(255,255,255,0.05)',
    borderRadius: '16px',
    padding: '24px',
    border: '1px solid rgba(255,255,255,0.08)',
  },
  featureIcon: { fontSize: '32px', marginBottom: '12px' },
  featureTitle: { fontSize: '16px', fontWeight: 700, marginBottom: '8px', color: '#f0f0f0' },
  featureDesc: { fontSize: '14px', color: '#9ca3af', lineHeight: 1.5 },
};
