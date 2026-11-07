import { useState } from 'react'
import { Play, Search, Video } from 'lucide-react'

import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/common/page-header'
import { Input } from '@/components/ui/input'
import { CARD_GRADIENTS, TUTORIALS, type Tutorial } from '@/features/tutorials/data'
import { TutorialPlayer } from '@/features/tutorials/tutorial-player'
import { cn } from '@/lib/utils'

export default function TutorialsPage() {
  const [query, setQuery] = useState('')
  const [playing, setPlaying] = useState<Tutorial | null>(null)
  const q = query.trim().toLowerCase()
  const list = TUTORIALS.map((tutorial, i) => ({ tutorial, number: i + 1 })).filter(
    ({ tutorial }) => !q || tutorial.title.toLowerCase().includes(q) || tutorial.description.toLowerCase().includes(q),
  )

  return (
    <div className="space-y-6">
      <PageHeader title="Tutorials" />

      <div className="rounded-xl border bg-card p-5">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <p className="flex items-center gap-2.5 text-[13px] text-muted-foreground">
            <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Video className="size-4" aria-hidden />
            </span>
            <span>
              <strong className="text-[15px] text-foreground">{TUTORIALS.length}</strong> video {TUTORIALS.length === 1 ? 'tutorial' : 'tutorials'}
            </span>
          </p>
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search videos" className="pl-9" aria-label="Search videos" />
          </div>
        </div>

        {list.length === 0 ? (
          <EmptyState size="sm" icon={Search} title="No tutorials match" description="Try another word." />
        ) : (
          <ul className="wp-stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {list.map(({ tutorial, number }) => (
              <li key={tutorial.slug}>
                <button
                  type="button"
                  onClick={() => setPlaying(tutorial)}
                  aria-label={`Watch tutorial ${number}: ${tutorial.title}`}
                  className="group w-full overflow-hidden rounded-xl border bg-card text-left transition duration-200 hover:-translate-y-0.5 hover:shadow-lg focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
                >
                  <span className={cn('relative flex h-32 items-center justify-center bg-gradient-to-br', CARD_GRADIENTS[(number - 1) % CARD_GRADIENTS.length])}>
                    <span className="absolute top-3 left-3 rounded-full bg-black/25 px-2 py-0.5 text-[11px] font-semibold text-white tabular">
                      {String(number).padStart(2, '0')}
                    </span>
                    <span className="flex size-12 items-center justify-center rounded-full bg-white/90 shadow-lg transition duration-200 group-hover:scale-110">
                      <Play className="ml-0.5 size-4 fill-slate-500 text-slate-500" aria-hidden />
                    </span>
                  </span>
                  <span className="block px-4 py-3">
                    <span className="block text-[14px] font-semibold">{tutorial.title}</span>
                    <span className="mt-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">
                      <Video className="size-3.5" aria-hidden /> Watch tutorial
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {playing && <TutorialPlayer key={playing.slug} tutorial={playing} open onOpenChange={(o) => !o && setPlaying(null)} />}
    </div>
  )
}
