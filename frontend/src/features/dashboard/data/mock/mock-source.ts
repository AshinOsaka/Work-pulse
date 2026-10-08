/**
 * SAMPLE DATA SOURCE — implements `DashboardDataSource` with simulated data.
 *
 * Delete this folder once the desktop agent and analytics APIs exist; the
 * live source (`../live-source.ts`) is the only other implementation needed.
 */
import { SampleWorkspace } from '@/features/dashboard/data/mock/sample-workspace'
import type { DashboardDataSource, DashboardEvent } from '@/features/dashboard/data/types'

const TICK_MS = 4_000
const LATENCY_MS = 250

let workspace: SampleWorkspace | null = null
const getWorkspace = () => (workspace ??= new SampleWorkspace())

/** Simulate network latency so loading states are exercised realistically. */
const respond = <T,>(produce: () => T) => new Promise<T>((resolve) => window.setTimeout(() => resolve(produce()), LATENCY_MS))

const listeners = new Set<(event: DashboardEvent) => void>()
let timer: number | undefined

export const sampleSource: DashboardDataSource = {
  kind: 'sample',
  availability: { presence: true, productivity: true, alerts: true, activity: true },
  getTeams: () => respond(() => getWorkspace().teams()),
  getKpis: (filters) => respond(() => getWorkspace().kpis(filters)),
  getProductivityTrend: (filters) => respond(() => getWorkspace().trend(filters)),
  getTeamActivity: (filters) => respond(() => getWorkspace().teamActivity(filters)),
  getLiveEmployees: (filters) => respond(() => getWorkspace().liveEmployees(filters)),
  getAlerts: (filters) => respond(() => getWorkspace().recentAlerts(filters)),
  getActivity: (filters) => respond(() => getWorkspace().activity(filters)),
  subscribe(listener) {
    listeners.add(listener)
    timer ??= window.setInterval(() => {
      const events = getWorkspace().tick()
      listeners.forEach((l) => events.forEach((event) => l(event)))
    }, TICK_MS)
    return () => {
      listeners.delete(listener)
      if (listeners.size === 0) {
        window.clearInterval(timer)
        timer = undefined
      }
    }
  },
}
