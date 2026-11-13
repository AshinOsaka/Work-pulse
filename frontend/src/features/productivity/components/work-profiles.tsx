import { useState, type FormEvent } from 'react'
import { BriefcaseBusiness, ListChecks, Pencil, Plus, RotateCcw, Save, Trash2, Users } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { FormAlert, FormField } from '@/components/common/form-field'
import { AvatarGroup } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/form-controls'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/misc'
import { useEmployeeOptions } from '@/features/people/api'
import {
  useCreateProfile,
  useCreateRule,
  useDeleteProfile,
  useDeleteRule,
  useDeleteTemplate,
  useProfileTemplates,
  useRules,
  useSaveTemplate,
  useSetProfileMembers,
  useUpdateProfile,
  useUpdateRule,
  useWorkProfiles,
} from '@/features/productivity/api'
import { ruleKey, RuleListEditor } from '@/features/productivity/components/rule-list-editor'
import { CATEGORY } from '@/features/productivity/meta'
import { AssigneePicker } from '@/features/work/components/assignee-picker'
import { ApiError, errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import type { EmployeeRef, ProductivityCategory, ProfileTemplate, TemplateRule, WorkProfile } from '@/types/api'

const BLANK = '__blank__'
const BLANK_TEMPLATE = { key: BLANK, name: 'Blank', description: 'No rules yet; add your own.' }

const sameRules = (a: TemplateRule[], b: TemplateRule[]) =>
  a.length === b.length && a.every((r) => b.some((x) => x.kind === r.kind && x.pattern === r.pattern && x.category === r.category))

/** Local add / re-categorise / remove for a list of rules that is saved later as a whole. */
function useLocalRules(initial: TemplateRule[]) {
  const [rules, setRules] = useState<TemplateRule[]>(initial)
  return {
    rules,
    setRules,
    onAdd: (rule: TemplateRule) => setRules((list) => [...list, rule]),
    onCategory: (rule: TemplateRule, category: ProductivityCategory) =>
      setRules((list) => list.map((r) => (ruleKey(r) === ruleKey(rule) ? { ...r, category } : r))),
    onRemove: (rule: TemplateRule) => setRules((list) => list.filter((r) => ruleKey(r) !== ruleKey(rule))),
  }
}

/** Create or edit a "Start from" template. Templates only seed new profiles; existing profiles never change. */
function TemplateDialog({
  template,
  initialRules,
  onOpenChange,
  onSaved,
  onDeleted,
}: {
  template: ProfileTemplate | null
  initialRules?: TemplateRule[]
  onOpenChange: (open: boolean) => void
  onSaved: (template: ProfileTemplate) => void
  onDeleted: (key: string) => void
}) {
  const save = useSaveTemplate()
  const remove = useDeleteTemplate()
  const [name, setName] = useState(template?.name ?? '')
  const [description, setDescription] = useState(template?.description ?? '')
  const local = useLocalRules(template?.rules ?? initialRules ?? [])
  const [confirming, setConfirming] = useState(false)
  const errors = save.error instanceof ApiError ? save.error.fieldErrors : {}
  const resettable = Boolean(template?.built_in && template.customized)
  const deletable = Boolean(template && !template.built_in)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate(
      { key: template?.key ?? null, name: name.trim(), description: description.trim(), rules: local.rules },
      {
        onSuccess: (t) => {
          toast.success(template ? `${t.name} template saved` : `${t.name} template added`)
          onSaved(t)
          onOpenChange(false)
        },
      },
    )
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <form onSubmit={submit} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>{template ? `Edit ${template.name} template` : 'New template'}</DialogTitle>
            <DialogDescription>
              A starting point for new work profiles. Saving it doesn&apos;t change profiles already created from it.
            </DialogDescription>
          </DialogHeader>
          {save.error && !Object.keys(errors).length && <FormAlert>{errorMessage(save.error)}</FormAlert>}
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} maxLength={60} required placeholder="e.g. Ticketing" />
            <FormField
              label="Description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              error={errors.description}
              maxLength={200}
              placeholder="e.g. Flights, visas and bookings."
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tpl-rules-pattern">Rules ({local.rules.length})</Label>
            <RuleListEditor idPrefix="tpl-rules" rules={local.rules} onAdd={local.onAdd} onCategory={local.onCategory} onRemove={local.onRemove} />
            {errors.rules && <p className="text-[12px] text-destructive">{errors.rules}</p>}
          </div>
          <DialogFooter className="sm:justify-between">
            <div>
              {(resettable || deletable) && (
                <Button type="button" variant="ghost" className={cn(deletable && 'text-destructive hover:text-destructive')} onClick={() => setConfirming(true)}>
                  {resettable ? (
                    <>
                      <RotateCcw /> Reset to default
                    </>
                  ) : (
                    <>
                      <Trash2 /> Delete template
                    </>
                  )}
                </Button>
              )}
            </div>
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={save.isPending} disabled={name.trim().length < 2}>
                {template ? 'Save template' : 'Add template'}
              </Button>
            </div>
          </DialogFooter>
        </form>
        {template && (
          <ConfirmDialog
            open={confirming}
            onOpenChange={setConfirming}
            title={resettable ? `Reset ${template.name} to default?` : `Delete the ${template.name} template?`}
            description={
              resettable
                ? 'Your changes to this template are discarded and the WorkPulse version comes back. Existing profiles keep their rules.'
                : 'It is removed from Start from. Profiles already created from it keep their rules.'
            }
            confirmLabel={resettable ? 'Reset template' : 'Delete template'}
            destructive={!resettable}
            loading={remove.isPending}
            onConfirm={() =>
              remove.mutate(template.key, {
                onSuccess: () => {
                  toast.success(resettable ? `${template.name} reset to default` : `${template.name} template deleted`)
                  setConfirming(false)
                  onDeleted(template.key)
                  onOpenChange(false)
                },
                onError: (e) => toast.error(errorMessage(e)),
              })
            }
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

type TemplateEdit = { template: ProfileTemplate | null; initialRules?: TemplateRule[] }

function NewProfileDialog({ onOpenChange }: { onOpenChange: (open: boolean) => void }) {
  const templates = useProfileTemplates()
  const create = useCreateProfile()
  const [template, setTemplate] = useState<string>(BLANK)
  const [name, setName] = useState('')
  const local = useLocalRules([])
  const [editing, setEditing] = useState<TemplateEdit | null>(null)
  const chosen = templates.data?.find((t) => t.key === template)
  const changed = !sameRules(local.rules, chosen?.rules ?? [])
  const errors = create.error instanceof ApiError ? create.error.fieldErrors : {}

  const apply = (t: ProfileTemplate | null) => {
    setTemplate(t?.key ?? BLANK)
    local.setRules(t?.rules ?? [])
    if (t && (!name || templates.data?.some((x) => x.name === name))) setName(t.name)
  }
  const pick = (key: string) => apply(templates.data?.find((x) => x.key === key) ?? null)
  const submit = (event: FormEvent) => {
    event.preventDefault()
    create.mutate(
      { name: name.trim(), template: template === BLANK ? null : template, rules: local.rules },
      {
        onSuccess: (p) => {
          toast.success(`${p.name} created${p.rule_count ? ` with ${p.rule_count} rules` : ''}`)
          onOpenChange(false)
        },
      },
    )
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <form onSubmit={submit} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>New work profile</DialogTitle>
            <DialogDescription>
              A job role with its own activity context. Its rules apply to its members on top of the company, department and team rules.
            </DialogDescription>
          </DialogHeader>
          {create.error && !Object.keys(errors).length && <FormAlert>{errorMessage(create.error)}</FormAlert>}
          <fieldset className="space-y-2">
            <legend className="mb-1.5 text-[13px] font-medium">Start from</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              {[null, ...(templates.data ?? [])].map((full: ProfileTemplate | null) => {
                const t = full ?? BLANK_TEMPLATE
                const tag = full && (full.built_in ? (full.customized ? 'Edited' : null) : 'Custom')
                return (
                  <div key={t.key} className="group relative">
                    <button
                      type="button"
                      aria-pressed={template === t.key}
                      onClick={() => pick(t.key)}
                      className={cn(
                        'h-full w-full rounded-lg border p-3 pr-8 text-left transition hover:border-primary/50',
                        template === t.key && 'border-primary bg-primary-soft/40 ring-1 ring-primary',
                      )}
                    >
                      <span className="flex items-center gap-1.5 text-[13px] font-medium">
                        {t.name}
                        {tag && <span className="rounded bg-muted px-1 py-px text-[10px] font-medium text-muted-foreground">{tag}</span>}
                      </span>
                      <span className="line-clamp-2 block text-[11px] text-muted-foreground">{t.description || `${full?.rules.length ?? 0} rules`}</span>
                    </button>
                    {full && (
                      <Button
                        type="button"
                        size="icon-sm"
                        variant="ghost"
                        className="absolute top-1.5 right-1.5 size-7 opacity-0 transition group-hover:opacity-100 focus-visible:opacity-100"
                        aria-label={`Edit the ${t.name} template`}
                        title="Edit template"
                        onClick={() => setEditing({ template: full })}
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                    )}
                  </div>
                )
              })}
              {templates.data ? (
                <button
                  type="button"
                  onClick={() => setEditing({ template: null })}
                  className="flex min-h-16 items-center justify-center gap-1.5 rounded-lg border border-dashed p-3 text-[13px] font-medium text-muted-foreground transition hover:border-primary/50 hover:text-foreground"
                >
                  <Plus className="size-4" aria-hidden /> New template
                </button>
              ) : (
                <Skeleton className="h-16 sm:col-span-2" />
              )}
            </div>
          </fieldset>
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Label htmlFor="new-profile-rules-pattern">Rules it starts with ({local.rules.length})</Label>
              <span className="flex items-center gap-1">
                {changed && chosen && (
                  <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-[12px]" onClick={() => local.setRules(chosen.rules)}>
                    <RotateCcw /> Undo changes
                  </Button>
                )}
                {changed && local.rules.length > 0 && (
                  <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-[12px]" onClick={() => setEditing({ template: null, initialRules: local.rules })}>
                    <Save /> Save as template
                  </Button>
                )}
              </span>
            </div>
            <RuleListEditor idPrefix="new-profile-rules" rules={local.rules} onAdd={local.onAdd} onCategory={local.onCategory} onRemove={local.onRemove} />
            <p className="text-[11px] text-muted-foreground">Changes here apply to this profile only. To change a template for next time, use its pencil.</p>
          </div>
          <FormField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} maxLength={60} required />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending} disabled={name.trim().length < 2}>
              Create profile
            </Button>
          </DialogFooter>
        </form>
        {editing && (
          <TemplateDialog
            key={editing.template?.key ?? 'new'}
            template={editing.template}
            initialRules={editing.initialRules}
            onOpenChange={(open) => !open && setEditing(null)}
            onSaved={(t) => {
              // A new template, or the one in use, is picked with its saved rules.
              if (!editing.template || editing.template.key === template) apply(t)
            }}
            onDeleted={(key) => {
              // A deleted or reset template that was in use goes back to Blank.
              if (key === template) apply(null)
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

/** An existing profile's own rules. Every change is saved at once and productivity figures are recalculated. */
function ProfileRulesDialog({ profile, onOpenChange }: { profile: WorkProfile; onOpenChange: (open: boolean) => void }) {
  const all = useRules()
  const create = useCreateRule()
  const update = useUpdateRule()
  const remove = useDeleteRule()
  const mine = (all.data ?? []).filter((r) => r.scope === 'profile' && r.scope_ref?.id === profile.id)
  const byKey = new Map(mine.map((r) => [ruleKey(r), r]))
  const busy = create.isPending || update.isPending || remove.isPending
  const fail = (e: unknown) => toast.error(errorMessage(e))

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{profile.name} rules</DialogTitle>
          <DialogDescription>
            Applications and websites for this profile&apos;s members. They override team, department, role and company rules. Changes are saved
            at once and productivity figures are recalculated.
          </DialogDescription>
        </DialogHeader>
        {all.isError ? (
          <FormAlert>{errorMessage(all.error)}</FormAlert>
        ) : !all.data ? (
          <Skeleton className="h-40" />
        ) : (
          <RuleListEditor
            idPrefix={`profile-${profile.id}`}
            rules={mine}
            disabled={busy}
            onAdd={(r) => create.mutate({ ...r, scope: 'profile', scope_id: profile.id }, { onSuccess: () => toast.success(`${r.pattern} added`), onError: fail })}
            onCategory={(r, category) => {
              const rule = byKey.get(ruleKey(r))
              if (rule) update.mutate({ id: rule.id, category }, { onSuccess: () => toast.success(`${r.pattern} is now ${CATEGORY[category].label.toLowerCase()}`), onError: fail })
            }}
            onRemove={(r) => {
              const rule = byKey.get(ruleKey(r))
              if (rule) remove.mutate(rule.id, { onSuccess: () => toast.success(`${r.pattern} removed`), onError: fail })
            }}
          />
        )}
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function MembersDialog({ profile, onOpenChange }: { profile: WorkProfile; onOpenChange: (open: boolean) => void }) {
  const people = useEmployeeOptions()
  const save = useSetProfileMembers()
  const [ids, setIds] = useState(profile.members.map((m) => m.id))
  const everyone: EmployeeRef[] = (people.data ?? []).map((p) => ({ id: p.id, full_name: p.full_name, email: '', job_title: p.job_title ?? null, status: 'active' }))
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Members of {profile.name}</DialogTitle>
          <DialogDescription>Each person has at most one work profile; adding someone here moves them from any other profile.</DialogDescription>
        </DialogHeader>
        <AssigneePicker members={everyone} value={ids} onChange={setIds} label={`${profile.name} members`} placeholder="Add people" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            loading={save.isPending}
            onClick={() =>
              save.mutate(
                { id: profile.id, employee_ids: ids },
                {
                  onSuccess: () => {
                    toast.success('Members updated')
                    onOpenChange(false)
                  },
                  onError: (e) => toast.error(errorMessage(e)),
                },
              )
            }
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Credit idle time to active when a Productive app/site is in the foreground (reading a GDS, a CRM, a ticket). */
function AppAwareIdleToggle({ profile, editable }: { profile: WorkProfile; editable: boolean }) {
  const update = useUpdateProfile()
  const id = `app-aware-${profile.id}`
  return (
    <div className="flex items-center gap-2.5 rounded-lg border bg-subtle px-3 py-2">
      <Switch
        id={id}
        checked={profile.app_aware_idle}
        disabled={!editable || update.isPending}
        onCheckedChange={(v) =>
          update.mutate(
            { id: profile.id, app_aware_idle: v },
            {
              onSuccess: () => toast.success(v ? 'Reading counts as active for this profile' : 'Reading no longer counts as active'),
              onError: (e) => toast.error(errorMessage(e)),
            },
          )
        }
      />
      <Label htmlFor={id} className="cursor-pointer text-[12px] font-medium leading-snug text-foreground">
        Count reading as active
      </Label>
    </div>
  )
}

/** Job roles (Developer, Designer, Accountant, Sales, Support…): each with its own activity context. */
export function WorkProfilesCard({ editable }: { editable: boolean }) {
  const profiles = useWorkProfiles()
  const remove = useDeleteProfile()
  const [creating, setCreating] = useState(false)
  const [members, setMembers] = useState<WorkProfile | null>(null)
  const [rulesFor, setRulesFor] = useState<WorkProfile | null>(null)
  const [deleting, setDeleting] = useState<WorkProfile | null>(null)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BriefcaseBusiness className="size-4 text-muted-foreground" aria-hidden /> Work profiles
        </CardTitle>
        <CardDescription>
          App and website rules for each job role. They override team, department, role and company rules.
        </CardDescription>
        {editable && (
          <CardAction>
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus /> New profile
            </Button>
          </CardAction>
        )}
      </CardHeader>
      <div className="mt-3 border-t">
        {!profiles.data ? (
          <div className="p-5">
            <Skeleton className="h-20" />
          </div>
        ) : profiles.data.length === 0 ? (
          <EmptyState
            size="sm"
            icon={BriefcaseBusiness}
            title="No work profiles yet"
            description={editable ? 'Start from a Developer, Designer, Accountant, Sales or Support template, then assign people.' : 'An administrator can add them.'}
          />
        ) : (
          <ul className="divide-y">
            {profiles.data.map((p) => (
              <li key={p.id} className="space-y-2.5 px-5 py-3">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium">{p.name}</p>
                    <p className="text-[12px] text-muted-foreground">
                      {p.rule_count} rule{p.rule_count === 1 ? '' : 's'} · {p.members.length} {p.members.length === 1 ? 'person' : 'people'}
                      {p.description && ` · ${p.description}`}
                    </p>
                  </div>
                  <AvatarGroup people={p.members} max={6} />
                  {editable && (
                    <span className="flex gap-1">
                      <Button size="sm" variant="outline" onClick={() => setRulesFor(p)}>
                        <ListChecks /> Rules
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setMembers(p)}>
                        <Users /> Members
                      </Button>
                      <Button size="icon-sm" variant="ghost" aria-label={`Delete ${p.name}`} onClick={() => setDeleting(p)}>
                        <Trash2 />
                      </Button>
                    </span>
                  )}
                </div>
                {(editable || p.app_aware_idle) && <AppAwareIdleToggle profile={p} editable={editable} />}
              </li>
            ))}
          </ul>
        )}
      </div>
      {creating && <NewProfileDialog onOpenChange={setCreating} />}
      {rulesFor && <ProfileRulesDialog key={rulesFor.id} profile={rulesFor} onOpenChange={(open) => !open && setRulesFor(null)} />}
      {members && <MembersDialog key={members.id} profile={members} onOpenChange={(open) => !open && setMembers(null)} />}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? ''}?`}
        description="Its rules are removed and its members fall back to the company, department and team rules. All productivity figures are recalculated."
        confirmLabel="Delete profile"
        destructive
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => setDeleting(null), onError: (e) => toast.error(errorMessage(e)) })}
      />
    </Card>
  )
}
