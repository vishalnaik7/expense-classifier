import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import useAuthStore from '../store/authStore';

const linkClass = ({ isActive }) =>
  `px-3 py-2 rounded-lg text-sm font-semibold transition ${
    isActive ? 'bg-blue-600 text-white' : 'text-gray-700 hover:bg-blue-50'
  }`;

/**
 * Responsive top navigation shared by authenticated pages.
 * Collapses into a hamburger menu below the `sm` breakpoint.
 */
const Navbar = () => {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <nav className="bg-white shadow-sm sticky top-0 z-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        <div className="flex items-center justify-between h-16">
          <NavLink to="/dashboard" className="flex items-center gap-2 shrink-0">
            <span className="text-xl">💰</span>
            <span className="font-bold text-gray-900 text-base sm:text-lg">Expense Tracker</span>
          </NavLink>

          {/* Desktop nav */}
          <div className="hidden sm:flex items-center gap-2">
            <NavLink to="/dashboard" className={linkClass}>Dashboard</NavLink>
            <NavLink to="/upload" className={linkClass}>Upload</NavLink>
          </div>

          <div className="hidden sm:flex items-center gap-3">
            <span className="text-sm text-gray-600 truncate max-w-[10rem]">
              {user?.username}
            </span>
            <button
              onClick={handleLogout}
              className="bg-red-600 hover:bg-red-700 text-white text-sm font-semibold py-2 px-4 rounded-lg transition"
            >
              Logout
            </button>
          </div>

          {/* Mobile hamburger */}
          <button
            onClick={() => setMenuOpen((open) => !open)}
            className="sm:hidden p-2 rounded-lg text-gray-700 hover:bg-gray-100"
            aria-label="Toggle menu"
            aria-expanded={menuOpen}
          >
            {menuOpen ? (
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>

        {/* Mobile menu */}
        {menuOpen && (
          <div className="sm:hidden pb-4 flex flex-col gap-1 border-t border-gray-100 pt-3">
            <NavLink to="/dashboard" className={linkClass} onClick={() => setMenuOpen(false)}>
              Dashboard
            </NavLink>
            <NavLink to="/upload" className={linkClass} onClick={() => setMenuOpen(false)}>
              Upload
            </NavLink>
            <div className="flex items-center justify-between px-3 pt-2 mt-2 border-t border-gray-100">
              <span className="text-sm text-gray-600 truncate">{user?.username}</span>
              <button
                onClick={handleLogout}
                className="bg-red-600 hover:bg-red-700 text-white text-sm font-semibold py-2 px-4 rounded-lg transition"
              >
                Logout
              </button>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
};

export default Navbar;
