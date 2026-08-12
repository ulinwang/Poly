import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import TopNav from './TopNav';
import Sidebar from './Sidebar';

export default function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="relative flex h-screen overflow-hidden bg-[#f4f7f6] text-surface-900 dark:bg-[#081311] dark:text-surface-50">
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="absolute -left-24 -top-40 h-96 w-96 rounded-full bg-primary-300/15 blur-3xl dark:bg-primary-700/10" />
        <div className="absolute -right-32 top-1/3 h-80 w-80 rounded-full bg-cyan-200/20 blur-3xl dark:bg-cyan-800/10" />
      </div>

      {/* Persistent sidebar — desktop */}
      <div className="relative z-20 hidden lg:block">
        <Sidebar />
      </div>

      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
      <TopNav onMenuClick={() => setSidebarOpen(!sidebarOpen)} />
      <div className="relative flex flex-1 overflow-hidden">
        {/* Mobile sidebar overlay + drawer */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-30 bg-surface-950/40 backdrop-blur-sm lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <div className={`
          fixed lg:hidden inset-y-0 left-0 z-40
          transform transition-transform duration-200
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}>
          <Sidebar onNavigate={() => setSidebarOpen(false)} />
        </div>

        <main className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
          <div className="animate-fade-in-up">
            <Outlet />
          </div>
        </main>
      </div>
      </div>
    </div>
  );
}
