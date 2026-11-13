import React from 'react';
import { useQuery } from '@tanstack/react-query';
import client from '../api/client';

const ModelSelector = () => {
  // Query Ollama status from backend
  const { data: availableData, isLoading } = useQuery({
    queryKey: ['llmAvailableModels'],
    queryFn: async () => {
      const response = await client.get('/llm/available-models');
      return response.data;
    },
    refetchInterval: 30000,
  });

  const canonicalModel = 'qwen3:14b';
  const isModelDetected = availableData?.models?.some(
    (m) => m.name === canonicalModel || m.name?.startsWith(canonicalModel)
  );

  return (
    <div className="glass-panel border border-dark-800 rounded-2xl p-6 shadow-xl space-y-6">
      <div className="flex items-center justify-between pb-4 border-b border-dark-800">
        <div>
          <span className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-400 font-mono">
            Privacy-Preserving Inference
          </span>
          <h2 className="text-xl font-bold text-dark-50 mt-1">AI Engine Status</h2>
        </div>
        <div className="flex items-center space-x-2">
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
            isModelDetected 
              ? 'bg-emerald-950/40 text-emerald-400 border border-emerald-500/20' 
              : 'bg-indigo-950/40 text-indigo-400 border border-indigo-500/20'
          }`}>
            <span className={`w-1.5 h-1.5 mr-1.5 rounded-full ${isModelDetected ? 'bg-emerald-400 animate-pulse' : 'bg-indigo-400'}`} />
            {isLoading ? 'Checking...' : isModelDetected ? 'Operational' : 'Local Inference Ready'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Active AI Engine Card */}
        <div className="bg-dark-900/50 border border-dark-800/80 rounded-xl p-4 space-y-1">
          <span className="text-[10px] uppercase font-bold text-dark-400 tracking-wider">
            Active AI Engine
          </span>
          <div className="text-lg font-bold text-dark-100 flex items-center space-x-2">
            <span>Local Ollama</span>
            <span className="text-xs bg-indigo-950/60 text-indigo-400 border border-indigo-500/20 px-2 py-0.5 rounded-md font-semibold">
              Privacy Enforced
            </span>
          </div>
          <p className="text-xs text-dark-400 leading-relaxed pt-1">
            Zero external telemetry or cloud LLM calls. All reasoning runs entirely on your local machine.
          </p>
        </div>

        {/* Model Specification Card */}
        <div className="bg-dark-900/50 border border-dark-800/80 rounded-xl p-4 space-y-1">
          <span className="text-[10px] uppercase font-bold text-dark-400 tracking-wider">
            Model
          </span>
          <div className="text-lg font-bold text-emerald-400 font-mono flex items-center space-x-2">
            <span>qwen3:14b</span>
            <span className="text-xs bg-emerald-950/60 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded-md font-semibold font-sans">
              Locked
            </span>
          </div>
          <p className="text-xs text-dark-400 leading-relaxed pt-1">
            Canonical 14B parameter quantized model optimized for resume parsing, ATS scoring, and interview intelligence.
          </p>
        </div>
      </div>

      <div className="bg-dark-950/40 border border-dark-850 rounded-xl p-4 text-xs text-dark-300 space-y-2">
        <div className="flex items-center space-x-2 text-dark-200 font-semibold">
          <svg className="w-4 h-4 text-indigo-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <span>Architecture Restriction Notice</span>
        </div>
        <p className="leading-relaxed text-dark-400">
          In accordance with AI-Powered Assistance Platform data privacy and governance policy, external LLM APIs (OpenAI, Gemini, Claude) and unapproved third-party models are strictly disabled. The platform exclusively executes <code className="text-indigo-300 font-mono bg-dark-900 px-1.5 py-0.5 rounded">qwen3:14b</code> via local Ollama.
        </p>
      </div>
    </div>
  );
};

export default ModelSelector;
