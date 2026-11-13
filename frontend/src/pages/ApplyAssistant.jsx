import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useJobs } from '../hooks/useJobs';
import CoverLetterEditor from '../components/CoverLetterEditor';
import apiClient from '../api/client';
import toast from 'react-hot-toast';

export const ApplyAssistant = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { submitApplication, isSubmittingApp } = useJobs();

  const data = location.state;
  const job = data?.job;
  const pkg = data?.package;
  const [coverLetter, setCoverLetter] = useState(pkg?.cover_letter || '');
  const [resumeBullets, setResumeBullets] = useState(pkg?.resume_bullets || []);
  const [notes, setNotes] = useState('');
  const [tone, setTone] = useState('formal');
  const [versions, setVersions] = useState([]);
  const [selectedVersion, setSelectedVersion] = useState('');
  const [atsScore, setAtsScore] = useState(null);
  const [isGeneratingCoverLetter, setIsGeneratingCoverLetter] = useState(false);

  useEffect(() => {
    const fetchVersions = async () => {
      try {
        const res = await apiClient.get('/resume/versions');
        setVersions(res.data || []);
      } catch (err) {
        console.error(err);
      }
    };
    fetchVersions();
  }, []);

  useEffect(() => {
    const scoreResume = async () => {
      if (!job?.description) return;
      try {
        const res = await apiClient.post('/resume/ats/score', {
          job_description: job.description,
        });
        setAtsScore(res.data);
      } catch (err) {
        console.error(err);
      }
    };
    scoreResume();
  }, [job]);

  if (!data || !job || !pkg) {
    return (
      <div className="max-w-md mx-auto px-4 py-16 text-center space-y-4">
        <span className="text-5xl">🧭</span>
        <h2 className="text-xl font-bold text-dark-100">No Tailored Data Found</h2>
        <p className="text-xs text-dark-400">
          Please select a job listing from the vector skill matcher and trigger application tailoring.
        </p>
        <Link
          to="/match"
          className="inline-block px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-xs transition-all shadow"
        >
          Go to Matcher
        </Link>
      </div>
    );
  }

  const handleToneCoverLetter = async () => {
    setIsGeneratingCoverLetter(true);
    const loadingToast = toast.loading(`Generating ${tone} cover letter...`);
    try {
      const res = await apiClient.post('/resume/cover-letter', {
        target_role: job.title,
        company_name: job.company,
        tone,
      });
      setCoverLetter(res.data.cover_letter);
      toast.success('Cover letter refreshed.', { id: loadingToast });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Unable to regenerate cover letter.', { id: loadingToast });
    } finally {
      setIsGeneratingCoverLetter(false);
    }
  };

  const handleSelectVersion = async (versionId) => {
    try {
      await apiClient.post(`/resume/select-version?version_id=${versionId}`);
      setSelectedVersion(versionId);
      toast.success('Resume version selected for this application.');
    } catch (err) {
      toast.error('Unable to switch resume version.');
    }
  };

  const handleSaveBullet = (idx, text) => {
    const updated = [...resumeBullets];
    updated[idx] = text;
    setResumeBullets(updated);
  };

  const handleCopyBullets = async () => {
    try {
      const text = resumeBullets.map(b => `- ${b}`).join('\n');
      await navigator.clipboard.writeText(text);
      toast.success('Tailored bullets copied to clipboard!');
    } catch (err) {
      toast.error('Failed to copy text.');
    }
  };

  const handleSubmitApplicationLog = async () => {
    const loadingToast = toast.loading('Logging application to database...');
    try {
      await submitApplication({
        job_id: job.id,
        company: job.company,
        title: job.title,
        location: job.location,
        job_url: job.job_url,
        cover_letter: coverLetter,
        resume_bullets: resumeBullets,
        notes: notes || 'Applied via AI Powered Assistance Platform',
        tone,
        resume_version_id: selectedVersion || undefined,
      });
      toast.success('Application logged successfully!', { id: loadingToast });
      navigate('/applications');
    } catch (err) {
      toast.error('Failed to log application.', { id: loadingToast });
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Header */}
      <div className="pb-4 border-b border-dark-800 flex justify-between items-start gap-4 flex-col sm:flex-row">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-dark-50">Application Customization Suite</h1>
          <p className="text-xs text-dark-400 mt-1">
            Review and adjust AI-tailored items for <span className="text-indigo-400 font-bold">{job.title}</span> at <span className="font-semibold text-dark-200">{job.company}</span>.
          </p>
        </div>
        
        <Link
          to="/match"
          className="px-4 py-2 border border-dark-800 hover:bg-dark-800 text-dark-100 text-xs font-bold rounded-xl transition-all"
        >
          Back to Matcher
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left column: bullets & logging metadata */}
        <div className="lg:col-span-1 space-y-6">
          {/* Suggested Subject */}
          <div className="glass-panel border rounded-2xl p-5 space-y-2">
            <h4 className="text-xs font-bold text-indigo-400 uppercase tracking-wider">Suggested Email Subject</h4>
            <div className="p-3 bg-dark-950/50 rounded-xl border border-dark-800 text-xs font-semibold text-dark-100 break-words select-all">
              {pkg.suggested_subject_line}
            </div>
          </div>

          {/* ATS Score */}
          {atsScore && (
            <div className="glass-panel border rounded-2xl p-5 space-y-3">
              <h4 className="text-xs font-bold text-amber-400 uppercase tracking-wider">ATS Compatibility</h4>
              <div className="text-3xl font-black text-dark-50">{atsScore.overall_score}%</div>
              <p className="text-[11px] text-dark-400 leading-relaxed">{atsScore.recommendation}</p>
              <div className="text-[10px] text-dark-500">{atsScore.suggestions}</div>
            </div>
          )}

          {/* Resume Version Selector */}
          <div className="glass-panel border rounded-2xl p-5 space-y-3">
            <h4 className="text-xs font-bold text-cyan-400 uppercase tracking-wider">Resume Version</h4>
            <select
              value={selectedVersion}
              onChange={(e) => handleSelectVersion(e.target.value)}
              className="w-full px-3 py-2 bg-dark-950 border border-dark-800 rounded-xl text-xs text-dark-100"
            >
              <option value="">Use latest uploaded resume</option>
              {versions.map((version) => (
                <option key={version.id} value={version.id}>{version.version_label}</option>
              ))}
            </select>
          </div>

          {/* Tone Selector */}
          <div className="glass-panel border rounded-2xl p-5 space-y-3">
            <h4 className="text-xs font-bold text-fuchsia-400 uppercase tracking-wider">Cover Letter Tone</h4>
            <select
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              className="w-full px-3 py-2 bg-dark-950 border border-dark-800 rounded-xl text-xs text-dark-100"
            >
              <option value="formal">Formal</option>
              <option value="conversational">Conversational</option>
              <option value="enthusiastic">Enthusiastic</option>
            </select>
            <button
              onClick={handleToneCoverLetter}
              disabled={isGeneratingCoverLetter}
              className="w-full py-2 bg-fuchsia-600 hover:bg-fuchsia-500 text-white font-bold rounded-xl text-xs transition-all"
            >
              {isGeneratingCoverLetter ? 'Generating...' : 'Refresh Cover Letter'}
            </button>
          </div>

          {/* Tailored Bullets */}
          <div className="glass-panel border rounded-2xl p-5 space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-dark-850">
              <h4 className="text-xs font-bold text-indigo-400 uppercase tracking-wider">Tailored Resume Bullets</h4>
              <button 
                onClick={handleCopyBullets}
                className="text-[10px] text-indigo-400 hover:underline font-bold"
              >
                Copy All
              </button>
            </div>
            
            <p className="text-[11px] text-dark-400 leading-relaxed">
              Integrate these bullets under the relevant experiences in your master resume to pass applicant filter algorithms.
            </p>

            <div className="space-y-3">
              {resumeBullets.map((bullet, idx) => (
                <div key={idx} className="space-y-1 text-xs">
                  <span className="text-dark-500 font-semibold">Bullet Point #{idx + 1}</span>
                  <textarea
                    value={bullet}
                    onChange={(e) => handleSaveBullet(idx, e.target.value)}
                    className="w-full bg-dark-950 border border-dark-800 focus:border-indigo-500/40 rounded-xl p-2 text-xs text-dark-200 focus:outline-none transition-all h-20 resize-none"
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Mark as Applied Form */}
          <div className="glass-panel border rounded-2xl p-5 space-y-4">
            <h4 className="text-xs font-bold text-emerald-400 uppercase tracking-wider">Application submission logging</h4>
            
            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-xs font-semibold text-dark-300 mb-1.5">Submission Notes (Optional)</label>
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="w-full px-3 py-2 bg-dark-950 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-dark-100 focus:outline-none transition-all"
                  placeholder="e.g. Applied via corporate portal"
                />
              </div>

              <button
                onClick={handleSubmitApplicationLog}
                disabled={isSubmittingApp}
                className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl text-xs transition-all shadow disabled:opacity-50"
              >
                {isSubmittingApp ? 'Logging...' : 'Mark as Applied'}
              </button>
            </div>
          </div>
        </div>

        {/* Right column: cover letter customizer */}
        <div className="lg:col-span-2">
          <CoverLetterEditor 
            initialValue={coverLetter} 
            onSave={(text) => {
              setCoverLetter(text);
              toast.success('Cover letter edits saved locally.');
            }}
          />
        </div>
      </div>
    </div>
  );
};
export default ApplyAssistant;
