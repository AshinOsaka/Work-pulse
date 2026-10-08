import { useState } from 'react'
import { Building2, MoreHorizontal, Pencil, Plus, Trash2, Users, UsersRound } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { FilterSelect, toOptions } from '@/components/common/filter-select'
import { Person } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/misc'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useDeleteDepartment, useDeleteTeam, useDepartments, useTeams } from '@/features/people/api'
import { DepartmentDialog, TeamDialog } from '@/features/people/components/structure-dialogs'
import { errorMessage } from '@/lib/api-client'
import { usePermissions } from '@/stores/auth-store'
import type { Department, Team } from '@/types/api'

function RowMenu({ label, onEdit, onDelete }: { label: string; onEdit: () => void; onDelete: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${label}`}>
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-40">
        <DropdownMenuItem onSelect={onEdit}>
          <Pencil /> Edit
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onSelect={onDelete}>
          <Trash2 /> Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function DepartmentsPage() {
  const { can } = usePermissions()
  const canManage = can('EMPLOYEE_MANAGE')
  const departments = useDepartments()
  const remove = useDeleteDepartment()
  const [editing, setEditing] = useState<Department | undefined>()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deleting, setDeleting] = useState<Department | null>(null)

  const openDialog = (item?: Department) => {
    setEditing(item)
    setDialogOpen(true)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] text-muted-foreground">
          {departments.data ? `${departments.data.length} ${departments.data.length === 1 ? 'department' : 'departments'}` : ' '}
        </p>
        {canManage && (
          <Button size="sm" onClick={() => openDialog()}>
            <Plus /> New department
          </Button>
        )}
      </div>

      {departments.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-44 rounded-xl" />
          ))}
        </div>
      ) : departments.isError ? (
        <Card>
          <EmptyState icon={Building2} title="Couldn't load departments" description={errorMessage(departments.error)} />
        </Card>
      ) : departments.data.length === 0 ? (
        <Card>
          <EmptyState
            icon={Building2}
            title="No departments yet"
            description="Departments group your teams and employees by function, like Engineering or Sales."
            action={
              canManage && (
                <Button size="sm" onClick={() => openDialog()}>
                  <Plus /> Create the first department
                </Button>
              )
            }
          />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {departments.data.map((department) => (
            <Card key={department.id} className="group flex flex-col p-5 transition hover:shadow-elevated">
              <div className="flex items-start gap-3">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
                  <Building2 className="size-4.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <Link
                    to={`/people/employees?department=${department.id}`}
                    className="block truncate font-semibold hover:text-primary"
                  >
                    {department.name}
                  </Link>
                  <p className="line-clamp-2 min-h-9 text-[12px] text-muted-foreground">
                    {department.description ?? 'No description'}
                  </p>
                </div>
                {canManage && (
                  <RowMenu label={department.name} onEdit={() => openDialog(department)} onDelete={() => setDeleting(department)} />
                )}
              </div>
              <div className="mt-4 flex items-center gap-4 border-t pt-4 text-[12px] text-muted-foreground">
                <span className="inline-flex items-center gap-1.5 tabular">
                  <Users className="size-3.5" /> {department.employee_count} employees
                </span>
                <span className="inline-flex items-center gap-1.5 tabular">
                  <UsersRound className="size-3.5" /> {department.team_count} teams
                </span>
              </div>
              <div className="mt-3 text-[13px]">
                {department.head ? (
                  <Person id={department.head.id} name={department.head.full_name} subtitle="Department head" size="sm" />
                ) : (
                  <span className="text-[12px] text-muted-foreground">No department head</span>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      <DepartmentDialog open={dialogOpen} onOpenChange={setDialogOpen} item={editing} />
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? 'department'}?`}
        description="Only empty departments can be deleted. Move its employees and teams elsewhere first."
        confirmLabel="Delete department"
        destructive
        loading={remove.isPending}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.id, {
            onSuccess: () => {
              toast.success('Department deleted')
              setDeleting(null)
            },
            onError: (e) => {
              toast.error(errorMessage(e))
              setDeleting(null)
            },
          })
        }
      />
    </div>
  )
}

const ALL = '__all__'

export function TeamsPage() {
  const { can } = usePermissions()
  const canManage = can('EMPLOYEE_MANAGE')
  const teams = useTeams()
  const departments = useDepartments()
  const remove = useDeleteTeam()
  const [department, setDepartment] = useState<string>(ALL)
  const [editing, setEditing] = useState<Team | undefined>()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deleting, setDeleting] = useState<Team | null>(null)

  const rows = (teams.data ?? []).filter((t) => department === ALL || t.department?.id === department)
  const openDialog = (item?: Team) => {
    setEditing(item)
    setDialogOpen(true)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <FilterSelect
          label="Filter by department"
          value={department === ALL ? null : department}
          onChange={(v) => setDepartment(v ?? ALL)}
          options={toOptions(departments.data)}
          allLabel="All departments"
          className="sm:w-56"
        />
        {canManage && (
          <Button size="sm" onClick={() => openDialog()}>
            <Plus /> New team
          </Button>
        )}
      </div>

      <Card className="overflow-hidden">
        {teams.isPending ? (
          <div className="space-y-2 p-5">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : teams.isError ? (
          <EmptyState icon={UsersRound} title="Couldn't load teams" description={errorMessage(teams.error)} />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={UsersRound}
            title={teams.data.length === 0 ? 'No teams yet' : 'No teams in this department'}
            description="Teams are working groups with a team lead, usually inside a department."
            action={
              canManage && (
                <Button size="sm" onClick={() => openDialog()}>
                  <Plus /> New team
                </Button>
              )
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">Team</TableHead>
                <TableHead>Department</TableHead>
                <TableHead>Team lead</TableHead>
                <TableHead className="text-right">Members</TableHead>
                {canManage && <TableHead className="w-12" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((team) => (
                <TableRow key={team.id}>
                  <TableCell className="max-w-72 pl-5">
                    <Link to={`/people/employees?team=${team.id}`} className="font-medium hover:text-primary">
                      {team.name}
                    </Link>
                    {team.description && <p className="truncate text-[12px] text-muted-foreground">{team.description}</p>}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{team.department?.name ?? '—'}</TableCell>
                  <TableCell>
                    {team.lead ? <Person id={team.lead.id} name={team.lead.full_name} size="sm" /> : <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell className="text-right tabular whitespace-nowrap">{team.member_count}</TableCell>
                  {canManage && (
                    <TableCell>
                      <RowMenu label={team.name} onEdit={() => openDialog(team)} onDelete={() => setDeleting(team)} />
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <TeamDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        item={editing}
        defaultDepartmentId={department === ALL ? undefined : department}
      />
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? 'team'}?`}
        description="Only teams without members can be deleted. Reassign its members first."
        confirmLabel="Delete team"
        destructive
        loading={remove.isPending}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.id, {
            onSuccess: () => {
              toast.success('Team deleted')
              setDeleting(null)
            },
            onError: (e) => {
              toast.error(errorMessage(e))
              setDeleting(null)
            },
          })
        }
      />
    </div>
  )
}
