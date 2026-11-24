import { useState, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: ReactNode
  confirmLabel: string
  destructive?: boolean
  loading?: boolean
  onConfirm: () => void
  /** For actions that can't be undone: the confirm button only works after these exact words are typed. */
  confirmText?: string
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive = false,
  loading = false,
  onConfirm,
  confirmText,
}: ConfirmDialogProps) {
  const [typed, setTyped] = useState('')
  const matches = !confirmText || typed.trim() === confirmText.trim()
  const change = (next: boolean) => {
    if (!next) setTyped('')
    onOpenChange(next)
  }
  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent className="sm:max-w-md" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="pt-1 leading-relaxed">{description}</DialogDescription>
        </DialogHeader>
        {confirmText && (
          <div className="space-y-1.5">
            <Label htmlFor="confirm-text" className="text-[13px] font-normal">
              Type <span className="font-semibold">{confirmText}</span> to confirm
            </Label>
            <Input
              id="confirm-text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              spellCheck={false}
              onKeyDown={(e) => e.key === 'Enter' && matches && !loading && onConfirm()}
            />
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => change(false)} disabled={loading}>
            Cancel
          </Button>
          <Button variant={destructive ? 'destructive' : 'default'} loading={loading} disabled={!matches} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
