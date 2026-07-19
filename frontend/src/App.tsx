import { Routes, Route } from 'react-router-dom';
import LandingPage from './pages/Landing';
import PaymentPage from './pages/Payment';
import RefundPage from './pages/Refund';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/pay" element={<PaymentPage />} />
      <Route path="/pay/:paymentId" element={<PaymentPage />} />
      <Route path="/refund" element={<RefundPage />} />
      <Route path="/refund/:refundId" element={<RefundPage />} />
    </Routes>
  );
}
