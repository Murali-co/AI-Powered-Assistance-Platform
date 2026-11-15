import React, { useState } from 'react';
import { useJobs } from '../hooks/useJobs';
import { LoadingSpinner } from '../components/LoadingSpinner';
import toast from 'react-hot-toast';

export const ApplicationsHistory = () => {
  const { appHistory, isLoadingHistory } = useJobs();
  const [selectedApp, setSelectedApp] = useState(null);

  if (isLoadingHistory) {
    return <LoadingSpinner text="Loading your application logs..." />;
  }

  const handleCopyMaterial = async (text, type = 'Text') => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`${type} copied to clipboard!`);
    } catch (err) {
      toast.error('Failed to copy.');
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Title */}
      <div className="pb-4 border-b border-dark-800">
        <h1 className="text-2xl md:text-3xl font-extrabold text-dark-50">Logged Applications</h1>
        <p className="text-xs text-dark-400 mt-1">Review historical resume bullets and cover letters for your past submissions.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Side: Listing Grid */}
        <div className="lg:col-span-1 space-y-4">
          <h3 className="text-xs font-bold text-dark-400 uppercase tracking-wider">Submission Records ({appHistory.length})</h3>
          
          {appHistory.length > 0 ? (
            <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
              {appHistory.map((app) => (
                <div
                  key={app.id}
                  onClick={() => setSelectedApp(app)}
                  className={`glass-panel border rounded-xl p-4 cursor-pointer transition-all duration-200 text-xs ${
                    selectedApp?.id === app.id
                      ? 'border-indigo-500 bg-indigo-500/5 shadow-[0_0_12px_rgba(99,102,241,0.15)]'
                      : 'hover:border-dark-700 hover:bg-dark-900/40'
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <span className="font-extrabold text-dark-100 text-sm tracking-tight leading-tight">{app.job_title}</span>
                    <span className="px-2 py-0.5 bg-emerald-950/20 text-emerald-400 border border-emerald-500/20 rounded-md font-bold uppercase tracking-wider text-[8px]">
                      {app.status}
                    </span>
                  </div>
                  <p className="text-dark-300 font-semibold mt-1">{app.company}</p>
                  <div className="flex justify-between items-center pt-2.5 mt-2.5 border-t border-dark-850/40 text-[10px] text-dark-400">
                    <span>Logged: {app.applied_at ? app.applied_at.split(/[ T]/)[0] : 'Recently'}</span>
                    <span className="text-indigo-400 font-semibold">Click to expand →</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="glass-panel border rounded-xl p-8 text-center text-xs text-dark-400">
              No applications logged in history yet.
            </div>
          )}
        </div>

        {/* Right Side: Details View */}
        <div className="lg:col-span-2">
          {selectedApp ? (
            <div className="glass-panel border rounded-2xl p-6 space-y-6">
              {/* Header */}
              <div className="pb-4 border-b border-dark-800 flex justify-between items-start">
                <div>
                  <h3 className="text-lg font-bold text-dark-50">{selectedApp.job_title}</h3>
                  <p className="text-xs text-dark-300 font-semibold">{selectedApp.company}</p>
                </div>
                <div className="text-right">
                  <span className="text-[10px] text-dark-400 font-semibold block">Date: {selectedApp.applied_at}</span>
                  <span className="text-[10px] text-dark-400 font-semibold block mt-1">Status: <span className="text-emerald-400 font-bold uppercase">{selectedApp.status}</span></span>
                </div>
              </div>

              {/* Notes */}
              {selectedApp.notes && (
                <div className="bg-dark-950/40 p-4 rounded-xl border border-dark-850 text-xs">
                  <p className="font-bold text-dark-400 mb-1.5 uppercase tracking-wider text-[9px]">Submission Notes</p>
                  <p className="text-dark-200 italic">"{selectedApp.notes}"</p>
                </div>
              )}

              {/* Cover Letter */}
              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <h4 className="text-xs font-bold text-indigo-400 uppercase tracking-wider">Tailored Cover Letter</h4>
                  <button
                    onClick={() => handleCopyMaterial(selectedApp.cover_letter, 'Cover letter')}
                    className="text-[10px] text-indigo-400 hover:underline font-bold"
                  >
                    Copy Letter
                  </button>
                </div>
                <pre className="text-xs text-dark-350 bg-dark-950/40 p-4 rounded-xl border border-dark-850 max-h-60 overflow-y-auto whitespace-pre-wrap leading-relaxed font-sans">
                  {selectedApp.cover_letter}
                </pre>
              </div>

              {/* Resume Bullets */}
              {selectedApp.resume_bullets && selectedApp.resume_bullets.length > 0 && (
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <h4 className="text-xs font-bold text-indigo-400 uppercase tracking-wider">Tailored Resume Bullets</h4>
                    <button
                      onClick={() => handleCopyMaterial(selectedApp.resume_bullets.join('\n'), 'Resume bullets')}
                      className="text-[10px] text-indigo-400 hover:underline font-bold"
                    >
                      Copy All Bullets
                    </button>
                  </div>
                  <ul className="space-y-2.5 text-xs text-dark-300 bg-dark-950/40 p-4 rounded-xl border border-dark-850">
                    {selectedApp.resume_bullets.map((bullet, idx) => (
                      <li key={idx} className="flex items-start space-x-2">
                        <span className="text-indigo-400 font-bold select-none">•</span>
                        <span>{bullet}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="glass-panel border border-dashed border-dark-850 rounded-2xl p-16 text-center text-xs text-dark-400 flex flex-col justify-center items-center space-y-3 h-full min-h-[300px]">
              <span className="text-5xl">🧭</span>
              <p className="font-bold text-dark-200">Select an Application Record</p>
              <p className="max-w-xs">
                Choose an application entry from the list on the left to expand cover letters and resume bullets.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
export default ApplicationsHistory;
