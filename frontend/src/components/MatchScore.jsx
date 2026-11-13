import React from 'react';

export const MatchScore = ({ score }) => {
  const getScoreColor = (val) => {
    if (val >= 80) return 'text-emerald-400 border-emerald-500/30 bg-emerald-950/20';
    if (val >= 50) return 'text-amber-400 border-amber-500/30 bg-amber-950/20';
    return 'text-red-400 border-red-500/30 bg-red-950/20';
  };

  const getProgressColor = (val) => {
    if (val >= 80) return 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]';
    if (val >= 50) return 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]';
    return 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]';
  };

  return (
    <div className="flex flex-col space-y-1.5 w-full">
      <div className="flex justify-between items-center text-xs font-semibold">
        <span className="text-dark-400 uppercase tracking-wider">Semantic Match</span>
        <span className={`px-2 py-0.5 rounded-full border text-xs font-bold ${getScoreColor(score)}`}>
          {score}% Match
        </span>
      </div>
      
      {/* Progress Bar container */}
      <div className="h-2 bg-dark-900 rounded-full w-full overflow-hidden border border-dark-800">
        <div 
          className={`h-full rounded-full transition-all duration-1000 ${getProgressColor(score)}`}
          style={{ width: `${score}%` }}
        ></div>
      </div>
    </div>
  );
};
export default MatchScore;
