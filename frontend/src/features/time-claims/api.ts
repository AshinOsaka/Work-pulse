import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { attendanceKeys } from '@/features/attendance/api'
import { api, toQuery } from '@/lib/api-client'
import type { TimeClaim, TimeClaimKind, TimeClaimPage, TimeClaimStatus, TimeClaimTeamResult } from '@/types/api'

export interface TimeClaimQuery {
  status?: TimeClaimStatus
  employee_id?: string
  /** Only the viewer's own claims (a manager looking at their own). */
  mine?: boolean
  page?: number
  page_size?: number
}

export interface TimeClaimInput {
  day: string
  start_time: string
  end_time: string
  kind: TimeClaimKind
  with_whom: string
  note?: string | null
}

export const timeClaimKeys = {
  all: ['time-claims'] as const,
  list: (q: TimeClaimQuery) => ['time-claims', 'list', q] as const,
}

export function useTimeClaims(query: TimeClaimQuery) {
  return useQuery({
    queryKey: timeClaimKeys.list(query),
    queryFn: () => api.get<TimeClaimPage>(`/time-claims${toQuery({ ...query })}`),
    placeholderData: keepPreviousData,
  })
}

/** A change to a claim changes attendance too, so both refresh. */
function useClaimMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      void client.invalidateQueries({ queryKey: timeClaimKeys.all })
      void client.invalidateQueries({ queryKey: attendanceKeys.all })
    },
  })
}

export const useLogTime = () => useClaimMutation((input: TimeClaimInput) => api.post<TimeClaim>('/time-claims', input))

export const useReviewClaim = () =>
  useClaimMutation(({ id, decision, note }: { id: string; decision: 'approve' | 'reject'; note?: string }) =>
    api.post<TimeClaim>(`/time-claims/${id}/review`, { decision, note: note || null }),
  )

export const useDeleteClaim = () => useClaimMutation((id: string) => api.delete<void>(`/time-claims/${id}`))

export const useEditClaim = () =>
  useClaimMutation(({ id, ...input }: Partial<TimeClaimInput> & { id: string }) => api.patch<TimeClaim>(`/time-claims/${id}`, input))

/** A manager logs one meeting for several of their people: one approved claim each. */
export const useLogForTeam = () =>
  useClaimMutation((input: TimeClaimInput & { employee_ids: string[] }) => api.post<TimeClaimTeamResult>('/time-claims/team', input))
