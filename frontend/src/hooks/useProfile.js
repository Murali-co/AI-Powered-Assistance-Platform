import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';
import { useAuth } from '../context/AuthContext';

export const useProfile = () => {
  const { user } = useAuth();
  const userId = user?.id;

  const { data: profile, isLoading, error, refetch } = useQuery({
    queryKey: ['profile', userId],
    queryFn: async () => {
      try {
        const response = await apiClient.get('/resume/profile');
        return response.data;
      } catch (err) {
        if (err.response && err.response.status === 404) {
          return null; // Profile doesn't exist yet
        }
        throw err;
      }
    },
    enabled: !!userId,
    retry: false,
  });

  return {
    profile,
    isLoading: !!userId && isLoading,
    error,
    refetch,
    hasProfile: !!profile,
  };
};
