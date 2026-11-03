import { useState, useEffect, useCallback } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import AccessModal from './components/AccessModal';
import ChatPage from './pages/ChatPage';
import IngestPage from './pages/IngestPage';
import LibraryPage from './pages/LibraryPage';
import DiagnosticsPage from './pages/DiagnosticsPage';
import MonitoringPage from './pages/MonitoringPage';
import AdminPage from './pages/AdminPage';
import AlertsPage from './pages/AlertsPage';
import { isAuthenticated, clearAuth, getStoredRole, getQuota } from './api/client';
import './App.css';

export default function App() {
  const [authed, setAuthed] = useState(isAuthenticated());
  const [quota, setQuota] = useState(null);

  const refreshQuota = useCallback(async () => {
    if (!isAuthenticated()) return;
    try {
      const q = await getQuota();
      setQuota(q);
    } catch {
      // Swallow — quota display is best-effort
    }
  }, []);

  // Listen for forced logout (token expired / 401)
  useEffect(() => {
    const handler = () => {
      setAuthed(false);
      setQuota(null);
    };
    window.addEventListener('ckp:auth_expired', handler);
    return () => window.removeEventListener('ckp:auth_expired', handler);
  }, []);

  // Refresh quota on mount and after each query
  useEffect(() => {
    if (authed) refreshQuota();
  }, [authed, refreshQuota]);

  // Listen for query events to refresh quota
  useEffect(() => {
    const handler = () => refreshQuota();
    window.addEventListener('ckp:query_complete', handler);
    return () => window.removeEventListener('ckp:query_complete', handler);
  }, [refreshQuota]);

  const handleAuth = (result) => {
    setAuthed(true);
    if (result) {
      setQuota({
        role: result.role,
        queries_used: result.queries_used || 0,
        queries_remaining: result.queries_remaining,
        query_limit: result.query_limit || 0,
      });
    }
  };

  const handleLogout = () => {
    clearAuth();
    setAuthed(false);
    setQuota(null);
  };

  if (!authed) {
    return <AccessModal onAuthenticated={handleAuth} />;
  }

  return (
    <BrowserRouter>
      <Layout quota={quota} onLogout={handleLogout}>
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/ingest" element={<IngestPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/monitoring" element={<MonitoringPage />} />
          <Route path="/diagnostics" element={<DiagnosticsPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
