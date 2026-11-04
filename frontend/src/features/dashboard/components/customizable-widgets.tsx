import { useMemo, useState, type ReactNode } from 'react'
import {
  closestCorners,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import { arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  Activity,
  BarChart3,
  Briefcase,
  CalendarCheck,
  Clock,
  Globe,
  GripVertical,
  LayoutGrid,
  LineChart,
  Plus,
  RotateCcw,
  Save,
  Settings2,
  Users,
  Wifi,
  X,
  type LucideIcon,
} from 'lucide-react'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { useHiddenSections } from '@/config/sections'
import { WidgetFrameContext } from '@/features/dashboard/components/widget'
import { api, errorMessage } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import type { DashboardArea, DashboardWidgetPref, User } from '@/types/api'

/** A widget the dashboard can show. `section`: hidden for people an admin has hidden that section from. */
export interface WidgetDef {
  id: string
  title: string
  description: string
  icon: LucideIcon
  defaultArea: DashboardArea
  section?: string
  /** Not on the standard dashboard; people add it from Add widget. */
  optional?: boolean
  /** Takes the whole top row instead of half of it. */
  wide?: boolean
  content: ReactNode
}

/** The catalogue in its standard order and areas, without the content (that needs the page's data). */
export const WIDGET_INFO: Omit<WidgetDef, 'content'>[] = [
  { id: 'connected_now', title: 'Connected now', description: 'Live device and signal counts.', icon: Wifi, defaultArea: 'top' },
  { id: 'work_hours', title: 'Work hours', description: 'Active, productive and neutral hours.', icon: Clock, defaultArea: 'top', section: 'productivity' },
  { id: 'trend', title: 'Productivity trend', description: 'Productive and unproductive time by date.', icon: LineChart, defaultArea: 'main', section: 'productivity' },
  { id: 'websites_apps', title: 'Websites & applications', description: 'Most used websites and applications.', icon: Globe, defaultArea: 'main', section: 'activity' },
  { id: 'attendance', title: 'Attendance', description: 'Present and away per working day.', icon: CalendarCheck, defaultArea: 'main', section: 'attendance' },
  { id: 'member_productivity', title: 'Member productivity', description: 'Top and less productive members.', icon: Users, defaultArea: 'side', section: 'productivity' },
  { id: 'recent_activity', title: 'Recent activity', description: 'Organisation changes in your scope.', icon: Activity, defaultArea: 'side' },
  { id: 'my_work', title: 'My work', description: 'Your current task, timer and tasks for today.', icon: Briefcase, defaultArea: 'top', optional: true, wide: true },
  { id: 'daily_work_hours', title: 'Daily work hours', description: 'Compare active, productive and neutral hours day by day.', icon: BarChart3, defaultArea: 'main', optional: true, section: 'productivity' },
]

/** The standard dashboard: the same arrangement as before customizing existed. */
export const DEFAULT_LAYOUT: DashboardWidgetPref[] = WIDGET_INFO.filter((w) => !w.optional).map((w) => ({ id: w.id, area: w.defaultArea, title: null }))

const AREAS: { value: DashboardArea; label: string }[] = [
  { value: 'top', label: 'Top row' },
  { value: 'main', label: 'Main column' },
  { value: 'side', label: 'Side column' },
]

const same = (a: DashboardWidgetPref[], b: DashboardWidgetPref[]) =>
  a.length === b.length && a.every((w, i) => w.id === b[i]!.id && w.area === b[i]!.area && (w.title || null) === (b[i]!.title || null))

/** Customize state for the dashboard: the saved layout, a draft while customizing, and save / reset / exit. */
export function useDashboardCustomizer() {
  const saved = useAuthStore((s) => s.user?.dashboard_layout)
  const updateSession = useAuthStore((s) => s.updateSession)
  const savedLayout = useMemo(() => saved ?? DEFAULT_LAYOUT, [saved])
  const [draft, setDraft] = useState<DashboardWidgetPref[] | null>(null)
  const [saving, setSaving] = useState(false)

  const customizing = draft !== null
  const layout = draft ?? savedLayout
  const dirty = customizing && !same(draft, savedLayout)

  const save = async () => {
    if (!draft) return
    setSaving(true)
    try {
      // The standard layout is stored as "no layout", so later improvements to it reach this person too.
      const user = same(draft, DEFAULT_LAYOUT)
        ? await api.delete<User>('/users/me/dashboard-layout')
        : await api.put<User>('/users/me/dashboard-layout', { widgets: draft.map((w) => ({ ...w, title: w.title || null })) })
      updateSession({ user })
      setDraft(null)
      toast.success('Dashboard saved')
    } catch (error) {
      toast.error("Couldn't save the dashboard", { description: errorMessage(error) })
    } finally {
      setSaving(false)
    }
  }

  return {
    customizing,
    layout,
    dirty,
    saving,
    start: () => setDraft(savedLayout.map((w) => ({ ...w }))),
    exit: () => setDraft(null),
    reset: () => setDraft(DEFAULT_LAYOUT.map((w) => ({ ...w }))),
    setDraft: (next: DashboardWidgetPref[]) => setDraft(next),
    save,
  }
}

export type DashboardCustomizer = ReturnType<typeof useDashboardCustomizer>

/** Moves a widget to `area`, before `beforeId` (or at the end of that area). The list order is the order. */
function moveTo(layout: DashboardWidgetPref[], id: string, area: DashboardArea, beforeId?: string): DashboardWidgetPref[] {
  const moving = layout.find((p) => p.id === id)
  if (!moving) return layout
  const rest = layout.filter((p) => p.id !== id)
  const placed = { ...moving, area }
  let index = beforeId ? rest.findIndex((p) => p.id === beforeId) : -1
  if (index < 0) {
    // After the last widget of that area (or at the end).
    const lastInArea = rest.map((p) => p.area).lastIndexOf(area)
    index = lastInArea >= 0 ? lastInArea + 1 : rest.length
  }
  return [...rest.slice(0, index), placed, ...rest.slice(index)]
}

function SortableWidget({
  pref,
  def,
  customizing,
  highlighted,
  onConfigure,
  onRemove,
}: {
  pref: DashboardWidgetPref
  def: WidgetDef
  customizing: boolean
  highlighted: boolean
  onConfigure: () => void
  onRemove: () => void
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: pref.id,
    data: { area: pref.area },
    disabled: !customizing,
  })
  const name = pref.title || def.title
  const controls = customizing ? (
    <span className="flex items-center gap-1">
      <Button
        ref={setActivatorNodeRef}
        variant="outline"
        size="icon-sm"
        className="cursor-grab touch-none active:cursor-grabbing"
        aria-label={`Move ${name}`}
        {...attributes}
        {...listeners}
      >
        <GripVertical />
      </Button>
      <Button variant="outline" size="icon-sm" onClick={onConfigure} aria-label={`Configure ${name}`}>
        <Settings2 />
      </Button>
      <Button variant="outline" size="icon-sm" onClick={onRemove} aria-label={`Remove ${name}`}>
        <X />
      </Button>
    </span>
  ) : null
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), transition }}
      className={cn('min-w-0', pref.area === 'top' && def.wide && 'xl:col-span-2', isDragging && 'relative z-20 opacity-80')}
    >
      <WidgetFrameContext.Provider value={{ title: pref.title, controls, highlighted: highlighted || isDragging }}>
        {def.content}
      </WidgetFrameContext.Provider>
    </div>
  )
}

/** One area of the dashboard. While customizing, an empty area still shows a place to drop widgets. */
function Area({
  area,
  items,
  customizing,
  className,
  children,
}: {
  area: DashboardArea
  items: string[]
  customizing: boolean
  className?: string
  children: ReactNode
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `area:${area}`, data: { area }, disabled: !customizing })
  const label = AREAS.find((a) => a.value === area)!.label
  return (
    <SortableContext items={items} strategy={verticalListSortingStrategy}>
      <div ref={setNodeRef} className={cn(className, customizing && items.length === 0 && 'min-h-24')}>
        {children}
        {customizing && items.length === 0 && (
          <div
            className={cn(
              'flex h-24 items-center justify-center rounded-xl border-2 border-dashed text-[12.5px] text-muted-foreground',
              isOver && 'border-primary/50 bg-primary/5 text-primary',
              area === 'top' && 'xl:col-span-2',
            )}
          >
            Drop a widget here ({label.toLowerCase()})
          </div>
        )}
      </div>
    </SortableContext>
  )
}

function CustomizeBar({ c, onAdd }: { c: DashboardCustomizer; onAdd: () => void }) {
  const [confirmExit, setConfirmExit] = useState(false)
  return (
    <Card className="flex flex-col gap-3 border-primary/30 bg-primary/[0.04] p-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-[14px] font-semibold">Customize dashboard</p>
        <p className="text-[12.5px] text-muted-foreground">Drag, rename, add or remove widgets.</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-[12px] text-muted-foreground" aria-live="polite">
          {c.dirty ? 'Unsaved changes' : 'No changes'}
        </span>
        <Button size="sm" variant="outline" onClick={onAdd}>
          <Plus /> Add widget
        </Button>
        <Button size="sm" variant="outline" onClick={c.reset}>
          <RotateCcw /> Reset
        </Button>
        <Button size="sm" variant="outline" onClick={() => (c.dirty ? setConfirmExit(true) : c.exit())}>
          Exit
        </Button>
        <Button size="sm" onClick={() => void c.save()} loading={c.saving} disabled={!c.dirty}>
          <Save /> Save dashboard
        </Button>
      </div>
      <ConfirmDialog
        open={confirmExit}
        onOpenChange={setConfirmExit}
        title="Discard your changes?"
        description="Your dashboard goes back to how it was last saved."
        confirmLabel="Discard changes"
        destructive
        onConfirm={() => {
          setConfirmExit(false)
          c.exit()
        }}
      />
    </Card>
  )
}

function ConfigureDialog({
  pref,
  def,
  onTitle,
  onArea,
  onClose,
}: {
  pref: DashboardWidgetPref | null
  def: WidgetDef | undefined
  onTitle: (title: string) => void
  onArea: (area: DashboardArea) => void
  onClose: () => void
}) {
  return (
    <Dialog open={pref !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings2 className="size-4 text-muted-foreground" aria-hidden /> Configure widget
          </DialogTitle>
          <DialogDescription>Changes show on the dashboard straight away and are kept when you save it.</DialogDescription>
        </DialogHeader>
        {pref && def && (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="widget-title">Widget title</Label>
              <Input id="widget-title" value={pref.title ?? ''} maxLength={60} placeholder={def.title} onChange={(e) => onTitle(e.target.value)} />
              <p className="text-[12px] text-muted-foreground">Leave it empty to use “{def.title}”.</p>
            </div>
            <div className="space-y-1.5">
              <Label>Position</Label>
              <SegmentedControl<DashboardArea> label="Position" value={pref.area} onChange={onArea} options={AREAS} />
              <p className="text-[12px] text-muted-foreground">Moves the widget to the end of that row or column. You can also drag it.</p>
            </div>
          </div>
        )}
        <DialogFooter>
          <Button onClick={onClose}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AddWidgetDialog({
  open,
  onOpenChange,
  available,
  present,
  onAdd,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  available: Omit<WidgetDef, 'content'>[]
  present: ReadonlySet<string>
  onAdd: (id: string) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <LayoutGrid className="size-4 text-muted-foreground" aria-hidden /> Add widget
          </DialogTitle>
          <DialogDescription>Choose a widget. It goes back to its usual place, and you can move it afterwards.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2.5 sm:grid-cols-2">
          {available.map((w) => {
            const added = present.has(w.id)
            return (
              <button
                key={w.id}
                type="button"
                disabled={added}
                onClick={() => onAdd(w.id)}
                aria-label={added ? `${w.title}: already on this dashboard` : `Add ${w.title}`}
                className="flex items-start gap-3 rounded-xl border bg-card p-3.5 text-left transition-colors enabled:hover:border-primary/40 enabled:hover:bg-muted/40 focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none disabled:opacity-55"
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary" aria-hidden>
                  <w.icon className="size-4" />
                </span>
                <span className="min-w-0">
                  <span className="block text-[13px] font-semibold">{w.title}</span>
                  <span className="block text-[12px] text-muted-foreground">{added ? 'Already on this dashboard' : w.description}</span>
                </span>
              </button>
            )
          })}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * The dashboard's widgets in the person's own arrangement, always in the dashboard's fixed formation: a top
 * row of two, then a wide main column beside a narrow side column. Customize mode adds drag, configure and
 * remove controls to each widget.
 */
export function CustomizableWidgets({ c, widgets }: { c: DashboardCustomizer; widgets: WidgetDef[] }) {
  const { isHidden } = useHiddenSections()
  const [configuring, setConfiguring] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const defs = useMemo(() => new Map(widgets.filter((w) => !isHidden(w.section)).map((w) => [w.id, w])), [widgets, isHidden])
  // Widgets the UI no longer knows, or that are hidden for this person, are skipped (kept in the saved layout).
  const shown = c.layout.filter((p) => defs.has(p.id))
  const inArea = (area: DashboardArea) => shown.filter((p) => p.area === area)
  const top = inArea('top')
  const main = inArea('main')
  const side = inArea('side')
  const present = new Set(c.layout.map((p) => p.id))
  const configured = shown.find((p) => p.id === configuring) ?? null

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return
    const overArea = (over.data.current?.area as DashboardArea | undefined) ?? null
    if (!overArea) return
    const overIsWidget = !String(over.id).startsWith('area:')
    const id = String(active.id)
    const from = c.layout.findIndex((p) => p.id === id)
    const to = overIsWidget ? c.layout.findIndex((p) => p.id === over.id) : -1
    if (overIsWidget && from >= 0 && to >= 0 && c.layout[from]!.area === overArea) {
      c.setDraft(arrayMove(c.layout, from, to)) // reorder within the same row or column
    } else {
      // Into another row or column: just before the widget dropped on, or at the end of that area.
      c.setDraft(moveTo(c.layout, id, overArea, overIsWidget ? String(over.id) : undefined))
    }
  }

  const widget = (pref: DashboardWidgetPref) => (
    <SortableWidget
      key={pref.id}
      pref={pref}
      def={defs.get(pref.id)!}
      customizing={c.customizing}
      highlighted={configuring === pref.id}
      onConfigure={() => setConfiguring(pref.id)}
      onRemove={() => c.setDraft(c.layout.filter((p) => p.id !== pref.id))}
    />
  )
  const ids = (list: DashboardWidgetPref[]) => list.map((p) => p.id)
  // The columns keep the 2/3 + 1/3 split; a column only takes the full width when the other one is empty.
  const hasMain = main.length > 0 || c.customizing
  const hasSide = side.length > 0 || c.customizing

  return (
    <>
      {c.customizing && <CustomizeBar c={c} onAdd={() => setAdding(true)} />}
      {shown.length === 0 && !c.customizing ? (
        <Card className="flex flex-col items-center gap-2 p-10 text-center">
          <LayoutGrid className="size-7 text-muted-foreground" aria-hidden />
          <p className="font-semibold">No widgets on your dashboard</p>
          <p className="max-w-sm text-[13px] text-muted-foreground">Customize it to add widgets back, or reset to the standard dashboard.</p>
          <Button size="sm" variant="outline" className="mt-1" onClick={c.start}>
            Customize
          </Button>
        </Card>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCorners} onDragEnd={onDragEnd}>
          {(top.length > 0 || c.customizing) && (
            <Area area="top" items={ids(top)} customizing={c.customizing} className="wp-stagger grid gap-5 xl:grid-cols-2">
              {top.map(widget)}
            </Area>
          )}
          {(hasMain || hasSide) && (
            <div className="grid gap-5 xl:grid-cols-3">
              {hasMain && (
                <Area area="main" items={ids(main)} customizing={c.customizing} className={cn('wp-stagger space-y-5', hasSide ? 'xl:col-span-2' : 'xl:col-span-3')}>
                  {main.map(widget)}
                </Area>
              )}
              {hasSide && (
                <Area area="side" items={ids(side)} customizing={c.customizing} className={cn('wp-stagger space-y-5', !hasMain && 'xl:col-span-3')}>
                  {side.map(widget)}
                </Area>
              )}
            </div>
          )}
        </DndContext>
      )}
      <ConfigureDialog
        pref={configured}
        def={configured ? defs.get(configured.id) : undefined}
        onTitle={(title) => configured && c.setDraft(c.layout.map((p) => (p.id === configured.id ? { ...p, title } : p)))}
        onArea={(area) => configured && area !== configured.area && c.setDraft(moveTo(c.layout, configured.id, area))}
        onClose={() => setConfiguring(null)}
      />
      <AddWidgetDialog
        open={adding}
        onOpenChange={setAdding}
        available={WIDGET_INFO.filter((w) => !isHidden(w.section))}
        present={present}
        onAdd={(id) => {
          const info = WIDGET_INFO.find((w) => w.id === id)
          if (!info) return
          c.setDraft(moveTo([...c.layout, { id, area: info.defaultArea, title: null }], id, info.defaultArea))
          toast.success(`${info.title} added`, { description: 'It’s back in its usual place.' })
        }}
      />
    </>
  )
}
