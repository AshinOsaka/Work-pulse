import { useState } from 'react'
import { LogOut, MonitorSmartphone, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/misc'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useRevokeOtherSessions, useRevokeSession, useSessions } from '@/features/security/api'
import { errorMessage } from '@/lib/api-client'
import { formatDateTime, formatRelative } from '@/lib/format'

export function SessionsCard() {
  const sessions = useSessions()
  const revoke = useRevokeSession()
  const revokeOthers = useRevokeOtherSessions()
  const [confirmAll, setConfirmAll] = useState(false)
  const others = (sessions.data ?? []).filter((s) => !s.current).length

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MonitorSmartphone className="size-4 text-muted-foreground" aria-hidden /> Where you're signed in
        </CardTitle>
        <CardDescription>Signing a session out takes effect immediately, including its live connections.</CardDescription>
        {others > 0 && (
          <CardAction>
            <Button size="sm" variant="outline" onClick={() => setConfirmAll(true)}>
              <LogOut /> Sign out everywhere else
            </Button>
          </CardAction>
        )}
      </CardHeader>
      {sessions.isPending ? (
        <div className="space-y-2 px-6 pb-6">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : sessions.isError ? (
        <WidgetError error={sessions.error} onRetry={() => void sessions.refetch()} />
      ) : (
        <ul aria-label="Sign-in sessions" className="divide-y border-t">
          {sessions.data.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2 text-[13px] font-medium">
                  {s.device}
                  {s.current && <Badge variant="soft">This browser</Badge>}
                  {s.mfa && (
                    <Badge variant="success" title="Signed in with two-step verification">
                      <ShieldCheck className="size-3" aria-hidden /> 2-step
                    </Badge>
                  )}
                </p>
                <p className="text-[12px] text-muted-foreground">
                  {s.ip_address ?? 'Unknown address'} · active {formatRelative(s.last_seen_at)} · signed in {formatDateTime(s.created_at)}
                </p>
              </div>
              {!s.current && (
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Sign out ${s.device}`}
                  loading={revoke.isPending && revoke.variables === s.id}
                  onClick={() =>
                    revoke.mutate(s.id, {
                      onSuccess: () => toast.success(`${s.device} signed out`),
                      onError: (e) => toast.error(errorMessage(e)),
                    })
                  }
                >
                  Sign out
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={confirmAll}
        onOpenChange={setConfirmAll}
        title="Sign out everywhere else?"
        description={`${others} other ${others === 1 ? 'session' : 'sessions'} will be signed out immediately. This browser stays signed in.`}
        confirmLabel="Sign out others"
        loading={revokeOthers.isPending}
        onConfirm={() =>
          revokeOthers.mutate(undefined, {
            onSuccess: (r) => {
              toast.success(`Signed out ${r.revoked} ${r.revoked === 1 ? 'session' : 'sessions'}`)
              setConfirmAll(false)
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </Card>
  )
}
