import React, { useState } from 'react';
import toast from 'react-hot-toast';

export const CoverLetterEditor = ({ 
  initialValue = '', 
  onSave, 
  onRegenerate, 
  isRegenerating = false 
}) => {
  const [content, setContent] = useState(initialValue);
  const [tone, setTone] = useState('formal');

  React.useEffect(() => {
    setContent(initialValue);
  }, [initialValue]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      toast.success('Cover letter copied to clipboard!');
    } catch (err) {
      toast.error('Failed to copy text.');
    }
  };

  const handleDownload = () => {
    const element = document.createElement('a');
    const file = new Blob([content], { type: 'text/plain' });
    element.href = URL.createObjectURL(file);
    element.download = 'Cover_Letter.txt';
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
    toast.success('Cover letter downloaded!');
  };

  return (
    <div className="glass-panel rounded-2xl border p-6 flex flex-col space-y-4">
      {/* Editor Controls */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 pb-4 border-b border-dark-800">
        <div>
          <h4 className="text-md font-bold text-dark-100">Cover Letter Customizer</h4>
          <p className="text-xs text-dark-400">Review, adjust, or regenerate the drafted letter</p>
        </div>

        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
          {/* Tone Selector */}
          <div className="flex items-center space-x-2 bg-dark-900 border border-dark-800 rounded-xl p-1 w-full sm:w-auto">
            {['formal', 'casual', 'creative'].map((t) => (
              <button
                key={t}
                onClick={() => setTone(t)}
                className={`px-3 py-1 rounded-lg text-xs font-bold capitalize transition-all ${
                  tone === t 
                    ? 'bg-indigo-600 text-white shadow' 
                    : 'text-dark-400 hover:text-dark-100'
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {onRegenerate && (
            <button
              onClick={() => onRegenerate(tone)}
              disabled={isRegenerating}
              className="px-3.5 py-1.5 bg-dark-900 hover:bg-dark-800 text-indigo-400 border border-indigo-500/20 hover:border-indigo-500/30 text-xs font-bold rounded-xl transition-all disabled:opacity-50 w-full sm:w-auto"
            >
              {isRegenerating ? 'Regenerating...' : 'Regenerate'}
            </button>
          )}
        </div>
      </div>

      {/* Textarea Editor */}
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        className="w-full h-96 bg-dark-950/50 border border-dark-800 focus:border-indigo-500/40 rounded-xl p-4 text-sm font-sans leading-relaxed text-dark-100 focus:outline-none focus:ring-1 focus:ring-indigo-500/40 transition-all resize-none"
        placeholder="Type or paste cover letter here..."
      />

      {/* Footer operations */}
      <div className="flex flex-wrap justify-between items-center gap-4 pt-2">
        <span className="text-xs text-dark-400 font-medium">
          Character Count: {content.length} | Word Count: {content.split(/\s+/).filter(Boolean).length}
        </span>

        <div className="flex items-center space-x-3 w-full sm:w-auto justify-end">
          <button
            onClick={handleCopy}
            className="px-4 py-2 bg-dark-900 border border-dark-800 hover:bg-dark-800 text-dark-100 text-xs font-bold rounded-xl transition-all flex items-center space-x-2"
          >
            <span>📋</span>
            <span>Copy Clipboard</span>
          </button>

          <button
            onClick={handleDownload}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-xl transition-all flex items-center space-x-2"
          >
            <span>📥</span>
            <span>Download .txt</span>
          </button>
          
          {onSave && (
            <button
              onClick={() => onSave(content)}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-xl transition-all"
            >
              Save Details
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
export default CoverLetterEditor;
