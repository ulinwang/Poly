import { Suspense, lazy, useEffect } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './components/layout/MainLayout';
import ErrorBoundary from './components/ErrorBoundary';
import MarketBrowser from './pages/MarketBrowser';
import { useSettingsStore } from './stores';

const MarketDetail = lazy(() => import('./pages/MarketDetail'));
const ExperimentManager = lazy(() => import('./pages/ExperimentManager'));
const ExperimentLive = lazy(() => import('./pages/ExperimentLive'));
const AgentInfo = lazy(() => import('./pages/AgentInfo'));
const DataAnalysis = lazy(() => import('./pages/DataAnalysis'));
const Settings = lazy(() => import('./pages/Settings'));

function DarkModeInit() {
  useEffect(() => {
    const dark = useSettingsStore.getState().darkMode;
    if (dark) document.documentElement.classList.add('dark');
  }, []);
  return null;
}

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-screen">
      <div className="w-12 h-12 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <DarkModeInit />
      <HashRouter>
        <Routes>
          <Route element={<MainLayout />}>
            <Route path="/" element={<Navigate to="/markets" replace />} />
            <Route path="/markets" element={<MarketBrowser />} />
            <Route path="/markets/:slug" element={
              <Suspense fallback={<PageLoader />}><MarketDetail /></Suspense>
            } />
            <Route path="/experiments" element={
              <Suspense fallback={<PageLoader />}><ExperimentManager /></Suspense>
            } />
            <Route path="/experiments/:id" element={
              <Suspense fallback={<PageLoader />}><ExperimentLive /></Suspense>
            } />
            <Route path="/agent" element={
              <Suspense fallback={<PageLoader />}><AgentInfo /></Suspense>
            } />
            <Route path="/analysis" element={
              <Suspense fallback={<PageLoader />}><DataAnalysis /></Suspense>
            } />
            <Route path="/settings/*" element={
              <Suspense fallback={<PageLoader />}><Settings /></Suspense>
            } />
          </Route>
        </Routes>
      </HashRouter>
    </ErrorBoundary>
  );
}

export default App;
