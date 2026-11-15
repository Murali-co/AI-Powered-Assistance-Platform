import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import apiClient from '../api/client';

const isValidEmail = (email) =>
  /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

export const ForgotPassword = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!email) {
      toast.error('Please enter your email address');
      return;
    }

    if (!isValidEmail(email)) {
      toast.error('Please enter a valid email address');
      return;
    }

    setSending(true);
    try {
      await apiClient.post('/auth/forgot-password', { email });
      setSent(true);
      toast.success('Password reset email sent! Check your inbox.');
    } catch (err) {
      const errorMsg = err.response?.data?.detail || 'Failed to send password reset email';
      toast.error(errorMsg);
    } finally {
      setSending(false);
    }
  };

  if (sent) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-slate-800 rounded-lg shadow-lg p-8 border border-green-500/30">
          <div className="flex flex-col items-center gap-4">
            <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center">
              <svg className="w-8 h-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white">Reset Email Sent!</h2>
            <p className="text-slate-400 text-center">
              We've sent a password reset link to <span className="text-purple-400 font-medium">{email}</span>
            </p>
            <p className="text-slate-500 text-sm">Click the link in your email to reset your password. The link expires in 15 minutes.</p>
            <div className="flex gap-3 w-full pt-4">
              <button
                onClick={() => navigate('/auth?mode=login')}
                className="flex-1 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors"
              >
                Back to Login
              </button>
              <button
                onClick={() => setSent(false)}
                className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium transition-colors"
              >
                Try Another Email
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-slate-800 rounded-lg shadow-lg p-8 border border-purple-500/30">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white">Forgot Password?</h1>
          <p className="text-slate-400 mt-2">
            No worries! Enter your email address and we'll send you a link to reset your password.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Email Address
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500"
              disabled={sending}
            />
          </div>

          <button
            type="submit"
            disabled={sending}
            className="w-full px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
          >
            {sending ? 'Sending...' : 'Send Reset Link'}
          </button>
        </form>

        <div className="mt-6 space-y-3 pt-6 border-t border-slate-700">
          <button
            onClick={() => navigate('/auth?mode=login')}
            className="w-full text-slate-400 hover:text-purple-400 transition-colors font-medium"
          >
            ← Back to Login
          </button>
          <button
            onClick={() => navigate('/auth?mode=register')}
            className="w-full text-slate-400 hover:text-purple-400 transition-colors text-sm"
          >
            Don't have an account? Register
          </button>
        </div>
      </div>
    </div>
  );
};

export default ForgotPassword;
