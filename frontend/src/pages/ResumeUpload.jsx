import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useResume } from '../hooks/useResume';
import { useProfile } from '../hooks/useProfile';
import FileDropzone from '../components/FileDropzone';
import { LoadingSpinner } from '../components/LoadingSpinner';
import toast from 'react-hot-toast';
import apiClient from '../api/client';

export const ResumeUpload = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { uploadResume, isUploading, analyzeResume, isAnalyzing, pollJobStatus } = useResume();
  const { profile, isLoading: isLoadingProfile, refetch } = useProfile();

  const [targetRole, setTargetRole] = useState('');
  const [extractedPreview, setExtractedPreview] = useState('');
  const [_analyzingText, setAnalyzingText] = useState('');
  const [pollingJobId, setPollingJobId] = useState(null);
  const [suggestedRoles, setSuggestedRoles] = useState([]);
  const [isSuggestingRoles, setIsSuggestingRoles] = useState(false);

  // If URL has analyze=true, auto-focus target role
  useEffect(() => {
    if (searchParams.get('analyze') === 'true' && profile) {
      // Focus element
      const el = document.getElementById('target-role-input');
      if (el) el.focus();
    }
  }, [searchParams, profile]);

  const handleFileUpload = async (file) => {
    const loadingToast = toast.loading('Uploading and extracting resume...');
    try {
      const response = await uploadResume(file);
      toast.success('Resume parsed! Detecting best roles...', { id: loadingToast });
      setExtractedPreview(response.text_preview);
      refetch();
      
      // Auto-fetch role suggestions
      setIsSuggestingRoles(true);
      try {
        const rolesRes = await apiClient.post('/resume/suggest-roles');
        setSuggestedRoles(rolesRes.data.suggested_roles || []);
      } catch {
        // ignore, user can still type manually
      } finally {
        setIsSuggestingRoles(false);
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to parse resume.', { id: loadingToast });
    }
  };

  const handleAnalyze = async (e) => {
    e.preventDefault();
    if (!targetRole.trim()) {
      toast.error('Please enter a target role.');
      return;
    }
    
    setAnalyzingText('Connecting to Local Ollama & analyzing gaps...');
    try {
      const response = await analyzeResume({ target_role: targetRole });
      const { job_id } = response;
      setPollingJobId(job_id);
      
      // Start polling status
      pollJobStatus(
        job_id,
        (_result) => {
          // Success Callback
          toast.success('Skill gap analysis complete!');
          setPollingJobId(null);
          setAnalyzingText('');
          // Redirect to Job Board page
          navigate('/jobs');
        },
        (errorMsg) => {
          // Failure Callback
          toast.error(errorMsg || 'Analysis failed.');
          setPollingJobId(null);
          setAnalyzingText('');
        }
      );
    } catch (error) {
      toast.error(error.message || 'Error triggering analysis.');
      setAnalyzingText('');
    }
  };

  if (isLoadingProfile) {
    return <LoadingSpinner text="Retrieving profile status..." />;
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8 relative">
      {/* Loading overlay for Ollama task */}
      {pollingJobId && (
        <div className="absolute inset-0 bg-dark-950/80 backdrop-blur-md z-50 flex items-center justify-center rounded-3xl">
          <div className="text-center space-y-4 max-w-sm p-6 bg-dark-900 border border-dark-800 rounded-2xl shadow-2xl">
            <LoadingSpinner size="lg" text="" />
            <h3 className="text-lg font-bold text-dark-100 animate-pulse">Running Local AI Analysis</h3>
            <p className="text-xs text-dark-400 leading-relaxed">
              Ollama is computing a skill-gap matrix and drafting cover letters using Qwen3:14b. This can take 10-40 seconds...
            </p>
          </div>
        </div>
      )}

      {/* Title */}
      <div>
        <h1 className="text-2xl md:text-3xl font-extrabold text-dark-50">Career Profile Builder</h1>
        <p className="text-xs text-dark-400 mt-1">Upload and analyze your resume to build a private knowledge vector profile.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Upload Column */}
        <div className="glass-panel border rounded-2xl p-6 space-y-6">
          <h3 className="text-md font-bold text-dark-100">Step 1: Document Upload</h3>
          <p className="text-xs text-dark-400 leading-relaxed">
            We support PDF and DOCX files. The text will be extracted, cleaned, and categorized in a local vector database.
          </p>
          
          <FileDropzone onFileSelect={handleFileUpload} isUploading={isUploading} />
          
          {isUploading && <LoadingSpinner text="Uploading resume..." />}
          
          {profile && !isUploading && (
            <div className="mt-4 p-4 bg-emerald-950/20 border border-emerald-500/20 rounded-xl flex items-center space-x-3 text-xs text-emerald-400">
              <span>✓</span>
              <span>An active resume is uploaded and indexed. You can re-upload to overwrite.</span>
            </div>
          )}
        </div>

        {/* Analyze Column */}
        <div className="glass-panel border rounded-2xl p-6 space-y-6 flex flex-col justify-between">
          <div className="space-y-4">
            <h3 className="text-md font-bold text-dark-100">Step 2: Skill Diagnostics</h3>
            <p className="text-xs text-dark-400 leading-relaxed">
              Enter your target job role. Ollama will compare your skills against industry standards for that role to calculate gaps and draft a cover letter.
            </p>

            <form onSubmit={handleAnalyze} className="space-y-4">
              {isSuggestingRoles && <p className="text-xs text-dark-400">Detecting best roles for you...</p>}

              {suggestedRoles.length > 0 && (
                <div>
                  <p className="text-xs text-dark-400 mb-2">AI-suggested roles — pick one or type your own:</p>
                  <div className="flex flex-wrap gap-2">
                    {suggestedRoles.map((role) => (
                      <button
                        key={role}
                        type="button"
                        onClick={() => setTargetRole(role)}
                        className={`px-3 py-1 rounded-full text-xs border transition-colors ${
                          targetRole === role
                            ? 'bg-indigo-600 border-indigo-500 text-white'
                            : 'border-dark-600 text-dark-300 hover:border-indigo-400'
                        }`}
                      >
                        {role}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-dark-300 mb-1.5">Target Job Role</label>
                <input
                  id="target-role-input"
                  type="text"
                  required
                  disabled={!profile || isAnalyzing}
                  value={targetRole}
                  onChange={(e) => setTargetRole(e.target.value)}
                  className="w-full px-4 py-2.5 bg-dark-950 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-sm text-dark-100 focus:outline-none transition-all disabled:opacity-50"
                  placeholder="e.g. Frontend Engineer, Data Scientist"
                />
              </div>

              <button
                type="submit"
                disabled={!profile || isAnalyzing}
                className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 disabled:bg-dark-800 disabled:text-dark-500 text-white font-bold rounded-xl text-xs transition-all flex justify-center items-center shadow-md"
              >
                {isAnalyzing ? 'Connecting Ollama...' : 'Trigger Skill Gap Diagnostics'}
              </button>
            </form>
          </div>

          {!profile && (
            <div className="p-3 bg-dark-950 border border-dark-900 rounded-xl text-xs text-dark-400 text-center">
              Please complete Step 1 before running diagnostics.
            </div>
          )}
        </div>
      </div>

      {/* Extracted Preview Panel */}
      {extractedPreview && (
        <div className="glass-panel border rounded-2xl p-6 space-y-3">
          <h3 className="text-md font-bold text-dark-100">Extracted Document Preview</h3>
          <pre className="text-xs text-dark-300 bg-dark-950/50 p-4 rounded-xl border border-dark-800/60 max-h-60 overflow-y-auto whitespace-pre-wrap leading-relaxed font-sans">
            {extractedPreview}
          </pre>
        </div>
      )}
    </div>
  );
};
export default ResumeUpload;
