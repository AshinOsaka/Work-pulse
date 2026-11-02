import { useMemo } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { useRoles } from '@/hooks/use-system'
import { api } from '@/lib/api-client'
import { canAssignLevel, ROLE_LEVELS, roleKeyLabel } from '@/lib/format'
import type { Role, RoleInfo } from '@/types/api'

/**
 * The company's roles (built-in access levels + custom roles). A role has a base access level that
 * decides what it can access; custom roles are named aliases over those levels.
 */
export function useRoleCatalog() {
  const roles = useRoles()
  const list = useMemo(() => roles.data?.roles ?? [], [roles.data])
  const byKey = useMemo(() => new Map(list.map((r) => [r.key, r])), [list])

  return {
    query: roles,
    roles: list,
    byKey,
    /** Display name for a role key, with a sensible fallback before the list loads. */
    name: (key: string | undefined) => (key ? (byKey.get(key)?.name ?? roleKeyLabel(key)) : '—'),
    /** Roles an actor may assign, highest level first. */
    assignable: (actor: Role | undefined): RoleInfo[] =>
      [...list]
        .filter((r) => canAssignLevel(actor, r.base_level))
        .sort((a, b) => ROLE_LEVELS[b.base_level] - ROLE_LEVELS[a.base_level] || a.name.localeCompare(b.name)),
  }
}

export interface RoleInput {
  name: string
  base_level: Role
}

function useInvalidateRoles() {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: ['roles'] })
    void client.invalidateQueries({ queryKey: ['users'] })
    void client.invalidateQueries({ queryKey: ['people'] })
  }
}

export function useCreateRole() {
  const invalidate = useInvalidateRoles()
  return useMutation({ mutationFn: (input: RoleInput) => api.post<RoleInfo>('/roles', input), onSuccess: invalidate })
}

export function useUpdateRole(key: string) {
  const invalidate = useInvalidateRoles()
  return useMutation({
    mutationFn: (input: Partial<RoleInput>) => api.patch<RoleInfo>(`/roles/${key}`, input),
    onSuccess: invalidate,
  })
}

export function useDeleteRole() {
  const invalidate = useInvalidateRoles()
  return useMutation({ mutationFn: (key: string) => api.delete<void>(`/roles/${key}`), onSuccess: invalidate })
}
