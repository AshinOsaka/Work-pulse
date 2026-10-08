import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, toQuery } from '@/lib/api-client'
import { usePermissions } from '@/stores/auth-store'
import type {
  Department,
  Device,
  DeviceOs,
  DeviceRegistered,
  EmployeeDetail,
  EmployeeInput,
  EmployeeListParams,
  EmployeeRef,
  EmployeeStatus,
  Employee,
  Page,
  PeopleSummary,
  Role,
  Team,
} from '@/types/api'

export const peopleKeys = {
  all: ['people'] as const,
  summary: () => ['people', 'summary'] as const,
  employees: (params: EmployeeListParams) => ['people', 'employees', params] as const,
  employee: (id: string) => ['people', 'employee', id] as const,
  devices: (id: string) => ['people', 'employee', id, 'devices'] as const,
  options: () => ['people', 'options'] as const,
  managers: () => ['people', 'managers'] as const,
  departments: () => ['people', 'departments'] as const,
  teams: () => ['people', 'teams'] as const,
}

// --------------------------------------------------------------------------- queries

export function usePeopleSummary() {
  const { can } = usePermissions()
  return useQuery({
    queryKey: peopleKeys.summary(),
    queryFn: () => api.get<PeopleSummary>('/people/summary'),
    enabled: can('EMPLOYEE_VIEW'),
  })
}

export function useEmployees(params: EmployeeListParams) {
  return useQuery({
    queryKey: peopleKeys.employees(params),
    queryFn: () => api.get<Page<Employee>>(`/employees${toQuery({ ...params })}`),
    placeholderData: keepPreviousData,
  })
}

export function useEmployee(id: string | undefined) {
  return useQuery({
    queryKey: peopleKeys.employee(id ?? ''),
    queryFn: () => api.get<EmployeeDetail>(`/employees/${id}`),
    enabled: Boolean(id),
  })
}

export function useEmployeeOptions(enabled = true) {
  return useQuery({
    queryKey: peopleKeys.options(),
    queryFn: () => api.get<EmployeeRef[]>('/employees/options'),
    enabled,
    staleTime: 60_000,
  })
}

/** Server-side search for pickers: finds anyone in scope, however large the company (the plain list is capped). */
export function useEmployeeSearch(search: string) {
  const term = search.trim()
  return useQuery({
    queryKey: [...peopleKeys.options(), 'search', term],
    queryFn: () => api.get<EmployeeRef[]>(`/employees/options${toQuery({ search: term })}`),
    enabled: term.length > 0,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  })
}

export function useManagers() {
  return useQuery({ queryKey: peopleKeys.managers(), queryFn: () => api.get<EmployeeRef[]>('/employees/managers') })
}

export function useDepartments(enabled = true) {
  return useQuery({
    queryKey: peopleKeys.departments(),
    queryFn: () => api.get<Department[]>('/departments'),
    enabled,
  })
}

export function useTeams(enabled = true) {
  return useQuery({ queryKey: peopleKeys.teams(), queryFn: () => api.get<Team[]>('/teams'), enabled })
}

export function useEmployeeDevices(id: string) {
  return useQuery({ queryKey: peopleKeys.devices(id), queryFn: () => api.get<Device[]>(`/employees/${id}/devices`) })
}

// --------------------------------------------------------------------------- mutations

/** Any organisation change can affect counts, pickers and profiles: refresh the module. */
function useInvalidatePeople() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: peopleKeys.all })
}

export function useCreateEmployee() {
  const invalidate = useInvalidatePeople()
  return useMutation({
    mutationFn: (input: EmployeeInput) => api.post<EmployeeDetail>('/employees', input),
    onSuccess: invalidate,
  })
}

export function useUpdateEmployee(id: string) {
  const invalidate = useInvalidatePeople()
  return useMutation({
    mutationFn: (input: EmployeeInput) => api.patch<EmployeeDetail>(`/employees/${id}`, input),
    onSuccess: invalidate,
  })
}

export function useChangeEmployeeStatus(id: string) {
  const invalidate = useInvalidatePeople()
  return useMutation({
    mutationFn: (status: EmployeeStatus) => api.post<EmployeeDetail>(`/employees/${id}/status`, { status }),
    onSuccess: invalidate,
  })
}

export function useInviteEmployee(id: string) {
  const invalidate = useInvalidatePeople()
  return useMutation({
    mutationFn: (role: Role) => api.post<EmployeeDetail>(`/employees/${id}/invite`, { role }),
    onSuccess: invalidate,
  })
}

export interface DepartmentInput {
  name?: string
  description?: string | null
  head_employee_id?: string | null
}

export function useSaveDepartment(id?: string) {
  const invalidate = useInvalidatePeople()
  return useMutation({
    mutationFn: (input: DepartmentInput) =>
      id ? api.patch<Department>(`/departments/${id}`, input) : api.post<Department>('/departments', input),
    onSuccess: invalidate,
  })
}

export function useDeleteDepartment() {
  const invalidate = useInvalidatePeople()
  return useMutation({ mutationFn: (id: string) => api.delete<void>(`/departments/${id}`), onSuccess: invalidate })
}

export interface TeamInput {
  name?: string
  description?: string | null
  department_id?: string | null
  lead_employee_id?: string | null
}

export function useSaveTeam(id?: string) {
  const invalidate = useInvalidatePeople()
  return useMutation({
    mutationFn: (input: TeamInput) => (id ? api.patch<Team>(`/teams/${id}`, input) : api.post<Team>('/teams', input)),
    onSuccess: invalidate,
  })
}

export function useDeleteTeam() {
  const invalidate = useInvalidatePeople()
  return useMutation({ mutationFn: (id: string) => api.delete<void>(`/teams/${id}`), onSuccess: invalidate })
}

export interface DeviceInput {
  name: string
  hostname?: string | null
  os: DeviceOs
  os_version?: string | null
}

export function useRegisterDevice(employeeId: string) {
  const invalidate = useInvalidatePeople()
  return useMutation({
    mutationFn: (input: DeviceInput) => api.post<DeviceRegistered>(`/employees/${employeeId}/devices`, input),
    onSuccess: invalidate,
  })
}

export function useRevokeDevice() {
  const invalidate = useInvalidatePeople()
  return useMutation({ mutationFn: (id: string) => api.post<Device>(`/devices/${id}/revoke`, {}), onSuccess: invalidate })
}
