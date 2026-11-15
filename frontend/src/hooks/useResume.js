import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../context/AuthContext';
import { useJobPolling } from './useJobPolling';
import apiClient from '../api/client';

export const useResume = () => {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const pollJobStatus = useJobPolling(user?.id);

  const uploadResumeMutation = useMutation({
    mutationFn: async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      const response = await apiClient.post('/resume/upload', formData);
      return response.data;
    },
    onSuccess: () => {
      // Invalidate profile query to refetch new data
      queryClient.invalidateQueries({ queryKey: ['profile'] });
    },
  });

  const analyzeResumeMutation = useMutation({
    mutationFn: async ({ target_role }) => {
      const response = await apiClient.post('/resume/analyze', { target_role });
      return response.data; // { job_id: ..., status: ... }
    },
  });


  return {
    uploadResume: uploadResumeMutation.mutateAsync,
    isUploading: uploadResumeMutation.isPending,
    analyzeResume: analyzeResumeMutation.mutateAsync,
    isAnalyzing: analyzeResumeMutation.isPending,
    pollJobStatus,
  };
};
