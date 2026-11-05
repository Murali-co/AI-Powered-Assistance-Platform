import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import apiClient from '../api/client';
import toast from 'react-hot-toast';
import { LoadingSpinner } from './LoadingSpinner';

export const Navbar = () => {
  const { user, logout } = useAuth();
  const location = useLocation();
  
  const [notifications, setNotifications] = useState([]);
  const [showNotifications, setShowNotifications] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Feedback states
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);

  const handleSubmitFeedback = async () => {
    if (!feedbackText.trim()) return;
    setIsSubmittingFeedback(true);
    const loadingToast = toast.loading('Sending feedback...');
    try {
      await apiClient.post('/feedback/submit', { feedback: feedbackText });
      toast.success('Thank you! Your feedback has been sent.', { id: loadingToast });
      setShowFeedbackModal(false);
      setFeedbackText('');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to submit feedback. Please try again.', { id: loadingToast });
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  const navItems = [
    { name: 'Dashboard', path: '/dashboard' },
    { name: 'Upload Resume', path: '/upload' },
    { name: 'Job Board', path: '/jobs' },
    { name: 'Smart Match', path: '/match' },
    { name: 'Applications', path: '/applications' },
    { name: 'Career Copilot', path: '/copilot' },
    { name: 'Interview Coach', path: '/interview' },
    { name: 'Security', path: '/security' },
    ...(user?.is_admin ? [{ name: 'Audit Log', path: '/admin/audit-log' }] : []),
  ];

  const isActive = (path) => location.pathname === path;

  // Fetch notifications
  const fetchNotifications = useCallback(async () => {
    if (!user) return;
    try {
      const res = await apiClient.get('/notifications');
      setNotifications(res.data || []);
    } catch (err) {
      console.error("Failed to fetch notifications:", err);
    }
  }, [user]);

  useEffect(() => {
    fetchNotifications();
    // Poll every 20 seconds for new alerts
    const interval = setInterval(fetchNotifications, 20000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  // Handle outside click to close dropdown
  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowNotifications(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const unreadCount = notifications.filter(n => !n.is_read).length;

  const handleMarkRead = async (id) => {
    try {
      await apiClient.post(`/notifications/read/${id}`);
      fetchNotifications();
    } catch (err) {
      console.error(err);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await apiClient.post('/notifications/read-all');
      fetchNotifications();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <nav className="sticky top-0 z-50 w-full glass-panel border-b border-dark-800 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/dashboard" className="flex items-center space-x-2">
            <span className="text-2xl">🧭</span>
            <span className="font-extrabold text-xl tracking-tight bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
              AI Powered Assistance Platform
            </span>
          </Link>

          {/* Nav Links */}
          <div className="hidden lg:flex items-center space-x-1.5">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`px-2.5 py-1.5 rounded-xl text-xs font-bold transition-all duration-200 whitespace-nowrap border ${
                  isActive(item.path)
                    ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/35'
                    : 'text-dark-300 hover:text-dark-50 hover:bg-dark-900/60 border-transparent hover:border-dark-800'
                }`}
              >
                {item.name}
              </Link>
            ))}
          </div>

          {/* User & Alerts Section */}
          <div className="flex items-center space-x-2 sm:space-x-3">
            {user && (
              <div className="relative flex items-center" ref={dropdownRef}>
                <button
                  onClick={() => setShowNotifications(!showNotifications)}
                  className="w-9 h-9 flex items-center justify-center rounded-xl text-dark-300 hover:text-dark-50 hover:bg-dark-900/60 border border-transparent hover:border-dark-800 transition-all duration-200 relative"
                  aria-label="Notifications"
                >
                  <span className="text-lg">🔔</span>
                  {unreadCount > 0 && (
                    <span className="absolute top-1.5 right-1.5 bg-indigo-500 text-white text-[9px] font-bold rounded-full w-4 h-4 flex items-center justify-center animate-pulse">
                      {unreadCount}
                    </span>
                  )}
                </button>

                {/* Notifications Dropdown */}
                {showNotifications && (
                  <div className="absolute right-0 mt-12 w-80 rounded-xl glass-panel border border-dark-800 shadow-2xl overflow-hidden z-50">
                    <div className="p-3 border-b border-dark-800 flex justify-between items-center bg-dark-950/60">
                      <h3 className="font-bold text-sm text-dark-50">Notifications</h3>
                      {unreadCount > 0 && (
                        <button
                          onClick={handleMarkAllRead}
                          className="text-[11px] text-indigo-400 hover:text-indigo-300 font-semibold"
                        >
                          Mark all as read
                        </button>
                      )}
                    </div>
                    <div className="max-h-64 overflow-y-auto divide-y divide-dark-800">
                      {notifications.length === 0 ? (
                        <div className="p-4 text-center text-xs text-dark-400">
                          No notifications yet.
                        </div>
                      ) : (
                        notifications.map((n) => (
                          <div
                            key={n.id}
                            className={`p-3 transition-colors duration-150 relative ${
                              n.is_read ? 'bg-transparent text-dark-400' : 'bg-indigo-950/10 text-dark-100 font-medium'
                            }`}
                          >
                            <div className="flex justify-between items-start">
                              <span className="text-[11px] font-bold tracking-wide uppercase text-indigo-400 mb-0.5">
                                {n.type === 'job_alert' ? '💼 Job Alert' : '📢 System'}
                              </span>
                              {!n.is_read && (
                                <button
                                  onClick={() => handleMarkRead(n.id)}
                                  className="text-[10px] text-dark-400 hover:text-indigo-400"
                                >
                                  Mark read
                                </button>
                              )}
                            </div>
                            <h4 className="text-xs font-semibold mb-0.5">{n.title}</h4>
                            <p className="text-[11px] leading-relaxed">{n.message}</p>
                            <span className="text-[9px] text-dark-500 block mt-1">
                              {new Date(n.created_at + 'Z').toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {user ? (
              <>
                <button
                  onClick={() => setShowFeedbackModal(true)}
                  className="h-9 px-3.5 rounded-xl border border-indigo-500/30 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 text-xs font-bold transition-all duration-200 flex items-center justify-center whitespace-nowrap"
                >
                  Feedback
                </button>
                <span className="hidden md:flex h-9 items-center justify-center text-xs font-bold px-3.5 rounded-xl bg-dark-900/60 text-dark-200 border border-dark-800 whitespace-nowrap">
                  👤 {user.full_name}
                </span>
                <button
                  onClick={logout}
                  className="h-9 px-3.5 rounded-xl border border-red-500/30 bg-red-500/10 hover:bg-red-500/20 text-red-300 text-xs font-bold transition-all duration-200 flex items-center justify-center whitespace-nowrap"
                >
                  Logout
                </button>
              </>
            ) : (
              <Link
                to="/auth"
                className="h-9 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition-all duration-200 flex items-center justify-center"
              >
                Login
              </Link>
            )}

            {/* Mobile menu button */}
            <div className="flex items-center lg:hidden ml-1">
              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                className="w-9 h-9 flex items-center justify-center rounded-xl text-dark-300 hover:text-dark-50 hover:bg-dark-900/60 border border-dark-800 transition-all duration-200"
                aria-label="Toggle menu"
              >
                <span className="text-base font-bold">{mobileMenuOpen ? '✕' : '☰'}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Menu Dropdown */}
      {mobileMenuOpen && (
        <div className="lg:hidden px-4 pt-2 pb-4 space-y-1.5 border-t border-dark-800 bg-dark-950/95 backdrop-blur-md">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              onClick={() => setMobileMenuOpen(false)}
              className={`block px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all duration-200 border ${
                isActive(item.path)
                  ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/35'
                  : 'text-dark-300 hover:text-dark-50 hover:bg-dark-900/50 border-transparent'
              }`}
            >
              {item.name}
            </Link>
          ))}
        </div>
      )}

      {/* Feedback Modal */}
      {showFeedbackModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-950/80 backdrop-blur-sm">
          <div className="w-full max-w-md glass-panel border border-dark-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-dark-800">
              <h3 className="text-base font-bold text-dark-50 flex items-center space-x-2">
                <span>💬</span>
                <span>Submit Feedback</span>
              </h3>
              <button
                onClick={() => {
                  setShowFeedbackModal(false);
                  setFeedbackText('');
                }}
                className="text-dark-400 hover:text-dark-200 text-sm"
              >
                ✕
              </button>
            </div>

            <p className="text-[11px] text-dark-400 leading-relaxed font-medium">
              We appreciate your feedback! Please let us know what you think, report bugs, or request features. Your message will be sent directly to the development team.
            </p>

            <div className="space-y-1.5">
              <textarea
                value={feedbackText}
                onChange={(e) => setFeedbackText(e.target.value)}
                disabled={isSubmittingFeedback}
                placeholder="Write your feedback here..."
                rows={5}
                className="w-full p-3 bg-dark-900 border border-dark-800 focus:border-indigo-500/40 rounded-xl outline-none text-xs text-dark-100 leading-relaxed font-semibold focus:ring-1 focus:ring-indigo-500/20 transition-all resize-none"
              />
            </div>

            <div className="flex justify-end space-x-2 pt-2">
              <button
                onClick={() => {
                  setShowFeedbackModal(false);
                  setFeedbackText('');
                }}
                disabled={isSubmittingFeedback}
                className="px-4 py-2 border border-dark-800 hover:bg-dark-800 text-dark-400 hover:text-dark-200 font-bold rounded-xl text-xs"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmitFeedback}
                disabled={isSubmittingFeedback || !feedbackText.trim()}
                className="px-5 py-2 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 disabled:from-dark-900 disabled:to-dark-900 text-white font-bold rounded-xl text-xs transition-all shadow-md flex items-center justify-center space-x-2"
              >
                {isSubmittingFeedback ? (
                  <>
                    <LoadingSpinner size="sm" text="" />
                    <span>Submitting...</span>
                  </>
                ) : (
                  <span>Submit</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </nav>
  );
};
export default Navbar;
