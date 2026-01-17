import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSessions, getSessionDetail, deleteSession } from '@/api';

export function useSessions(limit = 100, offset = 0) {
  return useQuery({
    queryKey: ['sessions', limit, offset],
    queryFn: () => getSessions(limit, offset),
    staleTime: 30000,
  });
}

export function useSessionDetail(sessionId: string | null) {
  return useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => getSessionDetail(sessionId!),
    enabled: !!sessionId,
    staleTime: 10000,
  });
}

export function useDeleteSession() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: deleteSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
    },
  });
}
