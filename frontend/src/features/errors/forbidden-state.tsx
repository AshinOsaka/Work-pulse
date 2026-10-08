import { ShieldAlert } from 'lucide-react'
import { Link } from 'react-router'

import { EmptyState } from '@/components/common/empty-state'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import type { Permission } from '@/types/api'

export function ForbiddenState({ permission }: { permission?: Permission }) {
  return (
    <Card className="mx-auto mt-6 max-w-xl">
      <EmptyState
        icon={ShieldAlert}
        title="You don't have access to this area"
        description={
          <>
            Ask a workspace administrator for access.
            {permission && (
              <>
                {' '}
                Required permission: <code className="rounded bg-muted px-1 py-0.5 text-[12px]">{permission}</code>
              </>
            )}
          </>
        }
        action={
          <Button variant="outline" size="sm" asChild>
            <Link to="/dashboard">Back to dashboard</Link>
          </Button>
        }
      />
    </Card>
  )
}
