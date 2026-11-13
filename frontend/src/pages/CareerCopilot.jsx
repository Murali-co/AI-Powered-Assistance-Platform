import React, { useState, useEffect, useRef } from 'react';
import apiClient, { getAccessToken } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useJobs } from '../hooks/useJobs';
import { LoadingSpinner } from '../components/LoadingSpinner';
import PendingApprovalCard from '../components/PendingApprovalCard';
import toast from 'react-hot-toast';

export const CareerCopilot = () => {
  const { refreshToken } = useAuth();
  const { matchedJobs } = useJobs();
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState('');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [selectedJobId, setSelectedJobId] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [pendingWorkflows, setPendingWorkflows] = useState([]);
  const [_capabilities, setCapabilities] = useState([]);
  const messagesEndRef = useRef(null);
  const abortControllerRef = useRef(null);
  const isMountedRef = useRef(true);

  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  const fetchPendingApprovals = async () => {
    try {
      const res = await apiClient.get('/orchestrator/workflows');
      const workflows = res.data || [];
      const pendingList = [];
      for (const wf of workflows) {
        if (wf.status === 'AWAITING_APPROVAL') {
          try {
            const tasksRes = await apiClient.get(`/orchestrator/workflows/${wf.workflow_id}/pending-approval`);
            if (tasksRes.data && tasksRes.data.length > 0) {
              for (const pendingTask of tasksRes.data) {
                pendingList.push({
                  workflow_id: wf.workflow_id,
                  goal: wf.goal,
                  pendingTask
                });
              }
            }
          } catch (e) {
            console.error(e);
          }
        }
      }
      setPendingWorkflows(pendingList);
    } catch (err) {
      // Ignore orchestrator error if endpoint isn't active
    }
  };

  const fetchCapabilities = async () => {
    try {
      const res = await apiClient.get('/orchestrator/capabilities');
      setCapabilities(res.data || []);
    } catch (err) {
      console.error(err);
    }
  };

  // Load user sessions on mount
  useEffect(() => {
    isMountedRef.current = true;
    fetchSessions();
    startNewSession();
    fetchPendingApprovals();
    fetchCapabilities();

    return () => {
      isMountedRef.current = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Auto scroll to bottom when messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const fetchSessions = async () => {
    try {
      const res = await apiClient.get('/copilot/sessions');
      setSessions(res.data);
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  };

  const startNewSession = () => {
    const newSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    setActiveSession(newSessionId);
    setMessages([]);
    setSelectedJobId('');
  };

  const loadSession = async (sessionId) => {
    setIsLoadingHistory(true);
    setActiveSession(sessionId);
    try {
      const res = await apiClient.get(`/copilot/history/${sessionId}`);
      setMessages(res.data);
    } catch (err) {
      toast.error('Failed to load chat history.');
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const deleteSession = async (sessionId, e) => {
    e.stopPropagation();
    const loadingToast = toast.loading('Deleting session...');
    try {
      await apiClient.delete(`/copilot/session/${sessionId}`);
      toast.success('Session deleted.', { id: loadingToast });
      fetchSessions();
      if (activeSession === sessionId) {
        startNewSession();
      }
    } catch (err) {
      toast.error('Failed to delete session.', { id: loadingToast });
    }
  };

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (isMountedRef.current) {
      setIsSending(false);
      setMessages(prev => {
        const lastIdx = prev.length - 1;
        if (lastIdx >= 0 && prev[lastIdx].role === 'assistant' && prev[lastIdx].isStreaming) {
          const updated = [...prev];
          updated[lastIdx] = {
            ...updated[lastIdx],
            isStreaming: false,
            content: updated[lastIdx].content ? `${updated[lastIdx].content} (cancelled)` : 'Cancelled'
          };
          return updated;
        }
        return prev;
      });
    }
  };

  const handleSend = async (textToSend) => {
    const messageText = textToSend || input;
    if (!messageText.trim()) return;

    if (!textToSend) setInput('');

    // Append user message
    const userMsg = { role: 'user', content: messageText };
    setMessages(prev => [...prev, userMsg]);
    setIsSending(true);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const getCsrfToken = () => {
      if (typeof document === 'undefined') return '';
      const match = document.cookie.match(new RegExp(`(?:^|; )csrf_token=([^;]*)`));
      return match ? decodeURIComponent(match[1]) : '';
    };

    const makeStreamRequest = async (tokenToUse) => {
      const headers = { 'Content-Type': 'application/json' };
      if (tokenToUse) {
        headers['Authorization'] = `Bearer ${tokenToUse}`;
      }
      const csrfToken = getCsrfToken();
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
      }

      return fetch(`${API_URL}/copilot/chat`, {
        method: 'POST',
        headers,
        credentials: 'include',
        signal: controller.signal,
        body: JSON.stringify({
          message: messageText,
          session_id: activeSession,
          job_id: selectedJobId || null,
          stream: true
        })
      });
    };

    try {
      let currentToken = getAccessToken();
      let response = await makeStreamRequest(currentToken);

      // Handle 401 with automatic token refresh (M11)
      if (response.status === 401) {
        try {
          const freshToken = await refreshToken();
          currentToken = freshToken || getAccessToken();
          response = await makeStreamRequest(currentToken);
        } catch {
          throw new Error('Authentication expired. Please log in again.');
        }
      }

      if (!response.ok) {
        let msg = 'Server error';
        try {
          const body = await response.json();
          msg = body.detail || JSON.stringify(body);
        } catch {
          const text = await response.text();
          if (text) msg = text;
        }
        throw new Error(msg);
      }

      // Add skeleton assistant message
      if (isMountedRef.current) {
        setMessages(prev => [...prev, { role: 'assistant', content: '', classified_as: 'loading', isStreaming: true }]);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Streaming not supported by this browser.');
      }

      const decoder = new TextDecoder();
      let done = false;
      let buffer = '';

      const processDataLine = (line) => {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data: ')) return;
        try {
          const data = JSON.parse(trimmed.slice(6));
          if (data.token) {
            if (isMountedRef.current) {
              setMessages(prev => {
                const lastIdx = prev.length - 1;
                if (lastIdx >= 0 && prev[lastIdx].role === 'assistant') {
                  const updated = [...prev];
                  updated[lastIdx] = {
                    ...updated[lastIdx],
                    content: updated[lastIdx].content + data.token,
                    classified_as: data.classified_as || updated[lastIdx].classified_as
                  };
                  return updated;
                }
                return prev;
              });
            }
          } else if (data.error) {
            toast.error(`Error: ${data.error}`);
          }
        } catch (e) {
          console.warn('Copilot stream parse failed:', e);
        }
      };

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: !done });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            processDataLine(line);
          }
        }
      }

      // Final decoder flush and process any remaining buffered lines
      buffer += decoder.decode();
      if (buffer.trim()) {
        const remaining = buffer.split('\n');
        for (const line of remaining) {
          processDataLine(line);
        }
      }

      if (isMountedRef.current) {
        setMessages(prev => {
          const lastIdx = prev.length - 1;
          if (lastIdx >= 0 && prev[lastIdx].role === 'assistant') {
            const updated = [...prev];
            updated[lastIdx] = {
              ...updated[lastIdx],
              isStreaming: false
            };
            return updated;
          }
          return prev;
        });
        fetchSessions();
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        // Stream aborted by user or unmount; ignore
        return;
      }
      console.error('Copilot chat error:', err);
      const errMsg = err.message || 'Connection to local LLM failed. Make sure Ollama is running.';
      toast.error(errMsg);
      if (isMountedRef.current) {
        setMessages(prev => {
          const lastIdx = prev.length - 1;
          if (lastIdx >= 0 && prev[lastIdx].role === 'assistant' && prev[lastIdx].isStreaming) {
            const updated = [...prev];
            updated[lastIdx] = {
              ...updated[lastIdx],
              content: updated[lastIdx].content ? `${updated[lastIdx].content}\n[Error: ${errMsg}]` : `Error: ${errMsg}`,
              isStreaming: false
            };
            return updated;
          }
          return [...prev, { role: 'assistant', content: `Error: ${errMsg}` }];
        });
      }
    } finally {
      if (isMountedRef.current) {
        setIsSending(false);
      }
      abortControllerRef.current = null;
    }
  };

  const handleSuggestionClick = (suggestion) => {
    handleSend(suggestion);
  };

  const suggestions = [
    { text: "What are my strongest skills?", category: "resume" },
    { text: "How do I become an AI Engineer?", category: "career" },
    { text: "Help me prepare for an interview.", category: "job" },
    { text: "What should I learn next to grow?", category: "career" }
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Title */}
      <div className="pb-4 border-b border-dark-800 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-dark-50">🧭 Career Copilot</h1>
          <p className="text-xs text-dark-400 mt-1">Unified AI Assistant for Resume Analysis, Job Alignment, and Roadmaps.</p>
        </div>

        {/* Job Context dropdown */}
        <div className="flex items-center space-x-2 text-xs w-full md:w-auto">
          <span className="text-dark-400 font-semibold shrink-0">Focus Job Context:</span>
          <select
            value={selectedJobId}
            onChange={(e) => setSelectedJobId(e.target.value)}
            className="px-3 py-2 bg-dark-900 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-dark-200 outline-none text-xs w-full md:max-w-xs transition-all"
          >
            <option value="">No Job Bound (General RAG)</option>
            {matchedJobs.map(job => (
              <option key={job.id} value={job.id}>
                {job.title} at {job.company} ({job.match_score}%)
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Pending Agent Action Approvals Banner */}
      {pendingWorkflows.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-bold text-amber-300 flex items-center space-x-2">
            <span>✋</span>
            <span>Pending Agent Action Approvals ({pendingWorkflows.length})</span>
          </h2>
          {pendingWorkflows.map((item, idx) => (
            <PendingApprovalCard
              key={idx}
              workflowId={item.workflow_id}
              pendingTask={item.pendingTask}
              onActionComplete={() => fetchPendingApprovals()}
            />
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8 min-h-[600px]">
        {/* Sidebar history */}
        <div className="lg:col-span-1 flex flex-col space-y-4">
          <button
            onClick={startNewSession}
            className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-xs transition-all shadow flex items-center justify-center space-x-2"
          >
            <span>＋</span>
            <span>New Discussion</span>
          </button>

          <div className="glass-panel border rounded-2xl p-4 flex-grow flex flex-col space-y-3 overflow-y-auto max-h-[500px] lg:max-h-[600px]">
            <h3 className="text-xs font-bold text-dark-300 uppercase tracking-wider pb-2 border-b border-dark-800">
              Discussions
            </h3>

            {sessions.length > 0 ? (
              <div className="space-y-1.5 overflow-y-auto pr-1">
                {sessions.map((sid) => (
                  <div
                    key={sid}
                    onClick={() => loadSession(sid)}
                    className={`group px-3 py-2.5 rounded-xl text-xs font-medium cursor-pointer border flex justify-between items-center transition-all ${
                      activeSession === sid
                        ? 'bg-dark-900 border-indigo-500/20 text-indigo-400'
                        : 'border-transparent text-dark-300 hover:bg-dark-900/50 hover:text-dark-100'
                    }`}
                  >
                    <span className="truncate max-w-[120px]">{sid.replace('session_', '')}</span>
                    <button
                      onClick={(e) => deleteSession(sid, e)}
                      className="opacity-0 group-hover:opacity-100 p-1 text-red-500 hover:text-red-400 rounded transition-all"
                      title="Delete Session"
                    >
                      🗑️
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-[11px] text-dark-400">
                No past sessions.
              </div>
            )}
          </div>
        </div>

        {/* Chat Console */}
        <div className="lg:col-span-3 glass-panel border rounded-2xl flex flex-col h-[600px]">
          {/* Active Status Header */}
          <div className="px-5 py-3.5 border-b border-dark-800 flex justify-between items-center bg-dark-900/20">
            <div className="flex items-center space-x-2 text-xs font-bold text-dark-300">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span>AI Powered Assistance Platform Copilot Active</span>
            </div>
            
            {/* Show classification category if assistant generated one */}
            {messages.length > 0 && messages[messages.length - 1]?.role === 'assistant' && (
              <div className="px-2.5 py-1 bg-indigo-950/40 text-indigo-400 border border-indigo-500/10 rounded-full text-[10px] font-bold uppercase tracking-wider">
                RAG Routing: {messages[messages.length - 1].classified_as || 'Resume'}
              </div>
            )}
          </div>

          {/* Messages display */}
          <div className="flex-grow overflow-y-auto p-5 space-y-4">
            {isLoadingHistory ? (
              <div className="h-full flex items-center justify-center">
                <LoadingSpinner text="Retrieving discussion log..." />
              </div>
            ) : messages.length > 0 ? (
              <>
                {messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-2xl p-4 text-xs leading-relaxed space-y-2 border ${
                        msg.role === 'user'
                          ? 'bg-indigo-600/10 border-indigo-500/20 text-dark-100'
                          : 'bg-dark-900 border-dark-800 text-dark-200'
                      }`}
                    >
                      <div className="font-bold text-[10px] uppercase tracking-wider text-dark-400">
                        {msg.role === 'user' ? 'You' : 'AI Copilot'}
                      </div>
                      <div className="whitespace-pre-line font-medium">{msg.content}</div>
                    </div>
                  </div>
                ))}
                {isSending && messages[messages.length - 1]?.role === 'user' && (
                  <div className="flex justify-start">
                    <div className="bg-dark-900 border border-dark-800 rounded-2xl p-4 max-w-[80%] text-xs">
                      <LoadingSpinner text="Retrieving context & reasoning..." />
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center space-y-6 max-w-md mx-auto py-10">
                <span className="text-5xl animate-bounce">🧭</span>
                <div className="space-y-2">
                  <h3 className="text-sm font-bold text-dark-200">Start a Career Consultation</h3>
                  <p className="text-xs text-dark-400 leading-relaxed">
                    Ask me any question about your resume, missing skills, career path roadmaps, 
                    interview preparation, or tailored cover letters.
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-2.5 w-full pt-4">
                  {suggestions.map((sug, i) => (
                    <button
                      key={i}
                      onClick={() => handleSuggestionClick(sug.text)}
                      className="px-3.5 py-3 border border-dark-800 hover:border-indigo-500/20 hover:bg-dark-900/50 rounded-xl text-left text-[11px] text-dark-300 font-semibold hover:text-dark-100 transition-all"
                    >
                      {sug.text}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Form Input */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="p-4 border-t border-dark-800 bg-dark-950/50 flex space-x-2"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={isSending}
              placeholder="Ask anything about your resume, jobs, or roadmaps..."
              className="flex-grow px-4 py-3 bg-dark-900 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-xs text-dark-100 focus:outline-none transition-all disabled:opacity-50"
            />
            {isSending ? (
              <button
                type="button"
                onClick={handleCancel}
                className="px-5 bg-rose-600/20 border border-rose-500/30 hover:bg-rose-600/30 text-rose-400 font-bold rounded-xl text-xs transition-all shadow-md shrink-0 flex items-center justify-center space-x-1.5"
                title="Stop generation"
              >
                <span>Stop</span>
              </button>
            ) : (
              <button
                type="submit"
                disabled={!input.trim()}
                className="px-5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-dark-900 disabled:text-dark-600 text-white font-bold rounded-xl text-xs transition-all shadow-md shrink-0 flex items-center justify-center"
              >
                Send
              </button>
            )}
          </form>
        </div>
      </div>
    </div>
  );
};

export default CareerCopilot;
