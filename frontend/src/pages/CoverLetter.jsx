import React, { useState } from 'react';
import { useLocation, Link } from 'react-router-dom';
import CoverLetterEditor from '../components/CoverLetterEditor';
import apiClient from '../api/client';
import toast from 'react-hot-toast';

export const CoverLetter = () => {
  const location = useLocation();

  const data = location.state;
  const [coverLetter, setCoverLetter] = useState(data?.cover_letter || '');
  const [isRegenerating, setIsRegenerating] = useState(false);

  if (!data || !data.target_role) {
    return (
      <div className="max-w-md mx-auto px-4 py-16 text-center space-y-4">
        <span className="text-5xl">🧭</span>
        <h2 className="text-xl font-bold text-dark-100">No Cover Letter Context</h2>
        <p className="text-xs text-dark-400">
          We need a target job context to generate cover letters. Run skill diagnostics first.
        </p>
        <Link
          to="/upload"
          className="inline-block px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-xs transition-all shadow"
        >
          Go to Diagnostics
        </Link>
      </div>
    );
  }

  const { target_role } = data;

  const handleRegenerate = async (tone) => {
    setIsRegenerating(true);
    const loadingToast = toast.loading(`Drafting cover letter in ${tone} tone...`);
    try {
      const response = await apiClient.post('/resume/cover-letter', {
        target_role,
        tone
      });
      setCoverLetter(response.data.cover_letter);
      toast.success('Cover letter updated!', { id: loadingToast });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to regenerate cover letter.', { id: loadingToast });
    } finally {
      setIsRegenerating(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Title */}
      <div className="pb-4 border-b border-dark-800 flex justify-between items-center">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-dark-50">General Cover Letter Draft</h1>
          <p className="text-xs text-dark-400 mt-1">Generated for: <span className="text-indigo-400 font-bold">{target_role}</span></p>
        </div>
        
        <Link
          to="/match"
          className="px-4 py-2 border border-dark-800 hover:bg-dark-800 text-dark-100 text-xs font-bold rounded-xl transition-all"
        >
          View Matched Jobs
        </Link>
      </div>

      {/* Editor Box */}
      <CoverLetterEditor 
        initialValue={coverLetter} 
        onRegenerate={handleRegenerate}
        isRegenerating={isRegenerating}
      />
    </div>
  );
};
export default CoverLetter;
