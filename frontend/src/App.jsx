import React, { Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import Navbar from './components/Navbar';
import { LoadingSpinner } from './components/LoadingSpinner';
import ErrorBoundary from './components/ErrorBoundary';

// Lazy-loaded page components for optimal bundle splitting (M11 / M15 / Phase 6)
const Landing = React.lazy(() => import('./pages/Landing'));
const Auth = React.lazy(() => import('./pages/Auth'));
const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const ResumeUpload = React.lazy(() => import('./pages/ResumeUpload'));
const SkillGap = React.lazy(() => import('./pages/SkillGap'));
const CoverLetter = React.lazy(() => import('./pages/CoverLetter'));
const JobBoard = React.lazy(() => import('./pages/JobBoard'));
const JobMatch = React.lazy(() => import('./pages/JobMatch'));
const ApplyAssistant = React.lazy(() => import('./pages/ApplyAssistant'));
const ApplicationsHistory = React.lazy(() => import('./pages/ApplicationsHistory'));
const AppliedJobs = React.lazy(() => import('./pages/AppliedJobs'));
const CareerCopilot = React.lazy(() => import('./pages/CareerCopilot'));
const InterviewCoach = React.lazy(() => import('./pages/InterviewCoach'));
const VerifyEmail = React.lazy(() => import('./pages/VerifyEmail'));
const ResendVerification = React.lazy(() => import('./pages/ResendVerification'));
const VerificationSuccess = React.lazy(() => import('./pages/VerificationSuccess'));
const ForgotPassword = React.lazy(() => import('./pages/ForgotPassword'));
const ResetPassword = React.lazy(() => import('./pages/ResetPassword'));
const SecuritySettings = React.lazy(() => import('./pages/SecuritySettings'));
const AdminAuditLog = React.lazy(() => import('./pages/AdminAuditLog'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// Route protector for secure pages
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-950 flex items-center justify-center">
        <LoadingSpinner text="Verifying credentials..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/auth" replace />;
  }

  return children;
};

const PageFallback = () => (
  <div className="min-h-[60vh] flex items-center justify-center">
    <LoadingSpinner text="Loading view..." />
  </div>
);

function AppContent() {
  return (
    <div className="min-h-screen bg-dark-950 text-dark-50 flex flex-col font-sans">
      <Navbar />
      <div className="flex-grow">
        <ErrorBoundary>
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/auth" element={<Auth />} />
              
              {/* Email Verification Routes (Public) */}
              <Route path="/verify-email" element={<VerifyEmail />} />
              <Route path="/resend-verification" element={<ResendVerification />} />
              <Route path="/verification-success" element={<VerificationSuccess />} />
              
              {/* Password Reset Routes (Public) */}
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/reset-password" element={<ResetPassword />} />
              
              {/* Protected Routes */}
              <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
              <Route path="/upload" element={<ProtectedRoute><ResumeUpload /></ProtectedRoute>} />
              <Route path="/skill-gap" element={<ProtectedRoute><SkillGap /></ProtectedRoute>} />
              <Route path="/cover-letter" element={<ProtectedRoute><CoverLetter /></ProtectedRoute>} />
              <Route path="/jobs" element={<ProtectedRoute><JobBoard /></ProtectedRoute>} />
              <Route path="/match" element={<ProtectedRoute><JobMatch /></ProtectedRoute>} />
              <Route path="/jobs/matched" element={<Navigate to="/match" replace />} />
              <Route path="/apply-assistant" element={<ProtectedRoute><ApplyAssistant /></ProtectedRoute>} />
              <Route path="/applications" element={<ProtectedRoute><ApplicationsHistory /></ProtectedRoute>} />
              <Route path="/applied-jobs" element={<ProtectedRoute><AppliedJobs /></ProtectedRoute>} />
              <Route path="/copilot" element={<ProtectedRoute><CareerCopilot /></ProtectedRoute>} />
              <Route path="/interview" element={<ProtectedRoute><InterviewCoach /></ProtectedRoute>} />
              <Route path="/security" element={<ProtectedRoute><SecuritySettings /></ProtectedRoute>} />
              <Route path="/admin/audit-log" element={<ProtectedRoute><AdminAuditLog /></ProtectedRoute>} />
              
              {/* Catch-all */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </div>
      
      {/* Toast Notification Container */}
      <Toaster 
        position="top-right" 
        toastOptions={{
          className: 'glass-panel text-dark-50 border border-dark-800 text-xs font-semibold py-3 px-4 rounded-xl',
          style: {
            background: 'rgba(15, 23, 42, 0.9)',
            backdropFilter: 'blur(8px)',
            color: '#f8fafc',
            border: '1px solid rgba(255, 255, 255, 0.08)'
          },
          success: {
            iconTheme: {
              primary: '#34d399',
              secondary: '#0f172a',
            },
          },
          error: {
            iconTheme: {
              primary: '#f87171',
              secondary: '#0f172a',
            },
          },
        }}
      />
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <AppContent />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
