import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import TopNav from './TopNav';
import Sidebar from './Sidebar';

export default function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="relative flex h-screen overflow-hidden bg-[#f3f4f4] text-surface-900 dark:bg-[#0b0f0e] dark:text-surface-50">

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
          <Sidebar forceExpanded onNavigate={() => setSidebarOpen(false)} />
        </div>

        <main className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 lg:px-7 lg:py-6">
          <div className="animate-fade-in-up">
            <Outlet />
          </div>
        </main>
      </div>
      </div>
    </div>
  );
}
