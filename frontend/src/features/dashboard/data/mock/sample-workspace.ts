/**
 * SAMPLE DATA — an in-memory simulation of a workspace with the desktop agent
 * installed. It produces believable presence, activity and alerts, and emits
 * events on a timer the same way the WebSocket gateway will in production.
 */
import { createRandom, hashUnit, type Random } from '@/features/dashboard/data/mock/prng'
import {
  SAMPLE_ALERT_TYPES,
  SAMPLE_APPS,
  SAMPLE_DEVICES,
  SAMPLE_PEOPLE,
  SAMPLE_TASKS,
  SAMPLE_TEAMS,
} from '@/features/dashboard/data/mock/sample-org'
import type {
  ActivityEvent,
  DashboardAlert,
  DashboardEvent,
  DashboardFilters,
  Kpi,
  KpiSnapshot,
  LiveEmployee,
  Period,
  PresencePoint,
  PresenceStatus,
  TeamActivity,
  TrendPoint,
} from '@/features/dashboard/data/types'

const MINUTE = 60_000
const DAY = 86_400_000

interface PersonState extends LiveEmployee {
  teamId: string
}

const teamName = (teamId: string) => SAMPLE_TEAMS.find((t) => t.id === teamId)?.name ?? 'Team'

export class SampleWorkspace {
  private readonly random: Random
  private readonly people: PersonState[]
  private alerts: DashboardAlert[] = []
  private events: ActivityEvent[] = []
  private timeline: PresencePoint[] = []
  private sequence = 0

  constructor(now = Date.now()) {
    this.random = createRandom(20261001)
    this.people = SAMPLE_PEOPLE.map((p, index) => {
      const status = this.randomStatus()
      return {
        person: { id: `sample-${index}`, name: p.name },
        title: p.title,
        teamId: p.teamId,
        teamName: teamName(p.teamId),
        status,
        application: status === 'offline' ? null : this.random.pick(SAMPLE_APPS[p.teamId] ?? []),
        task: status === 'offline' || this.random.chance(0.25) ? null : this.random.pick(SAMPLE_TASKS[p.teamId] ?? []),
        since: new Date(now - this.random.int(2, status === 'active' ? 170 : 40) * MINUTE).toISOString(),
        device: this.random.pick(SAMPLE_DEVICES),
      }
    })
    this.seedTimeline(now)
    this.seedHistory(now)
  }

  // ------------------------------------------------------------------ queries

  teams() {
    return SAMPLE_TEAMS.map(({ id, name }) => ({ id, name }))
  }

  kpis(filters: DashboardFilters, now = Date.now()): KpiSnapshot {
    const people = this.filtered(filters.teamId)
    const count = (status: PresenceStatus) => people.filter((p) => p.status === status).length
    const active = count('active')
    const idle = count('idle')
    const scale = people.length / this.people.length
    const recent = this.timeline.slice(-12).map((p) => Math.round((p.active + p.idle) * scale))

    const trend = this.trend(filters, now)
    const headcount = Array.from({ length: 8 }, (_, i) => Math.max(1, people.length - Math.floor((7 - i) / 3)))
    const current = trend.at(-1)
    const previous = trend.at(-2)
    const kpi = (value: number, prev: number | undefined, history: number[]): Kpi => ({
      value,
      previous: prev ?? null,
      history,
    })

    return {
      totalEmployees: kpi(people.length, headcount.at(-2), headcount),
      online: kpi(active + idle, Math.round((active + idle) * 0.94), recent),
      active: kpi(active, Math.round(active * 0.9), this.timeline.slice(-12).map((p) => Math.round(p.active * scale))),
      idle: kpi(idle, idle + 1, this.timeline.slice(-12).map((p) => Math.round(p.idle * scale))),
      workHours: kpi(current?.workHours ?? 0, previous?.workHours, trend.slice(-8).map((p) => p.workHours)),
      productivity: kpi(current?.productivity ?? 0, previous?.productivity ?? undefined, trend.slice(-8).map((p) => p.productivity ?? 0)),
      asOf: new Date(now).toISOString(),
    }
  }

  trend(filters: DashboardFilters, now = Date.now()): TrendPoint[] {
    const people = this.filtered(filters.teamId).length
    const bias = SAMPLE_TEAMS.find((t) => t.id === filters.teamId)?.bias ?? 0
    const day = (offset: number) => {
      const date = new Date(now - offset * DAY)
      date.setHours(0, 0, 0, 0)
      const weekend = date.getDay() === 0 || date.getDay() === 6
      const key = `${date.toDateString()}|${filters.teamId ?? 'all'}`
      const productivity = Math.min(95, Math.max(45, 71 + bias + 5 * Math.sin(date.getTime() / (9 * DAY)) + (hashUnit(key) - 0.5) * 8 - (weekend ? 6 : 0)))
      const hours = weekend ? people * (0.4 + hashUnit(`${key}h`) * 0.6) : people * (6.6 + hashUnit(`${key}h`) * 1.2)
      return { date, productivity, workHours: hours }
    }

    const buckets: Record<Period, number> = { daily: 14, weekly: 12, monthly: 12 }
    const points: TrendPoint[] = []
    for (let i = buckets[filters.period] - 1; i >= 0; i--) {
      const days =
        filters.period === 'daily'
          ? [day(i)]
          : filters.period === 'weekly'
            ? Array.from({ length: 7 }, (_, d) => day(i * 7 + d))
            : Array.from({ length: 30 }, (_, d) => day(i * 30 + d))
      const start = days.reduce((min, d) => (d.date < min ? d.date : min), days[0]!.date)
      points.push({
        date: start.toISOString(),
        productivity: Math.round((days.reduce((sum, d) => sum + d.productivity, 0) / days.length) * 10) / 10,
        workHours: Math.round(days.reduce((sum, d) => sum + d.workHours, 0)),
      })
    }
    return points
  }

  teamActivity(filters: DashboardFilters): TeamActivity {
    const teams = SAMPLE_TEAMS.filter((t) => !filters.teamId || t.id === filters.teamId).map((team) => {
      const members = this.people.filter((p) => p.teamId === team.id)
      return {
        teamId: team.id,
        teamName: team.name,
        active: members.filter((p) => p.status === 'active').length,
        idle: members.filter((p) => p.status === 'idle').length,
        offline: members.filter((p) => p.status === 'offline').length,
      }
    })
    const scale = this.filtered(filters.teamId).length / this.people.length
    return {
      teams,
      timeline: this.timeline.map((p) => ({ ...p, active: Math.round(p.active * scale), idle: Math.round(p.idle * scale) })),
    }
  }

  liveEmployees(filters: DashboardFilters): LiveEmployee[] {
    return this.filtered(filters.teamId).map((p) => ({ ...p }))
  }

  recentAlerts(filters: DashboardFilters): DashboardAlert[] {
    const ids = new Set(this.filtered(filters.teamId).map((p) => p.person.id))
    return this.alerts.filter((a) => ids.has(a.person.id)).slice(0, 12)
  }

  activity(filters: DashboardFilters): ActivityEvent[] {
    const ids = new Set(this.filtered(filters.teamId).map((p) => p.person.id))
    return this.events.filter((e) => !e.actor || ids.has(e.actor.id)).slice(0, 30)
  }

  // ------------------------------------------------------------------ simulation

  /** Advance the simulation; returns the events that a realtime channel would push. */
  tick(now = Date.now()): DashboardEvent[] {
    const emitted: DashboardEvent[] = []
    const changes = this.random.int(1, 3)
    for (let i = 0; i < changes; i++) {
      const person = this.random.pick(this.people)
      const event = this.transition(person, now)
      if (event) {
        this.events.unshift(event)
        emitted.push({ type: 'activity.created', event })
      }
    }
    if (this.random.chance(0.12)) {
      const alert = this.createAlert(this.random.pick(this.people.filter((p) => p.status !== 'offline')), now, 'open')
      this.alerts.unshift(alert)
      this.events.unshift({
        id: this.id('evt'),
        timestamp: alert.timestamp,
        kind: 'alert',
        actor: alert.person,
        summary: 'triggered an alert',
        detail: alert.detail,
      })
      emitted.push({ type: 'alert.created', alert })
    }
    this.events = this.events.slice(0, 80)
    this.alerts = this.alerts.slice(0, 40)
    this.recordPresence(now)
    emitted.push({ type: 'presence.changed', at: new Date(now).toISOString() })
    return emitted
  }

  private transition(person: PersonState, now: number): ActivityEvent | null {
    const at = new Date(now).toISOString()
    const base = { id: this.id('evt'), timestamp: at, actor: person.person }
    const apps = SAMPLE_APPS[person.teamId] ?? []
    const tasks = SAMPLE_TASKS[person.teamId] ?? []

    if (person.status === 'offline') {
      if (!this.random.chance(0.5)) return null
      Object.assign(person, { status: 'active', since: at, application: this.random.pick(apps) })
      return { ...base, kind: 'session', summary: 'started their workday', detail: person.device?.name }
    }
    if (person.status === 'idle') {
      Object.assign(person, { status: 'active', since: at })
      return { ...base, kind: 'idle', summary: 'is back from idle' }
    }
    const roll = this.random.next()
    if (roll < 0.45) {
      const app = this.random.pick(apps)
      if (app.name === person.application?.name) return null
      person.application = app
      return { ...base, kind: 'application', summary: `switched to ${app.name}` }
    }
    if (roll < 0.65) {
      Object.assign(person, { status: 'idle', since: at })
      return { ...base, kind: 'idle', summary: 'went idle', detail: person.application ? `Last active in ${person.application.name}` : undefined }
    }
    if (roll < 0.9) {
      const task = this.random.pick(tasks)
      const finished = person.task
      person.task = task
      return finished && this.random.chance(0.5)
        ? { ...base, kind: 'task', summary: 'completed a task', detail: finished }
        : { ...base, kind: 'task', summary: 'started working on a task', detail: task }
    }
    Object.assign(person, { status: 'offline', since: at, application: null, task: null })
    return { ...base, kind: 'session', summary: 'signed off' }
  }

  // ------------------------------------------------------------------ seeding

  private seedTimeline(now: number) {
    const total = this.people.length
    let active = Math.round(total * 0.62)
    for (let i = 59; i >= 0; i--) {
      active = Math.max(Math.round(total * 0.45), Math.min(Math.round(total * 0.8), active + this.random.int(-2, 2)))
      const idle = Math.max(1, Math.round(total * 0.16) + this.random.int(-2, 2))
      this.timeline.push({ time: new Date(now - i * MINUTE).toISOString(), active, idle })
    }
    this.recordPresence(now)
  }

  private seedHistory(now: number) {
    const statuses = ['open', 'acknowledged', 'resolved', 'resolved', 'acknowledged'] as const
    for (let i = 0; i < 10; i++) {
      const person = this.random.pick(this.people)
      this.alerts.push(this.createAlert(person, now - (i * 95 + this.random.int(5, 60)) * MINUTE, i < 2 ? 'open' : this.random.pick(statuses)))
    }
    for (let i = 0; i < 28; i++) {
      const person = this.random.pick(this.people)
      const apps = SAMPLE_APPS[person.teamId] ?? []
      const tasks = SAMPLE_TASKS[person.teamId] ?? []
      const kinds: ActivityEvent[] = [
        { id: '', timestamp: '', kind: 'application', actor: person.person, summary: `switched to ${this.random.pick(apps).name}` },
        { id: '', timestamp: '', kind: 'task', actor: person.person, summary: 'started working on a task', detail: this.random.pick(tasks) },
        { id: '', timestamp: '', kind: 'session', actor: person.person, summary: 'started their workday', detail: person.device?.name },
        { id: '', timestamp: '', kind: 'idle', actor: person.person, summary: 'is back from idle' },
      ]
      const event = this.random.pick(kinds)
      this.events.push({ ...event, id: this.id('evt'), timestamp: new Date(now - (i * 6 + this.random.int(1, 5)) * MINUTE).toISOString() })
    }
  }

  private createAlert(person: PersonState, at: number, status: DashboardAlert['status']): DashboardAlert {
    const spec = this.random.pick(SAMPLE_ALERT_TYPES)
    const unproductive = (SAMPLE_APPS[person.teamId] ?? []).find((a) => a.category === 'unproductive')?.name ?? 'YouTube'
    return {
      id: this.id('alert'),
      timestamp: new Date(at).toISOString(),
      person: person.person,
      type: spec.type,
      detail: spec.detail(unproductive),
      severity: spec.severity,
      status,
    }
  }

  private recordPresence(now: number) {
    const point = {
      time: new Date(now).toISOString(),
      active: this.people.filter((p) => p.status === 'active').length,
      idle: this.people.filter((p) => p.status === 'idle').length,
    }
    const last = this.timeline.at(-1)
    if (last && now - new Date(last.time).getTime() < MINUTE) this.timeline[this.timeline.length - 1] = { ...point, time: last.time }
    else this.timeline = [...this.timeline.slice(-59), point]
  }

  private filtered(teamId: string | null) {
    return teamId ? this.people.filter((p) => p.teamId === teamId) : this.people
  }

  private randomStatus(): PresenceStatus {
    const roll = this.random.next()
    return roll < 0.66 ? 'active' : roll < 0.84 ? 'idle' : 'offline'
  }

  private id(prefix: string) {
    this.sequence += 1
    return `${prefix}-${this.sequence}`
  }
}
