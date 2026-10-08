import { LogOut, Settings, ShieldCheck } from 'lucide-react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useLogout } from '@/features/auth/api'
import { ROLE_LABELS } from '@/lib/format'
import { initials } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'

export function useSignOut() {
  const logout = useLogout()
  const navigate = useNavigate()
  return () =>
    logout.mutate(undefined, {
      onSettled: () => {
        navigate('/login', { replace: true })
        toast.success('You have been signed out')
      },
    })
}

export function UserMenu() {
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  const signOut = useSignOut()
  if (!user) return null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="flex items-center gap-2 rounded-full p-0.5 transition hover:ring-4 hover:ring-accent focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
      >
        <span className="sr-only">Open profile menu</span>
        <Avatar className="size-8" aria-hidden>
          <AvatarFallback>{initials(user.full_name)}</AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="flex items-center gap-3 py-2">
          <Avatar className="size-9">
            <AvatarFallback>{initials(user.full_name)}</AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold">{user.full_name}</p>
            <p className="truncate text-[12px] font-normal text-muted-foreground">{user.email}</p>
          </div>
        </DropdownMenuLabel>
        <div className="px-2 pb-2">
          <Badge variant="soft">{ROLE_LABELS[user.role]}</Badge>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem onSelect={() => navigate('/settings')}>
            <Settings /> Settings
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => navigate('/security')}>
            <ShieldCheck /> Security
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onSelect={signOut}>
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
