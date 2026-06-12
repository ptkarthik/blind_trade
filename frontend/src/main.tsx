import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { LoginView } from './components/LoginView';

const AuthWrapper = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(!!localStorage.getItem('blind_trade_token'));

  if (!isAuthenticated) {
    return <LoginView onLoginSuccess={(token) => {
        localStorage.setItem('blind_trade_token', token);
        setIsAuthenticated(true);
    }} />;
  }

  return <App />;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthWrapper />
  </StrictMode>,
)
