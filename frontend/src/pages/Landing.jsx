import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const Landing = () => {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="relative min-h-[calc(100vh-4rem)] flex items-center justify-center overflow-hidden px-4 sm:px-6 lg:px-8 py-12">
      {/* Background neon glows */}
      <div className="absolute top-1/4 left-1/4 -translate-x-1/2 -translate-y-1/2 w-96 h-96 rounded-full bg-indigo-600/10 blur-[100px] pointer-events-none"></div>
      <div className="absolute bottom-1/4 right-1/4 translate-x-1/2 translate-y-1/2 w-[450px] h-[450px] rounded-full bg-purple-600/10 blur-[120px] pointer-events-none"></div>

      <div className="max-w-4xl w-full text-center space-y-8 relative z-10">
        {/* Badge */}
        <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-full border border-indigo-500/20 bg-indigo-950/20 text-indigo-400 text-xs font-bold tracking-wide animate-pulse">
          <span>🔒</span>
          <span>100% Local, Private Career Intelligence</span>
        </div>

        {/* Hero title */}
        <div className="space-y-4">
          <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight leading-[1.1]">
            Your AI-Powered Career Copilot
            <span className="block mt-2 bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
              AI Powered Assistance Platform
            </span>
          </h1>
          <p className="max-w-xl mx-auto text-dark-300 text-base sm:text-lg font-medium leading-relaxed">
            Extract skills securely, analyze job gaps, scrape matching local jobs, and draft highly tailored applications. All computed privately on your machine.
          </p>
        </div>

        {/* CTA Buttons */}
        <div className="flex flex-wrap justify-center gap-4">
          {isAuthenticated ? (
            <button
              onClick={() => navigate('/dashboard')}
              className="px-8 py-3.5 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white font-bold rounded-2xl transition-all duration-300 shadow-[0_4px_20px_rgba(99,102,241,0.3)] transform hover:-translate-y-0.5"
            >
              Enter Dashboard
            </button>
          ) : (
            <>
              <Link
                to="/auth?mode=register"
                className="px-8 py-3.5 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white font-bold rounded-2xl transition-all duration-300 shadow-[0_4px_20px_rgba(99,102,241,0.3)] transform hover:-translate-y-0.5"
              >
                Get Started
              </Link>
              <Link
                to="/auth?mode=login"
                className="px-8 py-3.5 bg-dark-900 border border-dark-800 hover:bg-dark-800 text-dark-100 font-bold rounded-2xl transition-all duration-300 transform hover:-translate-y-0.5"
              >
                Sign In
              </Link>
            </>
          )}
        </div>

        {/* Feature Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-12 text-left">
          <div className="glass-panel rounded-2xl p-6 border">
            <div className="text-2xl mb-3">🛡️</div>
            <h3 className="text-lg font-bold text-dark-100 mb-1.5">Phase 1: Local Intelligence</h3>
            <p className="text-xs text-dark-400 leading-relaxed">
              Upload resume documents safely. The text parser extracts semantic structures, parses skill competencies, and highlights missing gaps using Qwen3:14b running locally on your hardware.
            </p>
          </div>

          <div className="glass-panel rounded-2xl p-6 border">
            <div className="text-2xl mb-3">⚡</div>
            <h3 className="text-lg font-bold text-dark-100 mb-1.5">Phase 2: Market Matcher</h3>
            <p className="text-xs text-dark-400 leading-relaxed">
              Retrieve real-time jobs scraped from LinkedIn, Indeed, and Glassdoor. Compute similarity matrices natively inside ChromaDB vectors to find perfect listings, and customize resume copy instantly.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
export default Landing;
