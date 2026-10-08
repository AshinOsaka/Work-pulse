import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api-client'
import type { ReportJob, ReportPreview, ReportRequestInput, ReportTypeInfo } from '@/types/api'

export const reportKeys = {
  all: ['reports'] as const,
  types: () => ['reports', 'types'] as const,
  jobs: () => ['reports', 'jobs'] as const,
}

const ACTIVE = new Set(['queued', 'preparing', 'generating'])
export const isActive = (job: ReportJob) => ACTIVE.has(job.status)

export const useReportTypes = () => useQuery({ queryKey: reportKeys.types(), queryFn: () => api.get<ReportTypeInfo[]>('/reports/types'), staleTime: 300_000 })

/** Poll quickly while something is being generated; slowly otherwise (download links are short-lived). */
export const useReportJobs = () =>
  useQuery({
    queryKey: reportKeys.jobs(),
    queryFn: () => api.get<ReportJob[]>('/reports'),
    refetchInterval: (query) => ((query.state.data ?? []).some(isActive) ? 1500 : 60_000),
  })

export const usePreviewReport = () => useMutation({ mutationFn: (input: ReportRequestInput) => api.post<ReportPreview>('/reports/preview', input) })

export function useRequestReport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: ReportRequestInput) => api.post<ReportJob>('/reports', input),
    onSuccess: (job) => {
      client.setQueryData<ReportJob[]>(reportKeys.jobs(), (jobs) => [job, ...(jobs ?? [])])
      void client.invalidateQueries({ queryKey: reportKeys.jobs() })
    },
  })
}

export function useDeleteReport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/reports/${id}`),
    onSettled: () => void client.invalidateQueries({ queryKey: reportKeys.jobs() }),
  })
}
