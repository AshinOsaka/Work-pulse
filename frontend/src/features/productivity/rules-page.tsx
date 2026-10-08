import { useMemo, useState, type FormEvent } from 'react'
import { AppWindow, Globe, ListPlus, Plus, Sparkles, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { FormAlert, FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { RequirePermission } from '@/features/auth/guards'
import { formatSeconds } from '@/features/activity/format'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useDepartments, useTeams } from '@/features/people/api'
import { useCreateRule, useDeleteRule, useLoadRecommended, useRules, useUnclassified, useUpdateRule, useWorkProfiles } from '@/features/productivity/api'
import { ClassifyMenu } from '@/features/productivity/components/classify-menu'
import { WorkProfilesCard } from '@/features/productivity/components/work-profiles'
import { CATEGORY, rangeFor, SCOPE_LABEL } from '@/features/productivity/meta'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { ApiError, errorMessage } from '@/lib/api-client'
import { ROLE_LABELS } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import type { ProductivityCategory, ProductivityRule, Role, RuleKind, RuleScope } from '@/types/api'

const CATEGORIES: ProductivityCategory[] = ['productive', 'neutral', 'unproductive']

function RuleDialog({ open, onOpenChange, initial }: { open: boolean; onOpenChange: (open: boolean) => void; initial?: { kind: RuleKind; pattern: string } }) {
  const create = useCreateRule()
  const departments = useDepartments(open)
  const teams = useTeams(open)
  const profiles = useWorkProfiles(open)
  const [kind, setKind] = useState<RuleKind>(initial?.kind ?? 'app')
  const [pattern, setPattern] = useState(initial?.pattern ?? '')
  const [category, setCategory] = useState<ProductivityCategory>('productive')
  const [scope, setScope] = useState<RuleScope>('company')
  const [scopeId, setScopeId] = useState<string>('')
  const [role, setRole] = useState<Role>('EMPLOYEE')
  const errors = create.error instanceof ApiError ? create.error.fieldErrors : {}

  const needsTarget = scope === 'department' || scope === 'team' || scope === 'profile'
  const submit = (event: FormEvent) => {
    event.preventDefault()
    create.mutate(
      { kind, pattern, category, scope, scope_id: needsTarget ? scopeId || null : null, role: scope === 'role' ? role : null },
      {
        onSuccess: (rule) => {
          toast.success(`Rule added: ${rule.pattern} is ${CATEGORY[rule.category].label.toLowerCase()}`)
          onOpenChange(false)
        },
      },
    )
  }

  const targets =
    scope === 'department' ? (departments.data ?? []) : scope === 'team' ? (teams.data ?? []) : scope === 'profile' ? (profiles.data ?? []) : []
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>Add a productivity rule</DialogTitle>
            <DialogDescription>
              The most specific rule wins for each person: work profile, then team, department, role, and finally company-wide.
            </DialogDescription>
          </DialogHeader>
          {create.error && !Object.keys(errors).length && <FormAlert>{errorMessage(create.error)}</FormAlert>}
          <div className="space-y-1.5">
            <Label>Applies to</Label>
            <SegmentedControl<RuleKind>
              label="Rule type"
              value={kind}
              onChange={setKind}
              options={[
                { value: 'app', label: 'Application', icon: AppWindow },
                { value: 'website', label: 'Website', icon: Globe },
              ]}
            />
          </div>
          <FormField
            label={kind === 'app' ? 'Executable or application name' : 'Domain'}
            placeholder={kind === 'app' ? 'e.g. code.exe or Visual Studio Code' : 'e.g. github.com (includes subdomains)'}
            value={pattern}
            onChange={(e) => setPattern(e.target.value)}
            error={errors.pattern}
            required
          />
          <div className="space-y-1.5">
            <Label>Category</Label>
            <SegmentedControl<ProductivityCategory>
              label="Category"
              value={category}
              onChange={setCategory}
              options={CATEGORIES.map((c) => ({ value: c, label: CATEGORY[c].label }))}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="rule-scope">Scope</Label>
              <Select value={scope} onValueChange={(v) => setScope(v as RuleScope)}>
                <SelectTrigger id="rule-scope">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(['company', 'department', 'team', 'role', 'profile'] as RuleScope[]).map((s) => (
                    <SelectItem key={s} value={s}>
                      {SCOPE_LABEL[s]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {scope === 'role' ? (
              <div className="space-y-1.5">
                <Label htmlFor="rule-role">Role</Label>
                <Select value={role} onValueChange={(v) => setRole(v as Role)}>
                  <SelectTrigger id="rule-role">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(['EMPLOYEE', 'TEAM_LEAD', 'MANAGER', 'COMPANY_ADMIN'] as Role[]).map((r) => (
                      <SelectItem key={r} value={r}>
                        {ROLE_LABELS[r]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : scope !== 'company' ? (
              <div className="space-y-1.5">
                <Label htmlFor="rule-target">{SCOPE_LABEL[scope]}</Label>
                <Select value={scopeId} onValueChange={setScopeId}>
                  <SelectTrigger id="rule-target">
                    <SelectValue placeholder={scope === 'profile' ? 'Choose a work profile' : `Choose a ${scope}`} />
                  </SelectTrigger>
                  <SelectContent>
                    {targets.map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        {t.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending} disabled={!pattern.trim() || (needsTarget && !scopeId)}>
              Add rule
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function RulesTable({ rules, editable }: { rules: ProductivityRule[]; editable: boolean }) {
  const update = useUpdateRule()
  const remove = useDeleteRule()
  const [deleting, setDeleting] = useState<ProductivityRule | null>(null)
  return (
    <>
      <Table>
        <caption className="sr-only">Productivity rules</caption>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="pl-5">Application or website</TableHead>
            <TableHead>Applies to</TableHead>
            <TableHead>Category</TableHead>
            {editable && <TableHead className="pr-5" />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rules.map((rule) => (
            <TableRow key={rule.id}>
              <TableCell className="max-w-64 pl-5">
                <span className="flex min-w-0 items-center gap-2">
                  {rule.kind === 'website' ? <Globe className="size-3.5 shrink-0 text-muted-foreground" aria-label="Website" /> : <AppWindow className="size-3.5 shrink-0 text-muted-foreground" aria-label="Application" />}
                  <span className="truncate font-medium">{rule.pattern}</span>
                </span>
                {rule.note && <p className="truncate text-[11px] text-muted-foreground">{rule.note}</p>}
              </TableCell>
              <TableCell className="text-[13px]">
                {SCOPE_LABEL[rule.scope]}
                {rule.scope_ref && <span className="text-muted-foreground"> · {rule.scope_ref.name}</span>}
                {rule.role && <span className="text-muted-foreground"> · {ROLE_LABELS[rule.role]}</span>}
              </TableCell>
              <TableCell>
                {editable ? (
                  <Select value={rule.category} onValueChange={(v) => update.mutate({ id: rule.id, category: v }, { onError: (e) => toast.error(errorMessage(e)) })}>
                    <SelectTrigger size="sm" className="w-40" aria-label={`Category for ${rule.pattern}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CATEGORIES.map((c) => (
                        <SelectItem key={c} value={c}>
                          <span className={cn('size-2.5 rounded-sm', CATEGORY[c].swatch)} aria-hidden />
                          {CATEGORY[c].label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <span className="inline-flex items-center gap-1.5 text-[13px]">
                    <span className={cn('size-2.5 rounded-sm', CATEGORY[rule.category].swatch)} aria-hidden />
                    {CATEGORY[rule.category].label}
                  </span>
                )}
              </TableCell>
              {editable && (
                <TableCell className="pr-5 text-right">
                  <Button size="icon-sm" variant="ghost" aria-label={`Delete rule for ${rule.pattern}`} onClick={() => setDeleting(rule)}>
                    <Trash2 />
                  </Button>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this rule?"
        description={`${deleting?.pattern ?? ''} falls back to a broader rule, or becomes unclassified. All productivity figures are recalculated.`}
        confirmLabel="Delete rule"
        destructive
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => setDeleting(null) })}
      />
    </>
  )
}

export default function ProductivityRulesPage() {
  useDocumentTitle('Productivity rules')
  const { can } = usePermissions()
  const editable = can('POLICY_MANAGE')
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  const rules = useRules()
  const unclassified = useUnclassified(rangeFor('30d', timeZone), can('ACTIVITY_VIEW'))
  const recommended = useLoadRecommended()
  const [adding, setAdding] = useState<{ kind: RuleKind; pattern: string } | null>(null)
  const [filter, setFilter] = useState<'all' | RuleKind>('all')
  const visible = useMemo(() => (rules.data ?? []).filter((r) => filter === 'all' || r.kind === filter), [rules.data, filter])

  return (
    <RequirePermission permission={can('POLICY_MANAGE') ? 'POLICY_MANAGE' : 'ACTIVITY_VIEW'}>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="xl:col-span-2">
          <WorkProfilesCard editable={editable} />
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Rules</CardTitle>
            <CardDescription>
              {editable
                ? 'Classify applications and websites for the whole company, a department, a team, a permission role or a work profile.'
                : 'Only administrators can change rules.'}
            </CardDescription>
            {editable && (
              <CardAction className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  loading={recommended.isPending}
                  onClick={() =>
                    recommended.mutate(undefined, {
                      onSuccess: (r) => toast.success(r.added ? `Added ${r.added} starter rules` : 'All starter rules are already present'),
                    })
                  }
                >
                  <Sparkles /> Starter rules
                </Button>
                <Button size="sm" onClick={() => setAdding({ kind: 'app', pattern: '' })}>
                  <Plus /> Add rule
                </Button>
              </CardAction>
            )}
          </CardHeader>
          <div className="px-5 pt-3">
            <SegmentedControl<'all' | RuleKind>
              size="sm"
              label="Show"
              value={filter}
              onChange={setFilter}
              options={[
                { value: 'all', label: 'All' },
                { value: 'app', label: 'Applications' },
                { value: 'website', label: 'Websites' },
              ]}
            />
          </div>
          <div className="relative mt-3 overflow-x-auto border-t">
            {rules.isError ? (
              <WidgetError error={rules.error} onRetry={() => void rules.refetch()} />
            ) : !rules.data ? (
              <div className="p-5">
                <Skeleton className="h-40" />
              </div>
            ) : visible.length === 0 ? (
              <EmptyState
                size="sm"
                icon={ListPlus}
                title="No rules yet"
                description="Without rules everything is unclassified and no productivity insight is shown. Start with the starter rules or classify what people actually use."
              />
            ) : (
              <RulesTable rules={visible} editable={editable} />
            )}
          </div>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Not classified yet</CardTitle>
            <CardDescription>Most-used applications and websites no rule covers · last 30 days</CardDescription>
          </CardHeader>
          <div className="mt-3 border-t">
            {!unclassified.data ? (
              <div className="p-5">
                <Skeleton className="h-40" />
              </div>
            ) : unclassified.data.length === 0 ? (
              <EmptyState size="sm" icon={Sparkles} title="Everything is classified" description="All recorded activity in the last 30 days is covered by a rule." />
            ) : (
              <ul className="divide-y">
                {unclassified.data.map((item) => (
                  <li key={`${item.kind}:${item.key}`} className="flex items-center gap-3 px-5 py-2.5">
                    {item.kind === 'website' ? <Globe className="size-3.5 shrink-0 text-muted-foreground" aria-label="Website" /> : <AppWindow className="size-3.5 shrink-0 text-muted-foreground" aria-label="Application" />}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium">{item.name}</p>
                      <p className="text-[11px] text-muted-foreground tabular">
                        {formatSeconds(item.seconds)} · {item.employees} {item.employees === 1 ? 'person' : 'people'}
                      </p>
                    </div>
                    {editable && <ClassifyMenu kind={item.kind} pattern={item.key} name={item.name} />}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>

        {adding && <RuleDialog key={`${adding.kind}:${adding.pattern}`} open onOpenChange={(open) => !open && setAdding(null)} initial={adding} />}
      </div>
    </RequirePermission>
  )
}
