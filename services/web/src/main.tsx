import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './styles/tailwind.css';
import App from './App.tsx';
import { ActiveCaseProvider } from './lib/activeCase';
import { AuthProvider } from './context/AuthContext';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ActiveCaseProvider>
          <App />
        </ActiveCaseProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
