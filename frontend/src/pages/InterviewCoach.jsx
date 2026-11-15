import React, { useState, useEffect, useRef } from 'react';
import { useProfile } from '../hooks/useProfile';
import { useJobs } from '../hooks/useJobs';
import { LoadingSpinner } from '../components/LoadingSpinner';
import apiClient from '../api/client';
import toast from 'react-hot-toast';

export const InterviewCoach = () => {
  const { profile, hasProfile, isLoading: isLoadingProfile } = useProfile();
  const { matchedJobs } = useJobs();

  // Staging / Setup States
  const [isStaging, setIsStaging] = useState(true);
  const [focusType, setFocusType] = useState('general'); // general | role | job
  const [targetRole, setTargetRole] = useState('');
  const [selectedJobId, setSelectedJobId] = useState('');
  const [interviewMode, setInterviewMode] = useState('mixed'); // technical | behavioral | project-based | mixed
  const [initialDifficulty, setInitialDifficulty] = useState(3);

  // Active Session State
  const [session, setSession] = useState(null);
  const [answer, setAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGeneratingStart, setIsGeneratingStart] = useState(false);

  // Scaffolding Hint State
  const [activeHint, setActiveHint] = useState(null);
  const [isLoadingHint, setIsLoadingHint] = useState(false);

  // Turn Feedback State (shows immediately after each response before advancing)
  const [turnFeedback, setTurnFeedback] = useState(null);

  // Report Card State
  const [report, setReport] = useState(null);
  const [isLoadingReport, setIsLoadingReport] = useState(false);

  // Voice Interaction State (Web Speech API)
  const [isListening, setIsListening] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const recognitionRef = useRef(null);

  // Check Web Speech API support
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      setVoiceSupported(true);
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onresult = (event) => {
        let currentTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          currentTranscript += event.results[i][0].transcript;
        }
        setAnswer(prev => prev ? `${prev} ${currentTranscript.trim()}` : currentTranscript.trim());
      };

      recognition.onerror = (event) => {
        console.warn('Speech recognition error:', event.error);
        setIsListening(false);
        if (event.error === 'not-allowed') {
          toast.error('Microphone access was denied. Please allow microphone permissions.');
        }
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = recognition;
    }
  }, []);

  // Restore active session across page refresh
  useEffect(() => {
    const storedSessionId = sessionStorage.getItem('ai_powered_assistance_platform_active_interview_session');
    if (storedSessionId && isStaging) {
      apiClient.get(`/interview/session/${storedSessionId}`)
        .then(res => {
          const data = res.data;
          if (data && !data.is_finished && data.current_question) {
            setSession({
              session_id: data.session_id,
              question: data.current_question,
              topic: data.topics_covered?.[data.topics_covered.length - 1] || 'Core Assessment',
              question_type: data.question_type || 'technical',
              difficulty_level: data.difficulty_level || 3,
              difficulty_label: data.difficulty_label || 'Mid-Level Professional',
              question_index: data.question_index || 1,
              max_questions: data.max_questions || 5,
              topics_covered: data.topics_covered || []
            });
            setIsStaging(false);
            toast.success('Resumed active interview session.');
          }
        })
        .catch(() => {
          sessionStorage.removeItem('ai_powered_assistance_platform_active_interview_session');
        });
    }
  }, [isStaging]);

  const toggleSpeechRecognition = () => {
    if (!voiceSupported) {
      toast.error('Speech recognition is not supported in this browser. Please use keyboard text entry.');
      return;
    }

    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
    } else {
      try {
        recognitionRef.current?.start();
        setIsListening(true);
        toast('Listening... Speak your answer clearly.', { icon: '🎙️' });
      } catch (err) {
        console.error('Failed to start speech recognition', err);
      }
    }
  };

  const handleSpeakQuestion = (text) => {
    if (!('speechSynthesis' in window)) {
      toast.error('Spoken feedback not supported in this browser.');
      return;
    }

    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    setIsSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };

  const handleStartInterview = async () => {
    setIsGeneratingStart(true);
    setActiveHint(null);
    setTurnFeedback(null);
    try {
      const payload = {
        interview_mode: interviewMode,
        initial_difficulty: parseInt(initialDifficulty, 10)
      };
      if (focusType === 'job' && selectedJobId) {
        payload.job_id = selectedJobId;
      } else if (focusType === 'role' && targetRole) {
        payload.target_role = targetRole;
      }

      const res = await apiClient.post('/interview/start', payload);
      const data = res.data;
      setSession(data);
      sessionStorage.setItem('ai_powered_assistance_platform_active_interview_session', data.session_id);
      setIsStaging(false);
      setReport(null);
      setAnswer('');
      toast.success('Adaptive interview initiated!');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to start interview.');
    } finally {
      setIsGeneratingStart(false);
    }
  };

  const handleRequestHint = async () => {
    if (!session?.session_id) return;
    setIsLoadingHint(true);
    try {
      const res = await apiClient.post('/interview/hint', { session_id: session.session_id });
      setActiveHint(res.data.hint);
      toast('Scaffolding hint loaded.', { icon: '💡' });
    } catch (err) {
      toast.error('Failed to fetch hint.');
    } finally {
      setIsLoadingHint(false);
    }
  };

  const handleSubmitAnswer = async () => {
    if (!answer.trim()) {
      toast.error('Please enter an answer before submitting.');
      return;
    }

    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
    }

    setIsSubmitting(true);
    try {
      const res = await apiClient.post('/interview/answer', {
        session_id: session.session_id,
        answer: answer.trim()
      });

      const data = res.data;
      setTurnFeedback({
        evaluation: data.current_evaluation,
        transition_reason: data.transition_reason,
        next_question: data.next_question,
        next_topic: data.next_topic,
        next_question_type: data.next_question_type,
        difficulty_level: data.difficulty_level || data.final_difficulty,
        difficulty_label: data.difficulty_label || data.final_difficulty_label,
        question_index: data.question_index,
        is_finished: data.is_finished
      });
      setActiveHint(null);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to evaluate answer. Please retry.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const advanceToNextQuestion = () => {
    if (!turnFeedback) return;

    if (turnFeedback.is_finished) {
      sessionStorage.removeItem('ai_powered_assistance_platform_active_interview_session');
      const finishedId = session.session_id;
      setSession(null);
      setTurnFeedback(null);
      handleGetReport(finishedId);
    } else {
      setSession(prev => ({
        ...prev,
        question: turnFeedback.next_question,
        topic: turnFeedback.next_topic || prev.topic,
        question_type: turnFeedback.next_question_type || prev.question_type,
        difficulty_level: turnFeedback.difficulty_level,
        difficulty_label: turnFeedback.difficulty_label,
        question_index: turnFeedback.question_index
      }));
      setTurnFeedback(null);
      setAnswer('');
      setActiveHint(null);
    }
  };

  const handleGetReport = async (sessionId) => {
    setIsLoadingReport(true);
    try {
      const res = await apiClient.get(`/interview/report?session_id=${sessionId}`);
      setReport(res.data);
      toast.success('Interview complete! Evaluation report generated.');
    } catch (err) {
      toast.error('Failed to compile report card.');
    } finally {
      setIsLoadingReport(false);
    }
  };

  const resetSession = () => {
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
    }
    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }
    sessionStorage.removeItem('ai_powered_assistance_platform_active_interview_session');
    setIsStaging(true);
    setSession(null);
    setReport(null);
    setTurnFeedback(null);
    setActiveHint(null);
    setAnswer('');
  };

  if (isLoadingProfile) {
    return (
      <div className="max-w-4xl mx-auto py-20">
        <LoadingSpinner text="Retrieving verified candidate profile..." />
      </div>
    );
  }

  if (!hasProfile || !profile?.resume_text) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-20 text-center">
        <div className="glass-panel border border-dark-800 rounded-2xl p-12 space-y-4">
          <span className="text-5xl block">📝</span>
          <h2 className="text-xl font-bold text-dark-100">Resume & Career Profile Needed</h2>
          <p className="text-xs text-dark-400 max-w-md mx-auto leading-relaxed">
            The Adaptive AI Interview Coach uses your verified career profile and target job description to generate evidence-grounded questions and rubric evaluations.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Page Header */}
      <div className="pb-4 border-b border-dark-800 flex justify-between items-start flex-wrap gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-dark-50 flex items-center space-x-3">
            <span>🗣️</span>
            <span>Adaptive AI Interview Coach</span>
          </h1>
          <p className="text-xs text-dark-400 mt-1">
            Personalized multi-turn mock interviews with STAR behavioral grading, technical depth rubrics, and deterministic difficulty scaling.
          </p>
        </div>
        <div className="flex items-center space-x-2 text-[10px] font-semibold bg-indigo-950/40 border border-indigo-500/20 text-indigo-300 px-3 py-1 rounded-full">
          <span>🔒 Privacy Preserved</span>
          <span>•</span>
          <span>Local Voice Support</span>
        </div>
      </div>

      {/* 1. Staging / Setup Selection */}
      {isStaging && !isLoadingReport && !report && (
        <div className="glass-panel border border-dark-800 rounded-2xl p-6 space-y-6">
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-bold text-dark-200 uppercase tracking-wider">Configure Interview Session</h3>
            <span className="text-xs text-dark-400">Step 1 of 2</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* General Resume Focus */}
            <div
              onClick={() => setFocusType('general')}
              className={`p-4 border rounded-xl cursor-pointer transition-all space-y-1.5 ${
                focusType === 'general'
                  ? 'bg-indigo-600/10 border-indigo-500/40 text-indigo-400 ring-1 ring-indigo-500/30'
                  : 'bg-dark-900/40 border-dark-800 text-dark-300 hover:bg-dark-900/60'
              }`}
            >
              <span className="text-xl block">📄</span>
              <h4 className="font-bold text-xs text-dark-100">Verified Profile Review</h4>
              <p className="text-[10px] text-dark-400 leading-relaxed font-medium">
                Comprehensive evaluation based on your verified skills and professional history.
              </p>
            </div>

            {/* Target Role */}
            <div
              onClick={() => setFocusType('role')}
              className={`p-4 border rounded-xl cursor-pointer transition-all space-y-1.5 ${
                focusType === 'role'
                  ? 'bg-indigo-600/10 border-indigo-500/40 text-indigo-400 ring-1 ring-indigo-500/30'
                  : 'bg-dark-900/40 border-dark-800 text-dark-300 hover:bg-dark-900/60'
              }`}
            >
              <span className="text-xl block">🎯</span>
              <h4 className="font-bold text-xs text-dark-100">Specific Target Role</h4>
              <p className="text-[10px] text-dark-400 leading-relaxed font-medium">
                Tailored interview focusing on target competencies and identified skill gaps.
              </p>
            </div>

            {/* Matched Job Listing */}
            <div
              onClick={() => setFocusType('job')}
              className={`p-4 border rounded-xl cursor-pointer transition-all space-y-1.5 ${
                focusType === 'job'
                  ? 'bg-indigo-600/10 border-indigo-500/40 text-indigo-400 ring-1 ring-indigo-500/30'
                  : 'bg-dark-900/40 border-dark-800 text-dark-300 hover:bg-dark-900/60'
              }`}
            >
              <span className="text-xl block">💼</span>
              <h4 className="font-bold text-xs text-dark-100">Matched Job Listing</h4>
              <p className="text-[10px] text-dark-400 leading-relaxed font-medium">
                Simulated role interview for an indexed posting with real company criteria.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5 text-xs">
              <label className="font-bold text-dark-300">Interview Mode & Rubric</label>
              <select
                value={interviewMode}
                onChange={(e) => setInterviewMode(e.target.value)}
                className="w-full px-3 py-2 bg-dark-900 border border-dark-800 focus:border-indigo-500/40 rounded-xl outline-none text-dark-200"
              >
                <option value="mixed">Mixed (STAR Behavioral + Technical Depth)</option>
                <option value="behavioral">Behavioral (Strict STAR Rubric)</option>
                <option value="technical">Technical (Coding & System Architecture)</option>
                <option value="project-based">Project-Based (Portfolio & Evidence)</option>
              </select>
            </div>

            <div className="space-y-1.5 text-xs">
              <label className="font-bold text-dark-300">Starting Difficulty Level</label>
              <select
                value={initialDifficulty}
                onChange={(e) => setInitialDifficulty(Number(e.target.value))}
                className="w-full px-3 py-2 bg-dark-900 border border-dark-800 focus:border-indigo-500/40 rounded-xl outline-none text-dark-200"
              >
                <option value={1}>Level 1: Foundational / Junior</option>
                <option value={2}>Level 2: Associate</option>
                <option value={3}>Level 3: Mid-Level Professional (Recommended)</option>
                <option value={4}>Level 4: Senior Specialist</option>
                <option value={5}>Level 5: Staff / Lead Architect</option>
              </select>
            </div>
          </div>

          {focusType === 'role' && (
            <div className="space-y-1.5 text-xs">
              <label className="font-bold text-dark-300">Target Role Title</label>
              <input
                type="text"
                placeholder="e.g. Senior Backend Engineer, Machine Learning Specialist"
                value={targetRole}
                onChange={(e) => setTargetRole(e.target.value)}
                className="w-full px-3 py-2 bg-dark-900 border border-dark-800 focus:border-indigo-500/40 rounded-xl outline-none text-dark-200"
              />
            </div>
          )}

          {focusType === 'job' && (
            <div className="space-y-1.5 text-xs">
              <label className="font-bold text-dark-300">Select Job Listing</label>
              {matchedJobs.length > 0 ? (
                <select
                  value={selectedJobId}
                  onChange={(e) => setSelectedJobId(e.target.value)}
                  className="w-full px-3 py-2 bg-dark-900 border border-dark-800 focus:border-indigo-500/40 rounded-xl outline-none text-dark-200"
                >
                  <option value="">Select a listing...</option>
                  {matchedJobs.map(job => (
                    <option key={job.id} value={job.id}>
                      {job.title} at {job.company} ({job.match_score}%)
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-[10px] text-amber-400">
                  No matched jobs found in local cache. You can use Target Role or General Review.
                </p>
              )}
            </div>
          )}

          <div className="pt-4 border-t border-dark-800 flex justify-end">
            <button
              onClick={handleStartInterview}
              disabled={isGeneratingStart || (focusType === 'role' && !targetRole) || (focusType === 'job' && !selectedJobId)}
              className="px-6 py-2.5 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition-all flex items-center space-x-2"
            >
              {isGeneratingStart ? (
                <>
                  <LoadingSpinner size="sm" text="" />
                  <span>Preparing Personalized Questions...</span>
                </>
              ) : (
                <>
                  <span>🚀</span>
                  <span>Begin Adaptive Interview</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* 2. Active Interview Console */}
      {session && !isStaging && !turnFeedback && (
        <div className="space-y-6">
          <div className="glass-panel border border-dark-800 rounded-2xl flex flex-col text-xs">
            {/* Header with Adaptive Metrics */}
            <div className="px-5 py-4 border-b border-dark-800 flex justify-between items-center bg-dark-900/40 flex-wrap gap-2">
              <div className="flex items-center space-x-3">
                <span className="font-extrabold text-indigo-400 uppercase tracking-wider text-[11px]">
                  Topic: {session.topic}
                </span>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-indigo-950 border border-indigo-500/30 text-indigo-300">
                  Level {session.difficulty_level}: {session.difficulty_label}
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-dark-800 text-dark-300">
                  {session.question_type?.toUpperCase()}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-dark-300 bg-dark-900 px-3 py-1 rounded border border-dark-800">
                  Question {session.question_index} of {session.max_questions || 5}
                </span>
              </div>
            </div>

            {/* Question Card */}
            <div className="p-6 space-y-6">
              <div className="p-5 bg-dark-900/90 border border-dark-800 rounded-xl space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-[10px] font-extrabold text-indigo-400 uppercase tracking-wider">
                    Interviewer Prompt
                  </span>
                  <button
                    onClick={() => handleSpeakQuestion(session.question)}
                    className="text-[11px] font-semibold text-dark-400 hover:text-indigo-400 flex items-center space-x-1"
                    title="Read question aloud (Local Browser Synthesis)"
                  >
                    <span>{isSpeaking ? '⏹️ Stop Audio' : '🔊 Listen'}</span>
                  </button>
                </div>
                <p className="text-dark-100 font-bold leading-relaxed whitespace-pre-line text-sm md:text-base">
                  {session.question}
                </p>
              </div>

              {/* Scaffolding Hint Area */}
              {activeHint && (
                <div className="p-4 bg-amber-950/20 border border-amber-500/30 rounded-xl text-amber-200 text-xs leading-relaxed space-y-1">
                  <span className="font-bold flex items-center space-x-1">
                    <span>💡</span>
                    <span>Scaffolding Guide (Without Revealing Answer)</span>
                  </span>
                  <p>{activeHint}</p>
                </div>
              )}

              {/* Candidate Answer Input */}
              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-[10px] font-extrabold text-dark-400 uppercase tracking-wider">
                    Your Response
                  </span>
                  <div className="flex items-center space-x-3">
                    <button
                      onClick={handleRequestHint}
                      disabled={isLoadingHint || !!activeHint}
                      className="text-[11px] font-semibold text-indigo-400 hover:text-indigo-300 disabled:opacity-50 flex items-center space-x-1"
                    >
                      <span>💡 Need a Hint?</span>
                    </button>
                    {voiceSupported && (
                      <button
                        onClick={toggleSpeechRecognition}
                        className={`text-[11px] font-bold px-2.5 py-1 rounded-lg border flex items-center space-x-1 transition-all ${
                          isListening
                            ? 'bg-red-950/40 border-red-500/40 text-red-400 animate-pulse'
                            : 'bg-dark-900 border-dark-800 text-dark-300 hover:text-dark-100'
                        }`}
                      >
                        <span>{isListening ? '🛑 Stop Dictating' : '🎙️ Voice Input'}</span>
                      </button>
                    )}
                  </div>
                </div>

                <textarea
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  disabled={isSubmitting}
                  placeholder={
                    session.question_type === 'behavioral'
                      ? "Structure your answer using STAR: Situation (context), Task (your responsibility), Action (what you specifically executed), Result (measurable outcome or lesson learned)..."
                      : "Articulate your technical approach, architecture trade-offs, edge-case resilience, and implementation details..."
                  }
                  rows={7}
                  className="w-full p-4 bg-dark-900 border border-dark-800 focus:border-indigo-500/40 rounded-xl outline-none text-dark-100 leading-relaxed font-medium focus:ring-1 focus:ring-indigo-500/20 transition-all resize-none"
                />

                {voiceSupported && (
                  <p className="text-[10px] text-dark-400">
                    Voice processed locally via browser Web Speech API. Audio is not saved or transmitted to external servers.
                  </p>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="p-4 border-t border-dark-800 bg-dark-950/40 flex justify-between items-center">
              <button
                onClick={resetSession}
                className="px-4 py-2 border border-dark-800 hover:bg-dark-800 text-dark-400 hover:text-dark-200 font-bold rounded-xl"
              >
                End Session
              </button>

              <button
                onClick={handleSubmitAnswer}
                disabled={isSubmitting || !answer.trim()}
                className="px-6 py-2.5 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 disabled:opacity-50 text-white font-bold rounded-xl flex items-center space-x-2"
              >
                {isSubmitting ? (
                  <>
                    <LoadingSpinner size="sm" text="" />
                    <span>Evaluating Against Rubric...</span>
                  </>
                ) : (
                  <>
                    <span>Submit Response</span>
                    <span>→</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 3. Turn Evaluation Feedback Card (Shown after each response) */}
      {turnFeedback && (
        <div className="glass-panel border border-dark-800 rounded-2xl p-6 space-y-6 text-xs">
          <div className="flex justify-between items-center border-b border-dark-800 pb-4">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400 block">Turn Feedback</span>
              <h3 className="text-base font-bold text-dark-100">Response Evaluation</h3>
            </div>
            <div className="flex items-center space-x-3">
              <div className="text-right">
                <span className="text-[10px] text-dark-400 block">Performance Score</span>
                <span className="text-lg font-extrabold text-indigo-400">{turnFeedback.evaluation.score}%</span>
              </div>
              <div className="px-3 py-1 rounded-lg bg-dark-900 border border-dark-800 text-[11px] font-bold text-dark-200">
                Level {turnFeedback.difficulty_level}: {turnFeedback.difficulty_label}
              </div>
            </div>
          </div>

          {/* Adaptive Difficulty Transition Notification */}
          {turnFeedback.transition_reason && (
            <div className="p-3 bg-indigo-950/30 border border-indigo-500/20 rounded-xl text-indigo-300 font-semibold flex items-center space-x-2">
              <span>⚡</span>
              <span>{turnFeedback.transition_reason}</span>
            </div>
          )}

          {/* STAR Elements Breakdown (if behavioral) */}
          {turnFeedback.evaluation.star_elements && (
            <div className="p-4 bg-dark-900/60 border border-dark-800 rounded-xl space-y-2">
              <span className="text-[11px] font-bold text-dark-300 uppercase tracking-wider block">STAR Rubric Breakdown</span>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {Object.entries(turnFeedback.evaluation.star_elements).map(([elem, present]) => (
                  <div
                    key={elem}
                    className={`p-2.5 rounded-lg border text-center font-bold text-xs capitalize flex items-center justify-center space-x-1.5 ${
                      present
                        ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-400'
                        : 'bg-red-950/20 border-red-500/30 text-red-400'
                    }`}
                  >
                    <span>{present ? '✓' : '✗'}</span>
                    <span>{elem}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Strengths & Improvement Areas */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="p-4 bg-emerald-950/10 border border-emerald-500/20 rounded-xl space-y-2">
              <span className="font-bold text-emerald-400 block text-xs">💪 Key Strengths</span>
              <ul className="space-y-1 text-dark-300 font-medium">
                {turnFeedback.evaluation.strengths?.map((s, idx) => (
                  <li key={idx} className="flex items-start space-x-1.5">
                    <span className="text-emerald-500">•</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="p-4 bg-amber-950/10 border border-amber-500/20 rounded-xl space-y-2">
              <span className="font-bold text-amber-400 block text-xs">🎯 Areas to Improve</span>
              <ul className="space-y-1 text-dark-300 font-medium">
                {turnFeedback.evaluation.areas_to_improve?.map((a, idx) => (
                  <li key={idx} className="flex items-start space-x-1.5">
                    <span className="text-amber-500">•</span>
                    <span>{a}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Suggested Structure & Practice Recommendation */}
          {turnFeedback.evaluation.suggested_structure && (
            <div className="p-4 bg-dark-900 border border-dark-800 rounded-xl space-y-1 text-dark-300">
              <span className="font-bold text-indigo-400 block text-xs">📐 Suggested Answer Structure</span>
              <p className="font-semibold text-dark-200">{turnFeedback.evaluation.suggested_structure}</p>
            </div>
          )}

          <div className="pt-4 border-t border-dark-800 flex justify-between items-center">
            <button
              onClick={() => {
                setTurnFeedback(null);
                setAnswer('');
              }}
              className="px-4 py-2 border border-dark-800 hover:bg-dark-800 text-dark-300 font-bold rounded-xl"
            >
              Retry Answer
            </button>

            <button
              onClick={advanceToNextQuestion}
              className="px-6 py-2.5 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white font-bold rounded-xl flex items-center space-x-2"
            >
              <span>{turnFeedback.is_finished ? 'View Complete Assessment Report' : 'Next Question'}</span>
              <span>→</span>
            </button>
          </div>
        </div>
      )}

      {/* 4. Complete Assessment Report Card */}
      {report && (
        <div className="glass-panel border border-dark-800 rounded-2xl p-8 space-y-8 text-xs">
          <div className="border-b border-dark-800 pb-6 flex justify-between items-center flex-wrap gap-4">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400 block">Assessment Concluded</span>
              <h2 className="text-xl font-extrabold text-dark-50">Mock Interview Performance Report</h2>
              <p className="text-dark-400 text-xs mt-1">Role Assessment: {report.target_role}</p>
            </div>
            <div className="text-center p-4 bg-dark-900 border border-dark-800 rounded-2xl min-w-[120px]">
              <span className="text-[10px] font-bold text-dark-400 uppercase tracking-wider block">Overall Score</span>
              <span className="text-3xl font-black text-indigo-400">{report.score}%</span>
              <span className="text-[10px] text-dark-400 block mt-1">
                Level {report.final_difficulty_level}
              </span>
            </div>
          </div>

          {/* STAR Coverage Breakdown (if available) */}
          {report.star_breakdown && (
            <div className="p-5 bg-dark-900/60 border border-dark-800 rounded-xl space-y-3">
              <span className="text-xs font-bold text-dark-200 uppercase tracking-wider block">STAR Method Mastery</span>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="p-3 bg-dark-950 rounded-lg text-center border border-dark-800">
                  <span className="text-[10px] text-dark-400 block">Situation</span>
                  <span className="text-base font-bold text-indigo-400">{report.star_breakdown.situation_coverage_pct}%</span>
                </div>
                <div className="p-3 bg-dark-950 rounded-lg text-center border border-dark-800">
                  <span className="text-[10px] text-dark-400 block">Task</span>
                  <span className="text-base font-bold text-indigo-400">{report.star_breakdown.task_coverage_pct}%</span>
                </div>
                <div className="p-3 bg-dark-950 rounded-lg text-center border border-dark-800">
                  <span className="text-[10px] text-dark-400 block">Action</span>
                  <span className="text-base font-bold text-indigo-400">{report.star_breakdown.action_coverage_pct}%</span>
                </div>
                <div className="p-3 bg-dark-950 rounded-lg text-center border border-dark-800">
                  <span className="text-[10px] text-dark-400 block">Result</span>
                  <span className="text-base font-bold text-indigo-400">{report.star_breakdown.result_coverage_pct}%</span>
                </div>
              </div>
            </div>
          )}

          {/* Detailed Observations */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div className="p-5 bg-emerald-950/10 border border-emerald-500/20 rounded-xl space-y-3">
              <h4 className="font-bold text-emerald-400 text-sm">Key Strengths Demonstrated</h4>
              <ul className="space-y-1.5 text-dark-300 font-medium leading-relaxed">
                {report.strengths?.map((s, idx) => (
                  <li key={idx} className="flex items-start space-x-2">
                    <span className="text-emerald-500">•</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="p-5 bg-amber-950/10 border border-amber-500/20 rounded-xl space-y-3">
              <h4 className="font-bold text-amber-400 text-sm">High-Priority Growth Areas</h4>
              <ul className="space-y-1.5 text-dark-300 font-medium leading-relaxed">
                {report.weaknesses?.map((w, idx) => (
                  <li key={idx} className="flex items-start space-x-2">
                    <span className="text-amber-500">•</span>
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Actionable Practice Recommendations */}
          <div className="p-5 bg-indigo-950/20 border border-indigo-500/20 rounded-xl space-y-3">
            <h4 className="font-bold text-indigo-300 text-sm">Actionable Practice Recommendations</h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-dark-200 font-medium">
              {report.practice_recommendations?.map((rec, idx) => (
                <div key={idx} className="p-3 bg-dark-900/80 border border-dark-800 rounded-lg flex items-start space-x-2">
                  <span className="text-indigo-400 font-bold">{idx + 1}.</span>
                  <span>{rec}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="pt-6 border-t border-dark-800 flex justify-end">
            <button
              onClick={resetSession}
              className="px-6 py-2.5 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white font-bold rounded-xl text-xs"
            >
              Start New Practice Interview
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default InterviewCoach;
