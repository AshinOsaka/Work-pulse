import { useState, type FormEvent } from 'react'
import { Check, Copy, Download, KeyRound, ShieldCheck, ShieldOff, Smartphone } from 'lucide-react'
import { toast } from 'sonner'

import { FormAlert, FormField, PasswordField } from '@/components/common/form-field'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useBeginMfaSetup, useDisableMfa, useEnableMfa, useRegenerateRecoveryCodes, type MfaSetup } from '@/features/security/api'
import { ApiError, errorMessage } from '@/lib/api-client'
import { useAuthStore } from '@/stores/auth-store'

function fieldError(error: unknown, field: string): string | undefined {
  if (!(error instanceof ApiError)) return undefined
  const details = error.details as { field?: string } | null
  return details?.field === field ? error.message : error.fieldErrors[field]
}

function RecoveryCodes({ codes }: { codes: string[] }) {
  const [copied, setCopied] = useState(false)
  const text = codes.join('\n')
  const copy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    toast.success('Recovery codes copied')
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([`WorkPulse recovery codes\nEach code works once.\n\n${text}\n`], { type: 'text/plain' }))
    const link = Object.assign(document.createElement('a'), { href: url, download: 'workpulse-recovery-codes.txt' })
    link.click()
    URL.revokeObjectURL(url)
  }
  return (
    <div className="space-y-3">
      <p className="text-[13px] text-muted-foreground">
        If you lose your phone, each of these codes lets you sign in once. Store them somewhere safe, such as a password manager. They
        won't be shown again.
      </p>
      <ol aria-label="Recovery codes" className="grid grid-cols-2 gap-1.5 rounded-lg border bg-muted/40 p-3 font-mono text-[13px] tracking-wide">
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ol>
      <div className="flex gap-2">
        <Button type="button" size="sm" variant="outline" onClick={() => void copy()}>
          {copied ? <Check /> : <Copy />} Copy
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={download}>
          <Download /> Download
        </Button>
      </div>
    </div>
  )
}

function SetupDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const begin = useBeginMfaSetup()
  const enable = useEnableMfa()
  const [password, setPassword] = useState('')
  const [setup, setSetup] = useState<MfaSetup | null>(null)
  const [code, setCode] = useState('')
  const [codes, setCodes] = useState<string[] | null>(null)

  const close = (next: boolean) => {
    if (!next) {
      setPassword('')
      setSetup(null)
      setCode('')
      setCodes(null)
      begin.reset()
      enable.reset()
    }
    onOpenChange(next)
  }

  const onPassword = (event: FormEvent) => {
    event.preventDefault()
    begin.mutate(password, { onSuccess: (result) => setSetup(result) })
  }
  const onCode = (event: FormEvent) => {
    event.preventDefault()
    enable.mutate(code, { onSuccess: (result) => setCodes(result.codes) })
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{codes ? 'Save your recovery codes' : 'Set up two-step verification'}</DialogTitle>
          <DialogDescription>
            {codes
              ? 'Two-step verification is on. You will be asked for a code from your app each time you sign in.'
              : setup
                ? 'Scan the QR code with an authenticator app (Microsoft Authenticator, Google Authenticator, 1Password…), then enter the code it shows.'
                : 'First, confirm your password.'}
          </DialogDescription>
        </DialogHeader>
        {codes ? (
          <>
            <RecoveryCodes codes={codes} />
            <DialogFooter>
              <Button onClick={() => close(false)}>I've saved them</Button>
            </DialogFooter>
          </>
        ) : setup ? (
          <form onSubmit={onCode} className="space-y-4" noValidate>
            <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-start">
              <img src={setup.qr_svg} alt="QR code to add WorkPulse to your authenticator app" className="size-40 shrink-0 rounded-lg border bg-white p-1" />
              <div className="min-w-0 space-y-1 text-[12px] text-muted-foreground">
                <p>Can't scan it? Enter this key in your app instead:</p>
                <p className="font-mono text-[13px] break-all text-foreground select-all">{setup.secret.replace(/(.{4})/g, '$1 ').trim()}</p>
              </div>
            </div>
            <FormField
              label="6-digit code from the app"
              autoComplete="one-time-code"
              inputMode="numeric"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              error={enable.error ? errorMessage(enable.error) : undefined}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={enable.isPending} disabled={code.length !== 6}>
                Turn on
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <form onSubmit={onPassword} className="space-y-4" noValidate>
            <PasswordField
              label="Password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={fieldError(begin.error, 'password')}
            />
            {begin.error && !fieldError(begin.error, 'password') && <FormAlert>{errorMessage(begin.error)}</FormAlert>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={begin.isPending} disabled={!password}>
                Continue
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** Password + current code, for turning it off or replacing recovery codes. */
function ConfirmDialog({ mode, onOpenChange }: { mode: 'disable' | 'codes' | null; onOpenChange: (open: boolean) => void }) {
  const disable = useDisableMfa()
  const regenerate = useRegenerateRecoveryCodes()
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [codes, setCodes] = useState<string[] | null>(null)
  const mutation = mode === 'disable' ? disable : regenerate

  const close = (next: boolean) => {
    if (!next) {
      setPassword('')
      setCode('')
      setCodes(null)
      disable.reset()
      regenerate.reset()
    }
    onOpenChange(next)
  }
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (mode === 'disable') {
      disable.mutate(
        { password, code },
        {
          onSuccess: () => {
            toast.success('Two-step verification is off')
            close(false)
          },
        },
      )
    } else regenerate.mutate({ password, code }, { onSuccess: (result) => setCodes(result.codes) })
  }

  return (
    <Dialog open={mode !== null} onOpenChange={close}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{codes ? 'Your new recovery codes' : mode === 'disable' ? 'Turn off two-step verification?' : 'Replace recovery codes?'}</DialogTitle>
          <DialogDescription>
            {codes
              ? 'Your old codes no longer work.'
              : mode === 'disable'
                ? 'Your account will be protected by your password alone.'
                : 'Your current recovery codes will stop working.'}
          </DialogDescription>
        </DialogHeader>
        {codes ? (
          <>
            <RecoveryCodes codes={codes} />
            <DialogFooter>
              <Button onClick={() => close(false)}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <PasswordField
              label="Password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={fieldError(mutation.error, 'password')}
            />
            <FormField
              label="Code from your app or a recovery code"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              error={fieldError(mutation.error, 'code')}
            />
            {mutation.error && !fieldError(mutation.error, 'password') && !fieldError(mutation.error, 'code') && (
              <FormAlert>{errorMessage(mutation.error)}</FormAlert>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" variant={mode === 'disable' ? 'destructive' : 'default'} loading={mutation.isPending} disabled={!password || code.trim().length < 6}>
                {mode === 'disable' ? 'Turn off' : 'Replace codes'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function TwoStepCard() {
  const enabled = useAuthStore((s) => Boolean(s.user?.mfa_enabled))
  const [setupOpen, setSetupOpen] = useState(false)
  const [confirm, setConfirm] = useState<'disable' | 'codes' | null>(null)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Smartphone className="size-4 text-muted-foreground" aria-hidden /> Two-step verification
        </CardTitle>
        <CardAction>{enabled ? <Badge variant="success">On</Badge> : <Badge variant="secondary">Off</Badge>}</CardAction>
        <CardDescription>
          {enabled
            ? 'Signing in needs your password and a code from your authenticator app.'
            : 'Add a code from an authenticator app to your sign-in, so a stolen password alone is not enough.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="text-[12px] text-muted-foreground">
        {enabled
          ? 'The desktop agent can then only be set up with an enrolment code from your administrator.'
          : 'Works with any standard authenticator app. You get recovery codes in case you lose your phone.'}
      </CardContent>
      <CardFooter className="flex-wrap justify-end gap-2">
        {enabled ? (
          <>
            <Button size="sm" variant="outline" onClick={() => setConfirm('codes')}>
              <KeyRound /> New recovery codes
            </Button>
            <Button size="sm" variant="outline" onClick={() => setConfirm('disable')}>
              <ShieldOff /> Turn off
            </Button>
          </>
        ) : (
          <Button size="sm" onClick={() => setSetupOpen(true)}>
            <ShieldCheck /> Set up
          </Button>
        )}
      </CardFooter>
      <SetupDialog open={setupOpen} onOpenChange={setSetupOpen} />
      <ConfirmDialog mode={confirm} onOpenChange={(open) => !open && setConfirm(null)} />
    </Card>
  )
}
