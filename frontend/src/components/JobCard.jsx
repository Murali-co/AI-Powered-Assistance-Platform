import React, { useState } from 'react';
import MatchScore from './MatchScore';
import { getSafeExternalUrl } from '../utils/urlSecurity';

const JOB_TYPE_STYLES = {
  remote: 'bg-emerald-900/30 text-emerald-400 border-emerald-500/20',
  hybrid: 'bg-amber-900/30 text-amber-400 border-amber-500/20',
  onsite: 'bg-blue-900/30 text-blue-400 border-blue-500/20',
};

const JOB_TYPE_LABELS = {
  remote: '🏠 Remote',
  hybrid: '🔄 Hybrid',
  onsite: '🏢 On-site',
};

export const JobCard = ({
  job,
  onAction,
  actionLabel = 'Generate Application',
  onExplain,
  explainLabel = 'Explain Match',
  onSave,
  showApplyLink = false,
}) => {
  const [expanded, setExpanded] = useState(false);

  if (!job || typeof job !== 'object') {
    return null;
  }

  const jobData = job;
  const rawJobType = typeof jobData.job_type === 'string' ? jobData.job_type : 'onsite';
  const jobType = rawJobType.toLowerCase();

  const formatSourceBadge = (src) => {
    const srcLower = (src || '').toLowerCase();
    if (srcLower.includes('linkedin')) return 'bg-blue-900/30 text-blue-400 border-blue-500/20';
    if (srcLower.includes('indeed')) return 'bg-indigo-900/30 text-indigo-400 border-indigo-500/20';
    if (srcLower.includes('glassdoor')) return 'bg-emerald-900/30 text-emerald-400 border-emerald-500/20';
    if (srcLower.includes('naukri')) return 'bg-orange-900/30 text-orange-400 border-orange-500/20';
    if (srcLower.includes('adzuna')) return 'bg-violet-900/30 text-violet-400 border-violet-500/20';
    return 'bg-dark-900 text-dark-400 border-dark-800';
  };

  const formatPostedAge = (postedAt) => {
    if (!postedAt || postedAt === 'Recently') return 'Recently';
    try {
      const posted = new Date(postedAt);
      const now = new Date();
      const diffMs = now - posted;
      if (Number.isNaN(diffMs)) return String(postedAt).split(' ')[0] || 'Recently';
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
      if (diffHours < 1) return 'Just now';
      if (diffHours < 24) return `${diffHours}h ago`;
      const diffDays = Math.floor(diffHours / 24);
      if (diffDays === 1) return '1 day ago';
      if (diffDays < 7) return `${diffDays} days ago`;
      if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
      return `${Math.floor(diffDays / 30)}mo ago`;
    } catch {
      return String(postedAt).split(' ')[0] || 'Recently';
    }
  };

  const matchedSkillsList = Array.isArray(jobData.matched_skills) ? jobData.matched_skills : [];
  const missingSkillsList = Array.isArray(jobData.missing_skills) ? jobData.missing_skills : [];
  const hasMatchScore = jobData.match_score !== undefined && jobData.match_score !== null;

  return (
    <div className="glass-panel glass-card-hover rounded-2xl p-5 border flex flex-col space-y-4">
      {/* Header section */}
      <div className="flex justify-between items-start">
        <div className="space-y-1.5 flex-1 min-w-0">
          {/* Badges row */}
          <div className="flex flex-wrap gap-1.5">
            <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full border ${formatSourceBadge(jobData.source)}`}>
              {jobData.source || 'Direct'}
            </span>
            <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full border ${JOB_TYPE_STYLES[jobType] || JOB_TYPE_STYLES.onsite}`}>
              {JOB_TYPE_LABELS[jobType] || '🏢 On-site'}
            </span>
          </div>
          <h3 className="text-lg font-bold text-dark-50 tracking-tight leading-tight">
            {jobData.title || jobData.job_title || 'Untitled Role'}
          </h3>
          <p className="text-dark-300 font-semibold text-sm">
            {jobData.company || jobData.company_name || 'Unknown Company'} — <span className="text-dark-400 font-medium text-xs">{jobData.location || 'Location Not Specified'}</span>
          </p>
        </div>

        <div className="flex flex-col items-end space-y-1.5 ml-3 shrink-0">
          {jobData.posted_at && (
            <span className="text-[10px] font-medium text-dark-400 whitespace-nowrap">
              {formatPostedAge(jobData.posted_at)}
            </span>
          )}
        </div>
      </div>

      {/* Match Score & Skills */}
      {hasMatchScore && (
        <div className="space-y-3 pt-1">
          <MatchScore score={jobData.match_score} />

          <div className="flex flex-wrap gap-1.5 pt-1">
            {matchedSkillsList.map((skill) => (
              <span key={skill} className="text-[10px] font-semibold px-2 py-0.5 bg-emerald-950/30 text-emerald-400 border border-emerald-500/10 rounded-md">
                ✓ {skill}
              </span>
            ))}
            {missingSkillsList.map((skill) => (
              <span key={skill} className="text-[10px] font-semibold px-2 py-0.5 bg-red-950/30 text-red-400 border border-red-500/10 rounded-md">
                + {skill}
              </span>
            ))}
          </div>

          {missingSkillsList.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2 rounded-xl border border-amber-500/20 bg-amber-950/15 px-2.5 py-2">
                <span className="text-[10px] text-amber-300 font-semibold">
                  Learn these skills
                </span>
                <a
                  href="https://www.coursera.org/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] font-bold text-amber-200 hover:text-amber-100"
                >
                  Learn ↗
                </a>
              </div>
              <button
                type="button"
                className="w-full px-3 py-2 border border-emerald-500/30 bg-emerald-900/20 text-emerald-300 rounded-xl text-[10px] font-bold"
              >
                Apply after learning
              </button>
            </div>
          )}
        </div>
      )}

      {/* Expanded Accordion Description */}
      {expanded && (
        <div className="pt-2 border-t border-dark-800/60 text-xs text-dark-300 leading-relaxed max-h-48 overflow-y-auto whitespace-pre-line pr-2 bg-dark-950/20 p-3 rounded-xl">
          {jobData.description || 'No detailed description provided for this job listing.'}
        </div>
      )}

      {/* Buttons */}
      <div className="flex justify-between items-center pt-2 gap-3">
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-indigo-400 hover:text-indigo-300 font-bold transition-all"
        >
          {expanded ? 'Hide Description' : 'View Description'}
        </button>

        <div className="flex items-center space-x-2">
          {/* Save Button */}
          {onSave && (
            <button
              type="button"
              onClick={onSave}
              className="px-3 py-2 border border-dark-800 hover:bg-dark-800 text-dark-200 rounded-xl text-xs font-bold transition-all"
              title="Save Job"
            >
              💾 Save
            </button>
          )}

          {/* Apply Link (safe protocol and rel="noopener noreferrer") */}
          {(() => {
            const safeApplyUrl = getSafeExternalUrl(jobData.url);
            return showApplyLink && safeApplyUrl ? (
              <a
                href={safeApplyUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3.5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition-all shadow-sm"
              >
                Apply ↗
              </a>
            ) : null;
          })()}

          {/* Explain Button */}
          {onExplain && (
            <button
              type="button"
              onClick={() => onExplain(jobData)}
              className="px-3.5 py-2 border border-dark-800 hover:bg-dark-800 text-dark-200 rounded-xl text-xs font-bold transition-all"
            >
              {explainLabel}
            </button>
          )}

          {/* Generate Application Button */}
          {onAction && (
            <button
              type="button"
              onClick={() => onAction(jobData)}
              className="px-4 py-2 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white rounded-xl text-xs font-bold transition-all duration-300 shadow-[0_4px_12px_rgba(99,102,241,0.2)]"
            >
              {actionLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
export default JobCard;
