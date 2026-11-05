import React from 'react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    // Log error to console for diagnostic purposes
    console.error('AI Powered Assistance Platform ErrorBoundary caught an unhandled component error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback({
          error: this.state.error,
          resetError: this.handleReset,
        });
      }

      return (
        <div className="min-h-[50vh] flex items-center justify-center p-6">
          <div className="max-w-lg w-full glass-panel border border-red-500/30 rounded-2xl p-6 sm:p-8 text-center space-y-5 shadow-2xl bg-dark-900/90 backdrop-blur-xl">
            <div className="w-14 h-14 mx-auto rounded-2xl bg-red-950/50 border border-red-500/20 flex items-center justify-center text-2xl shadow-inner">
              ⚠️
            </div>

            <div className="space-y-2">
              <h2 className="text-xl font-bold text-dark-50 tracking-tight">
                {this.props.title || 'Something went wrong in this view'}
              </h2>
              <p className="text-xs text-dark-300 leading-relaxed">
                An unexpected interface error occurred while rendering this section.
                Your data and session remain secure.
              </p>
            </div>

            {this.state.error?.message && (
              <div className="p-3 bg-dark-950/70 border border-dark-800 rounded-xl text-left overflow-x-auto text-[11px] font-mono text-red-300/90 max-h-32">
                {this.state.error.message}
              </div>
            )}

            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
              <button
                type="button"
                onClick={this.handleReset}
                className="w-full sm:w-auto px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-bold transition-all shadow-md"
              >
                Try Again
              </button>
              <button
                type="button"
                onClick={() => {
                  window.location.href = '/dashboard';
                }}
                className="w-full sm:w-auto px-5 py-2.5 border border-dark-800 hover:bg-dark-800 text-dark-200 rounded-xl text-xs font-bold transition-all"
              >
                Return to Dashboard
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
