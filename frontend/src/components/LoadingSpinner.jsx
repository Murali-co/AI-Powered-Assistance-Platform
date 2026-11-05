import React from 'react';

export const LoadingSpinner = ({ size = 'md', text = 'Loading...' }) => {
  const sizeClasses = {
    sm: 'w-5 h-5 border-2',
    md: 'w-8 h-8 border-3',
    lg: 'w-12 h-12 border-4',
  };

  return (
    <div className="flex flex-col items-center justify-center p-6 space-y-3">
      <div className={`${sizeClasses[size]} rounded-full border-t-indigo-500 border-r-transparent border-b-indigo-500 border-l-transparent animate-spin`}></div>
      {text && <p className="text-dark-400 text-sm font-medium animate-pulse">{text}</p>}
    </div>
  );
};

export const SkeletonLoader = ({ rows = 3 }) => {
  return (
    <div className="w-full space-y-3 animate-pulse p-4 glass-panel rounded-xl">
      <div className="h-6 bg-dark-800 rounded-md w-1/4"></div>
      <div className="space-y-2">
        {[...Array(rows)].map((_, idx) => (
          <div key={idx} className="h-4 bg-dark-800 rounded-md w-full"></div>
        ))}
      </div>
    </div>
  );
};
