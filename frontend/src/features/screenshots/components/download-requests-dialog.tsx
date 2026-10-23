import { Download, Loader2, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { EmptyState } from '@/components/common/empty-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/misc'
import { useDeleteScreenshotRequest, useScreenshotRequests } from '@/features/screenshots/api'
import { errorMessage } from '@/lib/api-client'
import { formatDate, formatDateTime } from '@/lib/format'
import type { ScreenshotRequest, ScreenshotRequestStatus } from '@/types/api'

const STATUS: Record<ScreenshotRequestStatus, { label: string; variant: 'secondary' | 'destructive' | 'default' }> = {
  queued: { label: 'Queued', variant: 'secondary' },
  preparing: { label: 'Preparing', variant: 'secondary' },
  packaging: { label: 'Packaging', variant: 'secondary' },
  ready: { label: 'Ready', variant: 'default' },
  empty: { label: 'No screenshots', variant: 'secondary' },
  failed: { label: 'Failed', variant: 'destructive' },
  expired: { label: 'Expired', variant: 'secondary' },
}
const PENDING: ScreenshotRequestStatus[] = ['queued', 'preparing', 'packaging']

function bytes(n: number | null): string {
  if (!n) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let value = n
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i++
  }
  return `${value.toFixed(value < 10 && i > 0 ? 1 : 0)} ${units[i]}`
}

function Row({ request }: { request: ScreenshotRequest }) {
  const remove = useDeleteScreenshotRequest()
  const status = STATUS[request.status]
  const pending = PENDING.includes(request.status)
  return (
    <li className="flex flex-wrap items-center gap-3 px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium">{request.employee_name}</p>
        <p className="text-[12px] text-muted-foreground">
          {formatDate(request.day)}
          {request.screenshot_count != null && request.status !== 'empty' && ` · ${request.screenshot_count} images`}
          {request.size_bytes ? ` · ${bytes(request.size_bytes)}` : ''} · requested {formatDateTime(request.created_at)}
        </p>
        {request.error && request.status === 'failed' && (
          <p className="mt-0.5 text-[12px] text-destructive">{request.error}</p>
        )}
      </div>
      <Badge variant={status.variant} className="gap-1">
        {pending && <Loader2 className="size-3 animate-spin" aria-hidden />}
        {status.label}
      </Badge>
      {request.status === 'ready' && request.download_url && (
        <Button asChild size="sm" variant="outline">
          <a href={request.download_url} download>
            <Download /> Download
          </a>
        </Button>
      )}
      {!pending && (
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="Remove request"
          loading={remove.isPending}
          onClick={() => remove.mutate(request.id, { onError: (e) => toast.error(errorMessage(e)) })}
        >
          <Trash2 />
        </Button>
      )}
    </li>
  )
}

export function DownloadRequestsDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const requests = useScreenshotRequests(open)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Download requests</DialogTitle>
          <DialogDescription>
            Your screenshot download requests. Ready ZIPs are private to you and expire after a few days.
          </DialogDescription>
        </DialogHeader>
        {!requests.data ? (
          <div className="space-y-2">
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        ) : requests.data.length === 0 ? (
          <EmptyState
            size="sm"
            icon={Download}
            title="No requests yet"
            description="Use Raise Request to package a person's screenshots for a day."
          />
        ) : (
          <ul className="max-h-[60vh] divide-y overflow-y-auto rounded-lg border">
            {requests.data.map((r) => (
              <Row key={r.id} request={r} />
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  )
}
