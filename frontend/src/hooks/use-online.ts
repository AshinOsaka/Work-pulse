import { useSyncExternalStore } from 'react'
import { onlineManager } from '@tanstack/react-query'

const subscribe = (notify: () => void) => onlineManager.subscribe(notify)
const isOnline = () => onlineManager.isOnline()

/** Whether the browser is online, as TanStack Query sees it (queries pause while offline and resume after). */
export function useOnline(): boolean {
  return useSyncExternalStore(subscribe, isOnline)
}
