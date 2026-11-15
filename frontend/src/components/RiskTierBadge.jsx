import React from 'react';

export const RiskTierBadge = ({ riskTier }) => {
  switch (riskTier) {
    case 'read_only':
      return (
        <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center space-x-1 inline-flex">
          <span>📖</span>
          <span>Read-Only</span>
        </span>
      );
    case 'write_internal':
      return (
        <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/30 flex items-center space-x-1 inline-flex">
          <span>✍️</span>
          <span>Internal Write</span>
        </span>
      );
    case 'external_action':
      return (
        <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/40 flex items-center space-x-1 inline-flex">
          <span>⚡</span>
          <span>External Action</span>
        </span>
      );
    default:
      return (
        <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-dark-800 text-dark-400 border border-dark-700 inline-flex">
          {riskTier || 'Unknown'}
        </span>
      );
  }
};

export const ApprovalStatusBadge = ({ status }) => {
  switch (status) {
    case 'AWAITING_APPROVAL':
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-amber-500/20 text-amber-300 border border-amber-500/50 animate-pulse inline-flex items-center space-x-1">
          <span>⏳</span>
          <span>Awaiting Approval</span>
        </span>
      );
    case 'AUTO_APPROVED':
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 inline-flex items-center space-x-1">
          <span>🤖</span>
          <span>Auto-Approved</span>
        </span>
      );
    case 'USER_APPROVED':
    case 'APPROVED':
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 inline-flex items-center space-x-1">
          <span>✓</span>
          <span>User Approved</span>
        </span>
      );
    case 'REJECTED':
      return (
        <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-red-500/20 text-red-300 border border-red-500/40 inline-flex items-center space-x-1">
          <span>✕</span>
          <span>Rejected</span>
        </span>
      );
    default:
      return null;
  }
};

export default RiskTierBadge;
