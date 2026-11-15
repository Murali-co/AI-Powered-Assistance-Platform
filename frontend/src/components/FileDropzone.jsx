import React, { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';

export const FileDropzone = ({ onFileSelect, isUploading }) => {
  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles && acceptedFiles.length > 0) {
      onFileSelect(acceptedFiles[0]);
    }
  }, [onFileSelect]);

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx']
    },
    maxFiles: 1,
    disabled: isUploading
  });

  return (
    <div className="w-full">
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-2xl p-8 flex flex-col items-center justify-center cursor-pointer transition-all duration-300 ${
          isDragActive
            ? 'border-indigo-400 bg-indigo-500/10 shadow-[0_0_15px_rgba(99,102,241,0.2)]'
            : 'border-dark-700 bg-dark-900/30 hover:border-dark-600 hover:bg-dark-900/50'
        }`}
      >
        <input {...getInputProps()} />
        <span className="text-4xl mb-4">📄</span>
        {isDragActive ? (
          <p className="text-indigo-400 font-semibold animate-pulse text-center">Drop the resume here...</p>
        ) : (
          <div className="text-center space-y-1">
            <p className="text-dark-100 font-semibold">Drag & drop your resume, or click to browse</p>
            <p className="text-dark-400 text-xs">Only PDF or DOCX formats (max 10MB)</p>
          </div>
        )}
      </div>

      {fileRejections.length > 0 && (
        <div className="mt-3 p-3 bg-red-950/20 border border-red-500/20 rounded-xl text-red-400 text-xs">
          <p className="font-bold">Rejected file:</p>
          {fileRejections.map(({ file, errors }) => (
            <div key={file.name}>
              {file.name} - {errors.map((e) => e.message).join(', ')}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
export default FileDropzone;
