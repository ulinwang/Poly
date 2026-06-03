import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './components/layout/MainLayout';
import MarketBrowser from './pages/MarketBrowser';
import MarketDetail from './pages/MarketDetail';
import ExperimentManager from './pages/ExperimentManager';
import ExperimentLive from './pages/ExperimentLive';
import Settings from './pages/Settings';

function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/" element={<Navigate to="/markets" replace />} />
          <Route path="/markets" element={<MarketBrowser />} />
          <Route path="/markets/:slug" element={<MarketDetail />} />
          <Route path="/experiments" element={<ExperimentManager />} />
          <Route path="/experiments/:id" element={<ExperimentLive />} />
          <Route path="/settings/*" element={<Settings />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}

export default App;
