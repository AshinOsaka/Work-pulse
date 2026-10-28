import { Eye } from 'lucide-react'

import { FormAlert } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { errorMessage } from '@/lib/api-client'
import type { LiveEmployee } from '@/types/api'

interface StartLiveDialogProps {
  target: LiveEmployee | null
  maxMinutes: number
  pending: boolean
  error: unknown
  onCancel: () => void
  onConfirm: (target: LiveEmployee) => void
}

/** A simple confirmation before a live stream starts: who you're viewing, in one line. */
export function StartLiveDialog({ target, pending, error, onCancel, onConfirm }: StartLiveDialogProps) {
  return (
    <Dialog open={target !== null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="sm:max-w-md">
        {target && (
          <>
            <DialogHeader>
              <DialogTitle>Start Live Stream?</DialogTitle>
              <DialogDescription>Starting a live stream will create an audit record.</DialogDescription>
            </DialogHeader>
            <div className="flex items-center gap-2 rounded-lg border bg-subtle px-3 py-2.5 text-[13px]">
              <Eye className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span className="text-muted-foreground">Viewing:</span>
              <span className="truncate font-medium">{target.employee.full_name}</span>
            </div>
            <p className="rounded-lg border bg-subtle px-3 py-2.5 text-[13px] text-muted-foreground">
              This action will start the live stream immediately after confirmation.
            </p>
            {error !== null && error !== undefined && <FormAlert>{errorMessage(error)}</FormAlert>}
            <DialogFooter>
              <Button variant="outline" onClick={onCancel} disabled={pending}>
                Cancel
              </Button>
              <Button onClick={() => onConfirm(target)} loading={pending}>
                Confirm &amp; Start Stream
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
