import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import ChatPage from './pages/ChatPage';
import IngestPage from './pages/IngestPage';
import LibraryPage from './pages/LibraryPage';
import DiagnosticsPage from './pages/DiagnosticsPage';
import './App.css';

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/ingest" element={<IngestPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/diagnostics" element={<DiagnosticsPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
