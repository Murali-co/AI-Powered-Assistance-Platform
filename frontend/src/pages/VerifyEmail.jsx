import React, { useState, useRef } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import apiClient, { setAccessToken } from '../api/client';

export const VerifyEmail = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');

  // States: 'idle' | 'verifying' | 'success' | 'expired' | 'error' | 'missing'
  const [status, setStatus] = useState(() => (token ? 'idle' : 'missing'));
  const [errorMessage, setErrorMessage] = useState('');
  const hasExecutedRef = useRef(false);

  const handleVerify = async () => {
    if (!token || hasExecutedRef.current) return;
    hasExecutedRef.current = true;
    setStatus('verifying');

    try {
      // Use explicit POST request coordinated with backend (M11/M15)
      const res = await apiClient.post('/auth/verify-email', { token });
      
      if (res.data?.access_token) {
        setAccessToken(res.data.access_token);
      }
      
      setStatus('success');
      toast.success('Email verified successfully!');
      
      // Redirect to login after 3 seconds
      setTimeout(() => {
        navigate('/auth?mode=login');
      }, 3000);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Verification failed';
      setErrorMessage(detail);
      
      if (typeof detail === 'string' && detail.toLowerCase().includes('expired')) {
        setStatus('expired');
      } else {
        setStatus('error');
      }
      toast.error(detail);
    }
  };

  if (status === 'missing') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-slate-800/90 backdrop-blur-md rounded-2xl shadow-2xl p-8 border border-purple-500/20 text-center">
          <div className="w-16 h-16 bg-amber-500/10 border border-amber-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <span className="text-2xl">⚠️</span>
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Missing Verification Token</h2>
          <p className="text-slate-400 text-sm mb-6 leading-relaxed">
            No verification token was found in the link. Please check your email and open the full verification URL, or request a new verification link.
          </p>
          <div className="flex flex-col gap-3">
            <Link
              to="/resend-verification"
              className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-sm transition-all shadow-md text-center"
            >
              Request New Verification Email
            </Link>
            <Link
              to="/auth?mode=login"
              className="w-full py-2.5 px-4 bg-slate-700/80 hover:bg-slate-700 text-slate-300 font-bold rounded-xl text-sm transition-all text-center"
            >
              Back to Login
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (status === 'verifying') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-slate-800/90 backdrop-blur-md rounded-2xl shadow-2xl p-8 border border-purple-500/30 text-center">
          <div className="flex flex-col items-center gap-4">
            <div className="animate-spin rounded-full h-12 w-12 border-3 border-indigo-500 border-t-transparent"></div>
            <h2 className="text-xl font-bold text-white">Verifying Your Email...</h2>
            <p className="text-slate-400 text-sm">Validating your security token with AI Powered Assistance Platform services.</p>
          </div>
        </div>
      </div>
    );
  }

  if (status === 'success') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-slate-800/90 backdrop-blur-md rounded-2xl shadow-2xl p-8 border border-green-500/30 text-center">
          <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Email Verified!</h2>
          <p className="text-slate-300 text-sm mb-2 leading-relaxed">
            Your email address has been successfully verified. You can now access your full AI Powered Assistance Platform account.
          </p>
          <p className="text-slate-400 text-xs mb-6">Redirecting you to login in a few seconds...</p>
          <button
            onClick={() => navigate('/auth?mode=login')}
            className="w-full py-2.5 px-4 bg-green-600 hover:bg-green-500 text-white font-bold rounded-xl text-sm transition-all shadow-md"
          >
            Continue to Login
          </button>
        </div>
      </div>
    );
  }

  if (status === 'expired') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-slate-800/90 backdrop-blur-md rounded-2xl shadow-2xl p-8 border border-amber-500/30 text-center">
          <div className="w-16 h-16 bg-amber-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <span className="text-2xl">⏳</span>
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Verification Link Expired</h2>
          <p className="text-slate-400 text-sm mb-6 leading-relaxed">
            This verification link has expired for security reasons. Please request a new verification link below.
          </p>
          <div className="flex flex-col gap-3">
            <Link
              to="/resend-verification"
              className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-sm transition-all shadow-md text-center"
            >
              Resend Verification Link
            </Link>
            <Link
              to="/auth?mode=login"
              className="w-full py-2.5 px-4 bg-slate-700/80 hover:bg-slate-700 text-slate-300 font-bold rounded-xl text-sm transition-all text-center"
            >
              Back to Login
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-slate-800/90 backdrop-blur-md rounded-2xl shadow-2xl p-8 border border-rose-500/30 text-center">
          <div className="w-16 h-16 bg-rose-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-rose-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Verification Failed</h2>
          <p className="text-slate-400 text-sm mb-6 leading-relaxed">
            {errorMessage || 'We were unable to verify your email address. The token may be invalid or already used.'}
          </p>
          <div className="flex flex-col gap-3">
            <Link
              to="/resend-verification"
              className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-sm transition-all shadow-md text-center"
            >
              Request New Link
            </Link>
            <Link
              to="/auth?mode=register"
              className="w-full py-2.5 px-4 bg-slate-700/80 hover:bg-slate-700 text-slate-300 font-bold rounded-xl text-sm transition-all text-center"
            >
              Register Again
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Idle state: explicit confirmation action
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-slate-800/90 backdrop-blur-md rounded-2xl shadow-2xl p-8 border border-indigo-500/30 text-center">
        <div className="w-16 h-16 bg-indigo-500/20 border border-indigo-500/30 rounded-full flex items-center justify-center mx-auto mb-4">
          <span className="text-3xl">✉️</span>
        </div>
        <h2 className="text-2xl font-bold text-white mb-2">Confirm Email Verification</h2>
        <p className="text-slate-300 text-sm mb-6 leading-relaxed">
          Click the button below to complete your email verification and activate your AI Powered Assistance Platform account.
        </p>
        <div className="flex flex-col gap-3">
          <button
            onClick={handleVerify}
            className="w-full py-3 px-4 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold rounded-xl text-sm transition-all shadow-lg hover:shadow-indigo-500/25"
          >
            Verify Email Address
          </button>
          <Link
            to="/auth?mode=login"
            className="w-full py-2.5 px-4 bg-slate-700/60 hover:bg-slate-700 text-slate-300 font-semibold rounded-xl text-xs transition-all text-center"
          >
            Cancel
          </Link>
        </div>
      </div>
    </div>
  );
};

export default VerifyEmail;
