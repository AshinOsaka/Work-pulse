import { useState } from 'react'
import { Check, Handshake, Pencil, Plus, Trash2, UsersRound, X } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/common/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/form-controls'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/misc'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { formatClock, formatDay } from '@/features/activity/format'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useDeleteClaim, useReviewClaim, useTimeClaims, type TimeClaimQuery } from '@/features/time-claims/api'
import { LogTimeDialog } from '@/features/time-claims/log-time-dialog'
import { KIND_LABEL, STATUS, formatMinutes } from '@/features/time-claims/meta'
import { errorMessage } from '@/lib/api-client'
import { useAuthStore, usePermissions } from '@/stores/auth-store'
import type { TimeClaim } from '@/types/api'

type View = 'pending' | 'all' | 'mine'
const PAGE_SIZE = 25

function RejectDialog({ claim, onClose }: { claim: TimeClaim; onClose: () => void }) {
  const review = useReviewClaim()
  const [note, setNote] = useState('')
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Reject {formatMinutes(claim.minutes)} from {claim.employee.name}?</DialogTitle>
          <DialogDescription>It stops counting in their attendance. They are told, with your reason.</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="reject-note">Reason</Label>
          <Textarea id="reject-note" value={note} onChange={(e) => setNote(e.target.value)} className="min-h-16 text-[13px]" maxLength={300} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            loading={review.isPending}
            onClick={() =>
              review.mutate(
                { id: claim.id, decision: 'reject', note: note.trim() },
                {
                  onSuccess: () => {
                    toast.success('Rejected')
                    onClose()
                  },
                  onError: (e) => toast.error(errorMessage(e)),
                },
              )
            }
          >
            Reject
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ClaimRow({ claim, showPerson, timeZone }: { claim: TimeClaim; showPerson: boolean; timeZone: string }) {
  const review = useReviewClaim()
  const remove = useDeleteClaim()
  const [rejecting, setRejecting] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [editingClaim, setEditingClaim] = useState(false)
  const myEmployeeId = useAuthStore((s) => s.user?.employee_id)
  const mine = claim.employee.id === myEmployeeId
  const status = STATUS[claim.status]
  return (
    <li className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
          {showPerson && <span className="font-semibold">{claim.employee.name}</span>}
          <span className="font-medium">{KIND_LABEL[claim.kind]}</span>
          <span className="text-muted-foreground">with {claim.with_whom}</span>
          <Badge variant={status.variant}>{status.label}</Badge>
          {claim.status === 'approved' && claim.auto_approved && !claim.reviewed_by && (
            <span className="text-[11px] text-muted-foreground">within the daily limit</span>
          )}
        </div>
        <p className="text-[12px] text-muted-foreground tabular">
          {formatDay(claim.day)} · {formatClock(claim.started_at, timeZone)} – {formatClock(claim.ended_at, timeZone)} ·{' '}
          <span className="font-medium text-foreground">{formatMinutes(claim.minutes)}</span>
        </p>
        {claim.note && <p className="text-[12px] text-foreground/80">{claim.note}</p>}
        {claim.added_by ? (
          <p className="text-[12px] text-muted-foreground">Added by {claim.added_by}</p>
        ) : claim.reviewed_by && (
          <p className="text-[12px] text-muted-foreground">
            {claim.status === 'rejected' ? 'Rejected' : 'Approved'} by {claim.reviewed_by}
            {claim.review_note && <> · “{claim.review_note}”</>}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {claim.can_review && claim.status !== 'approved' && (
          <Button
            size="sm"
            loading={review.isPending}
            onClick={() =>
              review.mutate(
                { id: claim.id, decision: 'approve' },
                { onSuccess: () => toast.success('Approved: it now counts in attendance'), onError: (e) => toast.error(errorMessage(e)) },
              )
            }
          >
            <Check /> Approve
          </Button>
        )}
        {claim.can_review && claim.status !== 'rejected' && (
          <Button size="sm" variant="outline" onClick={() => setRejecting(true)}>
            <X /> Reject
          </Button>
        )}
        {claim.can_edit && (
          <Button size="sm" variant="ghost" aria-label="Edit" onClick={() => setEditingClaim(true)}>
            <Pencil />
          </Button>
        )}
        {claim.can_delete && (
          <Button size="sm" variant="ghost" aria-label="Delete" onClick={() => setDeleting(true)}>
            <Trash2 />
          </Button>
        )}
      </div>
      {rejecting && <RejectDialog claim={claim} onClose={() => setRejecting(false)} />}
      {editingClaim && (
        <LogTimeDialog mode={{ kind: 'edit', claim, asManager: claim.can_review }} onOpenChange={setEditingClaim} />
      )}
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={mine ? 'Delete this time?' : `Delete ${claim.employee.name}'s time?`}
        description={
          mine
            ? `${formatMinutes(claim.minutes)} stops counting in your attendance. This can't be undone.`
            : `${formatMinutes(claim.minutes)} stops counting in ${claim.employee.name}'s attendance. They are told. This can't be undone.`
        }
        confirmLabel="Delete"
        destructive
        loading={remove.isPending}
        onConfirm={() =>
          remove.mutate(claim.id, {
            onSuccess: () => {
              setDeleting(false)
              toast.success('Time deleted')
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </li>
  )
}

export default function TimeClaimsPage() {
  const { can } = usePermissions()
  const reviewer = can('TIME_CLAIM_MANAGE')
  const hasEmployee = useAuthStore((s) => Boolean(s.user?.employee_id))
  const timeZone = useAuthStore((s) => s.company?.timezone ?? 'UTC')
  // Managers start on everyone's claims (newest first), so time counted within the daily limit is seen too.
  const [view, setView] = useState<View>(reviewer ? 'all' : 'mine')
  const [page, setPage] = useState(1)
  const [logging, setLogging] = useState(false)
  const [loggingTeam, setLoggingTeam] = useState(false)
  const query: TimeClaimQuery = {
    status: view === 'pending' ? 'pending' : undefined,
    mine: view === 'mine' || undefined,
    page,
    page_size: PAGE_SIZE,
  }
  const list = useTimeClaims(query)
  const data = list.data
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-6">
      <PageHeader
        title="Time claims"
        icon={Handshake}
        description="Log meetings and visits away from the computer."
        actions={
          <>
            {reviewer && (
              <Button variant="outline" onClick={() => setLoggingTeam(true)}>
                <UsersRound /> Log time for team
              </Button>
            )}
            {hasEmployee && (
              <Button onClick={() => setLogging(true)}>
                <Plus /> Log time
              </Button>
            )}
          </>
        }
      />
      <Card className="overflow-hidden">
        {reviewer && (
          <div className="flex flex-wrap items-center gap-3 border-b px-4 py-3">
            <SegmentedControl<View>
              label="Show"
              size="sm"
              value={view}
              onChange={(v) => {
                setView(v)
                setPage(1)
              }}
              options={[
                { value: 'all', label: 'All' },
                { value: 'pending', label: `Waiting for approval${data ? ` ${data.pending_for_me}` : ''}` },
                ...(hasEmployee ? [{ value: 'mine' as View, label: 'Mine' }] : []),
              ]}
            />
          </div>
        )}
        {list.isError ? (
          <WidgetError error={list.error} onRetry={() => void list.refetch()} />
        ) : !data ? (
          <div className="space-y-2 p-4">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={Handshake}
            title={view === 'pending' ? 'Nothing waiting for approval' : 'No time logged yet'}
            description={
              view === 'pending'
                ? 'Time over the daily limit appears here for you to approve or reject.'
                : 'Log a meeting, client visit or call so it counts in attendance.'
            }
            action={
              hasEmployee && view !== 'pending' ? (
                <Button size="sm" onClick={() => setLogging(true)}>
                  <Plus /> Log time
                </Button>
              ) : undefined
            }
          />
        ) : (
          <ul className="divide-y">
            {data.items.map((c) => (
              <ClaimRow key={c.id} claim={c} showPerson={reviewer && view !== 'mine'} timeZone={timeZone} />
            ))}
          </ul>
        )}
        {data && pages > 1 && (
          <div className="flex items-center justify-end gap-2 border-t px-4 py-2.5 text-[12px] text-muted-foreground">
            Page {page} of {pages}
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        )}
      </Card>
      {logging && data && <LogTimeDialog mode={{ kind: 'self', autoMinutes: data.auto_minutes }} onOpenChange={setLogging} />}
      {loggingTeam && <LogTimeDialog mode={{ kind: 'team' }} onOpenChange={setLoggingTeam} />}
    </div>
  )
}
