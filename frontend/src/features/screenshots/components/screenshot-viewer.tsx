import { useEffect, useState } from 'react'
import { AppWindow, ChevronLeft, ChevronRight, Laptop, ShieldCheck, Trash2, X } from 'lucide-react'
import { Dialog as DialogPrimitive } from 'radix-ui'
import { toast } from 'sonner'

import { Spinner } from '@/components/ui/misc'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { PersonAvatar } from '@/components/common/person'
import { Button } from '@/components/ui/button'
import { useDeleteScreenshot, useScreenshotDetail } from '@/features/screenshots/api'
import { formatBytes } from '@/features/screenshots/format'
import { errorMessage } from '@/lib/api-client'
import { formatDate } from '@/lib/format'
import { usePermissions } from '@/stores/auth-store'
import type { ScreenshotItem } from '@/types/api'

interface ScreenshotViewerProps {
  items: ScreenshotItem[]
  index: number | null
  timeZone: string
  onIndexChange: (index: number | null) => void
}

function formatMoment(value: string, timeZone: string): string {
  return new Date(value).toLocaleString(undefined, {
    timeZone,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** Full-screen viewer. Each screenshot opened here is fetched individually, and that access is audited. */
export function ScreenshotViewer({ items, index, timeZone, onIndexChange }: ScreenshotViewerProps) {
  const { can } = usePermissions()
  const item = index !== null ? items[index] : undefined
  const detail = useScreenshotDetail(item?.id ?? null)
  const remove = useDeleteScreenshot()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [loaded, setLoaded] = useState<string | null>(null)
  const hasPrev = index !== null && index > 0
  const hasNext = index !== null && index < items.length - 1

  useEffect(() => {
    if (index !== null && index >= items.length) onIndexChange(items.length ? items.length - 1 : null)
  }, [index, items.length, onIndexChange])

  const go = (delta: number) => {
    if (index === null) return
    const next = index + delta
    if (next >= 0 && next < items.length) onIndexChange(next)
  }

  const data = detail.data?.id === item?.id ? detail.data : undefined
  const imageReady = data && loaded === data.image_url

  return (
    <DialogPrimitive.Root open={item !== undefined} onOpenChange={(open) => !open && onIndexChange(null)}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-neutral-950 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className="fixed inset-0 z-50 flex flex-col text-white outline-none lg:flex-row bg-neutral-950"
          onKeyDown={(e) => {
            if (e.key === 'ArrowLeft') go(-1)
            if (e.key === 'ArrowRight') go(1)
          }}
          aria-describedby={undefined}
        >
          {item && (
            <>
              <div className="relative flex min-h-0 flex-1 items-center justify-center p-3 sm:p-6">
                {/* Thumbnail first, swapped for the full image once it has loaded. */}
                <img
                  src={imageReady ? data.image_url : item.thumbnail_url}
                  alt={`Screenshot of ${item.employee.full_name}, ${formatMoment(item.captured_at, timeZone)}`}
                  referrerPolicy="no-referrer"
                  draggable={false}
                  className="max-h-full max-w-full rounded-md object-contain shadow-2xl select-none"
                  style={{ aspectRatio: `${item.width} / ${item.height}` }}
                />
                {data && !imageReady && (
                  <>
                    <img src={data.image_url} alt="" className="hidden" onLoad={() => setLoaded(data.image_url)} />
                    <span className="absolute inset-0 flex items-center justify-center" aria-live="polite">
                      <span className="flex items-center gap-2 rounded-full bg-black/60 px-3 py-1.5 text-[12px]">
                        <Spinner className="size-3.5" /> Loading full resolution…
                      </span>
                    </span>
                  </>
                )}
                {hasPrev && (
                  <button
                    type="button"
                    onClick={() => go(-1)}
                    aria-label="Previous screenshot"
                    className="absolute top-1/2 left-3 flex size-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 transition hover:bg-white/20 focus-visible:ring-[3px] focus-visible:ring-white/50 focus-visible:outline-none"
                  >
                    <ChevronLeft className="size-5" />
                  </button>
                )}
                {hasNext && (
                  <button
                    type="button"
                    onClick={() => go(1)}
                    aria-label="Next screenshot"
                    className="absolute top-1/2 right-3 flex size-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 transition hover:bg-white/20 focus-visible:ring-[3px] focus-visible:ring-white/50 focus-visible:outline-none"
                  >
                    <ChevronRight className="size-5" />
                  </button>
                )}
              </div>

              <aside className="flex shrink-0 flex-col gap-4 border-t border-white/10 bg-neutral-900 p-4 text-[13px] lg:w-80 lg:border-t-0 lg:border-l lg:p-5">
                <div className="flex items-start gap-3">
                  <PersonAvatar name={item.employee.full_name} seed={item.employee.id} className="size-9" />
                  <div className="min-w-0 flex-1">
                    <DialogPrimitive.Title className="truncate font-semibold">{item.employee.full_name}</DialogPrimitive.Title>
                    <p className="text-white/60">{formatMoment(item.captured_at, timeZone)}</p>
                  </div>
                  <DialogPrimitive.Close
                    aria-label="Close viewer"
                    className="rounded-md p-1.5 text-white/70 transition hover:bg-white/10 hover:text-white focus-visible:ring-[3px] focus-visible:ring-white/50 focus-visible:outline-none"
                  >
                    <X className="size-4" />
                  </DialogPrimitive.Close>
                </div>

                {detail.isError ? (
                  <p className="rounded-md bg-red-500/15 px-3 py-2 text-red-200">{errorMessage(detail.error)}</p>
                ) : (
                  <dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-2">
                    <dt className="text-white/50">Application</dt>
                    <dd className="flex min-w-0 items-center gap-1.5">
                      <AppWindow className="size-3.5 shrink-0 text-white/50" />
                      <span className="truncate">{data ? (data.application ?? 'Not recorded') : '…'}</span>
                    </dd>
                    <dt className="text-white/50">Device</dt>
                    <dd className="flex min-w-0 items-center gap-1.5">
                      <Laptop className="size-3.5 shrink-0 text-white/50" />
                      <span className="truncate">{data ? (data.device_name ?? '—') : '…'}</span>
                    </dd>
                    <dt className="text-white/50">Resolution</dt>
                    <dd className="tabular">
                      {item.width} × {item.height}
                    </dd>
                    <dt className="text-white/50">Size</dt>
                    <dd className="tabular">{data ? formatBytes(data.size_bytes) : '…'}</dd>
                    <dt className="text-white/50">Deleted on</dt>
                    <dd>{data ? formatDate(data.expires_at) : '…'}</dd>
                  </dl>
                )}

                <p className="flex gap-2 rounded-md bg-white/5 px-3 py-2 text-[12px] text-white/60">
                  <ShieldCheck className="mt-0.5 size-3.5 shrink-0" />
                  Opening a screenshot is recorded in the audit log. Image links are private and expire after a few
                  minutes.
                </p>

                <div className="mt-auto flex items-center justify-between gap-2">
                  <span className="text-[12px] text-white/50 tabular">
                    {(index ?? 0) + 1} of {items.length}
                  </span>
                  {can('POLICY_MANAGE') && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-red-300 hover:bg-red-500/15 hover:text-red-200"
                      onClick={() => setConfirmDelete(true)}
                    >
                      <Trash2 /> Delete
                    </Button>
                  )}
                </div>
              </aside>

              <ConfirmDialog
                open={confirmDelete}
                onOpenChange={setConfirmDelete}
                title="Delete this screenshot?"
                description="Use this for a capture that should not have been taken. It is permanently removed; the deletion is recorded in the audit log."
                confirmLabel="Delete screenshot"
                destructive
                loading={remove.isPending}
                onConfirm={() =>
                  remove.mutate(item.id, {
                    onSuccess: () => {
                      setConfirmDelete(false)
                      toast.success('Screenshot deleted')
                    },
                    onError: (error) => toast.error(errorMessage(error)),
                  })
                }
              />
            </>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
