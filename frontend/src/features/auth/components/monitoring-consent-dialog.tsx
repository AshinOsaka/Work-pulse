import { Link } from 'react-router'
import { MonitorCheck } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useAcknowledgeMonitoring } from '@/features/auth/api'
import { useAuthStore } from '@/stores/auth-store'

/**
 * A one-time notice shown to a monitored person after they first sign in. Company devices may be
 * monitored, but the law (and good practice) expects people to be told; recording their
 * acknowledgement makes that explicit and auditable. It is shown once, then never again.
 */
export function MonitoringConsentDialog() {
  const user = useAuthStore((s) => s.user)
  const acknowledge = useAcknowledgeMonitoring()

  // Only people who are actually monitored (have an employee record) and haven't acknowledged yet.
  const open = Boolean(user?.employee_id) && user?.monitoring_acknowledged === false

  return (
    <Dialog open={open}>
      <DialogContent
        showCloseButton={false}
        onInteractOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
        className="sm:max-w-md"
      >
        <DialogHeader>
          <span className="mb-1 flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
            <MonitorCheck className="size-5" aria-hidden />
          </span>
          <DialogTitle>This is a monitored company device</DialogTitle>
          <DialogDescription>
            To run this work account, please acknowledge how your work activity is recorded.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-[13px] text-muted-foreground">
          <p>While you're signed in to the WorkPulse desktop agent on this company device, your workspace records:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>The applications and websites you use for work (domains only, where website tracking is on)</li>
            <li>Work hours, and whether you're active or idle</li>
            <li>Screenshots, if and when your workspace's policy takes them</li>
          </ul>
          <p className="text-foreground">
            It never records what you type, your passwords, your clipboard, or the contents of your messages and files.
          </p>
          <p>
            You can read exactly what is and isn't collected, and who can see it, any time in{' '}
            <Link to="/settings/privacy" className="font-medium text-primary hover:underline">
              Monitoring &amp; privacy
            </Link>
            .
          </p>
        </div>

        <Button className="w-full" onClick={() => acknowledge.mutate()} disabled={acknowledge.isPending}>
          {acknowledge.isPending ? 'Saving…' : 'I understand and acknowledge'}
        </Button>
      </DialogContent>
    </Dialog>
  )
}
