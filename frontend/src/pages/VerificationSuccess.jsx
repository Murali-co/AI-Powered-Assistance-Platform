import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export const VerificationSuccess = () => {
  const navigate = useNavigate();

  useEffect(() => {
    // Redirect to login after 5 seconds
    const timer = setTimeout(() => {
      navigate('/auth?mode=login');
    }, 5000);

    return () => clearTimeout(timer);
  }, [navigate]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        {/* Success Animation */}
        <div className="text-center mb-8">
          <div className="relative w-20 h-20 mx-auto mb-6">
            <div className="absolute inset-0 bg-green-500/20 rounded-full animate-pulse"></div>
            <div className="absolute inset-2 bg-slate-800 rounded-full flex items-center justify-center border-2 border-green-500">
              <svg className="w-10 h-10 text-green-500 animate-bounce" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="bg-slate-800 rounded-lg shadow-lg p-8 border border-green-500/30 text-center">
          <h1 className="text-3xl font-bold text-white mb-2">Email Verified!</h1>
          <p className="text-slate-400 mb-2">
            🎉 Congratulations! Your email has been successfully verified.
          </p>
          <p className="text-slate-500 mb-6">
            You can now log in to your AI Powered Assistance Platform account and start your job search journey.
          </p>

          {/* Features */}
          <div className="bg-slate-700/50 rounded-lg p-4 mb-6 border border-slate-600">
            <h3 className="text-slate-300 font-semibold mb-3">What's Next?</h3>
            <ul className="space-y-2 text-left text-slate-400 text-sm">
              <li className="flex items-center gap-2">
                <svg className="w-4 h-4 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                <span>Upload your resume for AI analysis</span>
              </li>
              <li className="flex items-center gap-2">
                <svg className="w-4 h-4 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                <span>Discover personalized job matches</span>
              </li>
              <li className="flex items-center gap-2">
                <svg className="w-4 h-4 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                <span>Get AI-powered cover letters</span>
              </li>
              <li className="flex items-center gap-2">
                <svg className="w-4 h-4 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                <span>Practice interviews with our AI coach</span>
              </li>
            </ul>
          </div>

          {/* CTA Buttons */}
          <div className="flex flex-col gap-3">
            <button
              onClick={() => navigate('/auth?mode=login')}
              className="w-full px-4 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors"
            >
              Go to Login
            </button>
            <p className="text-slate-500 text-sm">
              Redirecting in 5 seconds...
            </p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-4 mt-6">
          <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700 text-center">
            <div className="text-2xl font-bold text-green-400">500+</div>
            <p className="text-slate-400 text-xs mt-1">Jobs Daily</p>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700 text-center">
            <div className="text-2xl font-bold text-purple-400">AI Powered</div>
            <p className="text-slate-400 text-xs mt-1">Matches</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VerificationSuccess;
