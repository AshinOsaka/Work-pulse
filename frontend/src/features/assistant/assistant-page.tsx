import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ArrowUp, CalendarCheck, Check, CircleAlert, Database, FolderKanban, History, ListChecks, MessageSquarePlus, Radio, Sparkles, Square, Trash2, TriangleAlert, Users, type LucideIcon } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { PageHeader } from '@/components/common/page-header'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Textarea } from '@/components/ui/form-controls'
import { Skeleton, Spinner } from '@/components/ui/misc'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { useAssistantStatus, useClearConversations, useConversations, useDeleteConversation, type ToolUse } from '@/features/assistant/api'
import { AnswerCard } from '@/features/assistant/cards'
import { Markdown } from '@/features/assistant/markdown'
import { useAssistantChat, type ChatTurn } from '@/features/assistant/use-assistant-chat'
import { RequirePermission } from '@/features/auth/guards'
import { WidgetError } from '@/features/dashboard/components/widget'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { errorMessage } from '@/lib/api-client'
import { formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'

const SUGGESTION_ICONS: LucideIcon[] = [Sparkles, Radio, Users, FolderKanban, ListChecks, CalendarCheck]

function HistoryPanel({ activeId, onSelect, onNew }: { activeId: string | null; onSelect: (id: string) => void; onNew: () => void }) {
  const conversations = useConversations()
  const remove = useDeleteConversation()
  const clear = useClearConversations()
  const [confirm, setConfirm] = useState(false)
  const list = conversations.data ?? []
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 px-3 pt-3 pb-2">
        <h2 className="text-[13px] font-semibold">Conversations</h2>
        <Button size="sm" variant="soft" onClick={onNew}>
          <MessageSquarePlus /> New
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {conversations.isPending ? (
          <div className="space-y-2 p-1">
            {[0, 1, 2].map((n) => (
              <Skeleton key={n} className="h-10" />
            ))}
          </div>
        ) : conversations.isError ? (
          <WidgetError error={conversations.error} onRetry={() => void conversations.refetch()} />
        ) : list.length === 0 ? (
          <p className="px-2 py-6 text-center text-[12px] text-muted-foreground">Your questions will be listed here for 90 days.</p>
        ) : (
          <ul aria-label="Your conversations" className="space-y-0.5">
            {list.map((c) => (
              <li key={c.id} className="group relative">
                <button
                  type="button"
                  onClick={() => onSelect(c.id)}
                  aria-current={c.id === activeId ? 'page' : undefined}
                  className={cn(
                    'w-full rounded-md py-2 pr-9 pl-2.5 text-left transition hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none',
                    c.id === activeId && 'bg-accent',
                  )}
                >
                  <span className="block truncate text-[13px] font-medium">{c.title}</span>
                  <span className="block text-[11px] text-muted-foreground">
                    {formatRelative(c.updated_at)} · {c.questions} {c.questions === 1 ? 'question' : 'questions'}
                  </span>
                </button>
                <button
                  type="button"
                  aria-label={`Delete "${c.title}"`}
                  disabled={remove.isPending}
                  onClick={() =>
                    remove.mutate(c.id, {
                      onSuccess: () => c.id === activeId && onNew(),
                      onError: (error) => toast.error(errorMessage(error)),
                    })
                  }
                  className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-1.5 text-muted-foreground opacity-0 transition group-hover:opacity-100 hover:bg-background hover:text-destructive focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none max-lg:opacity-100"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {list.length > 0 && (
        <div className="border-t p-2">
          <Button size="sm" variant="ghost" className="w-full justify-start text-muted-foreground" onClick={() => setConfirm(true)}>
            <Trash2 /> Clear history
          </Button>
        </div>
      )}
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Clear all conversations?"
        description="Every conversation you've had with the assistant will be deleted. This can't be undone."
        confirmLabel="Clear history"
        destructive
        loading={clear.isPending}
        onConfirm={() =>
          clear.mutate(undefined, {
            onSuccess: () => {
              setConfirm(false)
              onNew()
              toast.success('Conversation history cleared')
            },
            onError: (error) => toast.error(errorMessage(error)),
          })
        }
      />
    </div>
  )
}

function ToolChip({ use }: { use: ToolUse }) {
  return (
    <li
      className={cn(
        'inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px]',
        use.status === 'error' ? 'border-warning/40 bg-warning-soft text-foreground' : 'bg-muted/50 text-muted-foreground',
      )}
      title={use.status === 'error' ? (use.message ?? undefined) : undefined}
    >
      {use.status === 'running' ? (
        <Spinner className="size-3" />
      ) : use.status === 'done' ? (
        <Check className="size-3 text-success" aria-hidden />
      ) : (
        <CircleAlert className="size-3 text-warning" aria-hidden />
      )}
      <span className="truncate">
        {use.label}
        {use.status === 'error' && use.message ? ` — ${use.message}` : ''}
      </span>
      <span className="sr-only">{use.status === 'running' ? '(in progress)' : use.status === 'done' ? '(done)' : '(failed)'}</span>
    </li>
  )
}

function Message({ turn }: { turn: ChatTurn }) {
  if (turn.role === 'user') {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-md bg-primary-solid px-3.5 py-2 text-sm whitespace-pre-wrap text-primary-foreground">{turn.text}</p>
      </div>
    )
  }
  const streaming = 'streaming' in turn && turn.streaming
  const waiting = streaming && !turn.text && turn.tools.length === 0
  return (
    <article className="flex gap-3" aria-busy={streaming || undefined}>
      <div className="mt-0.5 hidden size-7 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary sm:flex" aria-hidden>
        <Sparkles className="size-3.5" />
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        <h3 className="sr-only">Assistant</h3>
        {turn.tools.length > 0 && (
          <ul aria-label="Data checked" className="flex flex-wrap gap-1.5">
            {turn.tools.map((use, n) => (
              <ToolChip key={use.id ?? n} use={use} />
            ))}
          </ul>
        )}
        {waiting && (
          <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <Spinner className="size-3.5" /> Thinking…
          </p>
        )}
        {turn.text && <Markdown text={turn.text} />}
        {turn.cards.length > 0 && (
          <div className="space-y-3">
            {turn.cards.map((card, n) => (
              <AnswerCard key={n} card={card} />
            ))}
          </div>
        )}
        {turn.error && (
          <p role="alert" className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive-soft px-3 py-2 text-[13px]">
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-destructive" aria-hidden />
            {turn.error}
          </p>
        )}
      </div>
    </article>
  )
}

function Welcome({ suggestions, onPick }: { suggestions: string[]; onPick: (q: string) => void }) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-2 py-8 text-center sm:py-12">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
        <Sparkles className="size-6" />
      </div>
      <h2 className="mt-4 text-lg font-semibold tracking-tight">Ask about your team's work</h2>
      <p className="mt-1 max-w-md text-[13px] text-muted-foreground">
        Answers come only from WorkPulse records you're allowed to see — each one says which period and data it used, with links to the full view.
      </p>
      <ul aria-label="Suggested questions" className="mt-6 grid w-full gap-2 sm:grid-cols-2">
        {suggestions.map((q, n) => {
          const Icon = SUGGESTION_ICONS[n % SUGGESTION_ICONS.length]
          return (
            <li key={q}>
              <button
                type="button"
                onClick={() => onPick(q)}
                className="flex h-full w-full items-start gap-2.5 rounded-lg border bg-card px-3 py-2.5 text-left text-[13px] shadow-xs transition hover:border-primary/40 hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none"
              >
                <Icon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                <span>{q}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function Composer({ streaming, onSend, onStop }: { streaming: boolean; onSend: (q: string) => void; onStop: () => void }) {
  const [value, setValue] = useState('')
  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    if (streaming || !value.trim()) return
    onSend(value)
    setValue('')
  }
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) submit(event)
  }
  return (
    <form onSubmit={submit} className="border-t bg-card/60 p-3">
      <div className="relative">
        <label htmlFor="assistant-question" className="sr-only">
          Ask a question about your team's work
        </label>
        <Textarea
          id="assistant-question"
          rows={1}
          maxLength={2000}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about attendance, activity, projects or tasks…"
          className="field-sizing-content max-h-40 min-h-11 resize-none py-2.5 pr-12"
        />
        {streaming ? (
          <Button type="button" size="icon-sm" variant="outline" onClick={onStop} className="absolute right-1.5 bottom-1.5" aria-label="Stop answering">
            <Square className="size-3.5 fill-current" />
          </Button>
        ) : (
          <Button type="submit" size="icon-sm" className="absolute right-1.5 bottom-1.5" disabled={!value.trim()} aria-label="Send question">
            <ArrowUp />
          </Button>
        )}
      </div>
      <p className="mt-1.5 text-[11px] text-muted-foreground">
        Summaries of recorded work signals, not judgements about people. Check important figures on the linked pages.
      </p>
    </form>
  )
}

function Chat() {
  const status = useAssistantStatus()
  const chat = useAssistantChat()
  const [params, setParams] = useSearchParams()
  const [historyOpen, setHistoryOpen] = useState(false)
  const scroller = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)
  const requested = params.get('c')
  const { conversationId, open, reset } = chat

  // The URL (?c=) names the open conversation, so history entries are linkable and survive a reload. Each effect
  // reacts only to its own side changing; otherwise a stale value from one side would immediately undo the other.
  const inUrl = useRef<string | null | undefined>(undefined)
  const shown = useRef<string | null>(null)
  useEffect(() => {
    if (requested === inUrl.current) return
    inUrl.current = requested
    if (!requested) reset()
    else if (requested !== shown.current) void open(requested)
  }, [requested, open, reset])
  useEffect(() => {
    if (conversationId === shown.current) return
    shown.current = conversationId
    if (conversationId && conversationId !== inUrl.current) {
      inUrl.current = conversationId
      setParams({ c: conversationId }, { replace: true })
    }
  }, [conversationId, setParams])

  // Follow the answer as it streams in, unless the person has scrolled up to read.
  const { turns } = chat
  useEffect(() => {
    const el = scroller.current
    if (el && pinned.current && turns.length) el.scrollTop = el.scrollHeight
  }, [turns])

  const startNew = () => {
    if (requested) setParams({})
    else reset()
    setHistoryOpen(false)
  }
  const select = (id: string) => {
    setParams({ c: id })
    setHistoryOpen(false)
  }
  const send = (q: string) => {
    pinned.current = true
    void chat.send(q)
  }

  if (status.isPending) return <Skeleton className="h-[calc(100svh-10rem)] min-h-[28rem] rounded-xl" />
  const header = <PageHeader title="AI Assistant" description="Ask questions about your workforce data and get answers with their sources." icon={Sparkles} />
  if (status.isError) {
    return (
      <div className="space-y-6">
        {header}
        <Card>
          <WidgetError error={status.error} onRetry={() => void status.refetch()} />
        </Card>
      </div>
    )
  }
  if (!status.data.configured) {
    return (
      <div className="space-y-6">
        {header}
        <Card>
          <EmptyState
          icon={Sparkles}
          title="The assistant isn't switched on yet"
          description={
            <>
              An administrator needs to give the WorkPulse server an Anthropic API key (the <code className="rounded bg-muted px-1 font-mono text-[12px]">ANTHROPIC_API_KEY</code>{' '}
              setting) and restart it. Until then, the same data is available in Live Tracking, Productivity, Projects and Reports.
            </>
          }
          />
        </Card>
      </div>
    )
  }

  const history = <HistoryPanel activeId={conversationId} onSelect={select} onNew={startNew} />
  return (
    <div className="grid h-[calc(100svh-7.5rem)] min-h-[30rem] grid-cols-[minmax(0,1fr)] overflow-hidden rounded-xl border bg-card shadow-xs lg:h-[calc(100svh-9.5rem)] lg:grid-cols-[16rem_minmax(0,1fr)]">
      <aside aria-label="Conversation history" className="hidden min-h-0 border-r bg-muted/20 lg:block">
        {history}
      </aside>
      <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
        <SheetContent side="left" className="w-[19rem] bg-card p-0 pt-8">
          <SheetTitle className="sr-only">Conversation history</SheetTitle>
          <SheetDescription className="sr-only">Open or delete earlier conversations with the assistant</SheetDescription>
          {history}
        </SheetContent>
      </Sheet>

      <section aria-label="Assistant" className="flex min-h-0 min-w-0 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
          <Button size="icon-sm" variant="ghost" className="lg:hidden" aria-label="Conversation history" onClick={() => setHistoryOpen(true)}>
            <History />
          </Button>
          <h2 className="min-w-0 flex-1 truncate text-[13px] font-semibold">{chat.title ?? 'New conversation'}</h2>
          <span className="hidden items-center gap-1 text-[11px] text-muted-foreground sm:inline-flex">
            <Database className="size-3" aria-hidden /> Grounded in WorkPulse data
          </span>
          {chat.turns.length > 0 && (
            <Button size="sm" variant="ghost" onClick={startNew}>
              <MessageSquarePlus /> <span className="max-sm:sr-only">New conversation</span>
            </Button>
          )}
        </header>

        <div
          ref={scroller}
          onScroll={(e) => {
            const el = e.currentTarget
            pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
          }}
          className="min-h-0 flex-1 overflow-y-auto"
        >
          {chat.loading ? (
            <div className="space-y-4 p-4 sm:p-6">
              <Skeleton className="ml-auto h-9 w-1/2" />
              <Skeleton className="h-24 w-4/5" />
            </div>
          ) : chat.loadError ? (
            <EmptyState
              icon={TriangleAlert}
              title="Couldn't open this conversation"
              description={chat.loadError}
              action={
                <Button size="sm" variant="outline" onClick={startNew}>
                  Start a new one
                </Button>
              }
            />
          ) : chat.turns.length === 0 ? (
            <Welcome suggestions={status.data.suggestions} onPick={send} />
          ) : (
            <div role="log" aria-label="Conversation" className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6">
              {chat.turns.map((turn) => (
                <Message key={turn.id} turn={turn} />
              ))}
            </div>
          )}
        </div>
        <p className="sr-only" aria-live="polite">
          {chat.streaming ? 'The assistant is answering' : chat.turns.length ? 'Answer ready' : ''}
        </p>
        <Composer streaming={chat.streaming} onSend={send} onStop={chat.stop} />
      </section>
    </div>
  )
}

export default function AssistantPage() {
  useDocumentTitle('AI Assistant')
  return (
    <RequirePermission permission="REPORT_VIEW">
      <Chat />
    </RequirePermission>
  )
}
