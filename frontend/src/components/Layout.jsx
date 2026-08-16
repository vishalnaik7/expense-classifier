import React, { useState } from 'react';
import Sidebar from './Sidebar';

/** Shared page shell: dark sidebar + light content area, used by every authenticated page. */
const Layout = ({ children }) => {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#f4f5fb] flex">
      <Sidebar mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} />

      <div className="flex-1 min-w-0">
        <button
          onClick={() => setMobileOpen(true)}
          className="lg:hidden fixed top-4 left-4 z-20 p-2 bg-white rounded-lg shadow-md"
          aria-label="Open menu"
        >
          <svg className="w-5 h-5 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <main className="px-4 sm:px-6 lg:px-10 pt-16 lg:pt-8 pb-6 sm:pb-8 max-w-[1600px] mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
};

export default Layout;
