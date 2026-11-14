import React, { useState } from 'react';
import apiClient from '../api/client';
import toast from 'react-hot-toast';

export const PendingApprovalCard = ({ workflowId, pendingTask, onActionComplete }) => {
  const [loadingAction, setLoadingAction] = useState(null); // 'approve' | 'reject' | null

  if (!pendingTask) return null;

  const handleApprove = async () => {
    setLoadingAction('approve');
    try {
      await apiClient.post(`/orchestrator/workflows/${workflowId}/approve`, {
        task_id: pendingTask.task_id
      });
      toast.success('External action approved! Resuming workflow...');
      if (onActionComplete) onActionComplete(workflowId, 'approved');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to approve task.');
    } finally {
      setLoadingAction(null);
    }
  };

  const handleReject = async () => {
    setLoadingAction('reject');
    try {
      await apiClient.post(`/orchestrator/workflows/${workflowId}/reject`, {
        task_id: pendingTask.task_id
      });
      toast.success('Task rejected. Workflow cancelled.');
      if (onActionComplete) onActionComplete(workflowId, 'rejected');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to reject task.');
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <div className="glass-panel border-2 border-amber-500/40 rounded-2xl p-5 shadow-2xl bg-amber-950/20 space-y-4 my-4 animate-fade-in">
      <div className="flex items-start justify-between gap-3 pb-3 border-b border-amber-500/20">
        <div className="flex items-center space-x-2">
          <span className="text-xl animate-bounce">✋</span>
          <div>
            <h3 className="text-sm font-bold text-amber-200">
              Human-in-the-Loop Approval Required
            </h3>
            <p className="text-[11px] text-amber-400/80">
              The agent wants to perform an external action with real-world side effects.
            </p>
          </div>
        </div>
        <span className="px-2.5 py-1 rounded-full text-[10px] font-extrabold uppercase bg-amber-500/20 text-amber-300 border border-amber-500/40 tracking-wider">
          External Action
        </span>
      </div>

      <div className="space-y-2 bg-dark-900/60 p-3.5 rounded-xl border border-amber-500/20">
        <div className="text-xs font-semibold text-dark-100 flex items-center space-x-2">
          <span className="text-dark-400">Action:</span>
          <span className="font-mono text-amber-300">{pendingTask.task_type}</span>
        </div>
        <div className="text-xs text-dark-200 font-medium leading-relaxed">
          {pendingTask.summary || pendingTask.description}
        </div>
        {pendingTask.input && Object.keys(pendingTask.input).length > 0 && (
          <div className="mt-2 text-[11px] text-dark-400 font-mono bg-dark-950/80 p-2 rounded border border-dark-800 overflow-x-auto">
            {JSON.stringify(pendingTask.input, null, 2)}
          </div>
        )}
      </div>

      <div className="flex items-center justify-end space-x-3 pt-1">
        <button
          onClick={handleReject}
          disabled={loadingAction !== null}
          className="px-4 py-2 rounded-xl border border-red-500/40 bg-red-500/10 hover:bg-red-500/20 text-red-300 text-xs font-bold transition shadow-sm disabled:opacity-50"
        >
          {loadingAction === 'reject' ? 'Rejecting...' : '✕ Reject Action'}
        </button>
        <button
          onClick={handleApprove}
          disabled={loadingAction !== null}
          className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition shadow-lg disabled:opacity-50 flex items-center space-x-1.5"
        >
          <span>✓</span>
          <span>{loadingAction === 'approve' ? 'Approving...' : 'Approve & Execute'}</span>
        </button>
      </div>
    </div>
  );
};

export default PendingApprovalCard;
