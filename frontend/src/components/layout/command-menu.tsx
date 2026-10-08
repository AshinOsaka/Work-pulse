import { Building2, KeyRound, LogOut, Monitor, Moon, Sun, UserPlus, Users, UsersRound } from 'lucide-react'
import { useNavigate } from 'react-router'

import { useVisibleModules } from '@/components/layout/sidebar'
import { useSignOut } from '@/components/layout/user-menu'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { NAV_SECTIONS } from '@/config/modules'
import { useModKey } from '@/hooks/use-hotkey'
import { usePermissions } from '@/stores/auth-store'
import { useUiStore } from '@/stores/ui-store'

export function CommandMenu() {
  const open = useUiStore((s) => s.commandOpen)
  const setOpen = useUiStore((s) => s.setCommandOpen)
  const setTheme = useUiStore((s) => s.setTheme)
  const modules = useVisibleModules()
  const navigate = useNavigate()
  const signOut = useSignOut()
  const { can } = usePermissions()

  useModKey('k', () => setOpen(!useUiStore.getState().commandOpen))

  const run = (action: () => void) => {
    setOpen(false)
    action()
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Search pages and actions…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        {NAV_SECTIONS.map((section) => {
          const items = modules.filter((m) => m.section === section)
          if (!items.length) return null
          return (
            <CommandGroup key={section} heading={section}>
              {items.map((module) => (
                <CommandItem
                  key={module.key}
                  value={module.label}
                  keywords={[module.section]}
                  onSelect={() => run(() => navigate(module.path))}
                >
                  <module.icon />
                  <span>{module.label}</span>
                  {module.status === 'upcoming' && (
                    <span className="ml-auto text-[11px] text-muted-foreground">Soon</span>
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
          )
        })}
        {can('EMPLOYEE_VIEW') && (
          <CommandGroup heading="People">
            <CommandItem value="Employees directory" keywords={['people', 'staff']} onSelect={() => run(() => navigate('/people/employees'))}>
              <Users /> Employees
            </CommandItem>
            <CommandItem value="Departments" keywords={['people']} onSelect={() => run(() => navigate('/people/departments'))}>
              <Building2 /> Departments
            </CommandItem>
            <CommandItem value="Teams" keywords={['people']} onSelect={() => run(() => navigate('/people/teams'))}>
              <UsersRound /> Teams
            </CommandItem>
            {can('EMPLOYEE_MANAGE') && (
              <CommandItem value="Add employee" keywords={['new', 'hire', 'invite']} onSelect={() => run(() => navigate('/people/employees'))}>
                <UserPlus /> Add employee
              </CommandItem>
            )}
          </CommandGroup>
        )}
        {can('USER_MANAGE') && (
          <CommandGroup heading="Administration">
            <CommandItem value="Roles and permissions" keywords={['users', 'members']} onSelect={() => run(() => navigate('/settings/roles'))}>
              <KeyRound /> Roles & permissions
            </CommandItem>
          </CommandGroup>
        )}
        <CommandSeparator />
        <CommandGroup heading="Preferences">
          <CommandItem value="theme light" onSelect={() => run(() => setTheme('light'))}>
            <Sun /> Switch to light theme
          </CommandItem>
          <CommandItem value="theme dark" onSelect={() => run(() => setTheme('dark'))}>
            <Moon /> Switch to dark theme
          </CommandItem>
          <CommandItem value="theme system" onSelect={() => run(() => setTheme('system'))}>
            <Monitor /> Use system theme
          </CommandItem>
        </CommandGroup>
        <CommandGroup heading="Account">
          <CommandItem value="sign out logout" onSelect={() => run(signOut)}>
            <LogOut /> Sign out
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
