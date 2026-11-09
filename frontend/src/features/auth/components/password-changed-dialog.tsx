import { KeyRound } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useAuthStore } from '@/stores/auth-store'

/**
 * Shown on the sign-in screen after a password change or reset signed the person out (here or on another device).
 * The reason comes from the server ("password_changed") or from this browser's own change/reset.
 */
export function PasswordChangedDialog() {
  const reason = useAuthStore((s) => s.signOutReason)
  const dismiss = () => useAuthStore.getState().setSignOutReason(null)
  return (
    <Dialog open={reason === 'password_changed'} onOpenChange={(open) => !open && dismiss()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader className="items-center text-center sm:items-center sm:text-center">
          <span className="mb-1 flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <KeyRound className="size-6" aria-hidden />
          </span>
          <DialogTitle>Your password was changed</DialogTitle>
          <DialogDescription>
            For your security, you’ve been signed out on all your devices. Please sign in again with your new
            password.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="sm:justify-center">
          <Button className="w-full sm:w-auto" onClick={dismiss}>
            Sign in with new password
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
