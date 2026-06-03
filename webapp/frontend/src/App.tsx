import { Suspense, lazy } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './components/layout/MainLayout';
import MarketBrowser from './pages/MarketBrowser';

const MarketDetail = lazy(() => import('./pages/MarketDetail'));
const ExperimentManager = lazy(() => import('./pages/ExperimentManager'));
const ExperimentLive = lazy(() => import('./pages/ExperimentLive'));
const Settings = lazy(() => import('./pages/Settings'));

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-screen">
      <div className="w-12 h-12 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );
}
// TODO: wire ErrorFallback into react-error-boundary when added

function App() {
  return (
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
          <Route path="/settings/*" element={
            <Suspense fallback={<PageLoader />}><Settings /></Suspense>
          } />
        </Route>
      </Routes>
    </HashRouter>
  );
}

export default App;
