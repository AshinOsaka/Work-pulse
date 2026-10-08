import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { ask, assistantKeys, fetchConversation, type AskEvent, type AssistantTurn, type Turn } from '@/features/assistant/api'
import { errorMessage } from '@/lib/api-client'

export type ChatTurn = Turn | (AssistantTurn & { streaming?: boolean })

interface ChatState {
  conversationId: string | null
  title: string | null
  turns: ChatTurn[]
  loading: boolean
  loadError: string | null
}

const EMPTY: ChatState = { conversationId: null, title: null, turns: [], loading: false, loadError: null }

const now = () => new Date().toISOString()

/** One conversation at a time: ask (streamed), stop, open from history, start over. */
export function useAssistantChat() {
  const client = useQueryClient()
  const [state, setState] = useState<ChatState>(EMPTY)
  const [streaming, setStreaming] = useState(false)
  const controller = useRef<AbortController | null>(null)
  // Bumped whenever the visible conversation changes, so late events from an abandoned stream are dropped.
  const generation = useRef(0)
  // The conversation the next question continues (a ref, so `send` doesn't change identity on every answer).
  const current = useRef<string | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  const refreshList = useCallback(() => void client.invalidateQueries({ queryKey: assistantKeys.conversations }), [client])

  const abandon = useCallback(() => {
    generation.current++
    controller.current?.abort()
    controller.current = null
    setStreaming(false)
  }, [])

  const reset = useCallback(() => {
    abandon()
    current.current = null
    setState(EMPTY)
  }, [abandon])

  const open = useCallback(
    async (id: string) => {
      abandon()
      const mine = generation.current
      current.current = id
      setState({ ...EMPTY, conversationId: id, loading: true })
      try {
        const conversation = await client.fetchQuery({ queryKey: assistantKeys.conversation(id), queryFn: () => fetchConversation(id), staleTime: 0 })
        if (generation.current === mine) setState({ conversationId: id, title: conversation.title, turns: conversation.turns, loading: false, loadError: null })
      } catch (error) {
        if (generation.current === mine) setState({ ...EMPTY, conversationId: id, loadError: errorMessage(error) })
      }
    },
    [abandon, client],
  )

  const send = useCallback(
    async (message: string) => {
      const text = message.trim()
      if (!text || controller.current) return
      const mine = generation.current
      const abort = new AbortController()
      controller.current = abort
      setStreaming(true)
      const pendingId = `pending-${Date.now()}`
      const answer: AssistantTurn & { streaming: boolean } = { id: pendingId, role: 'assistant', text: '', cards: [], tools: [], error: null, created_at: now(), streaming: true }
      setState((s) => ({ ...s, loadError: null, turns: [...s.turns, { id: `${pendingId}-q`, role: 'user', text, created_at: now() }, answer] }))

      const patch = (update: (turn: AssistantTurn & { streaming?: boolean }) => AssistantTurn & { streaming?: boolean }) => {
        if (generation.current !== mine) return
        setState((s) => ({ ...s, turns: s.turns.map((t) => (t.id === pendingId && t.role === 'assistant' ? update(t) : t)) }))
      }
      const onEvent = (event: AskEvent) => {
        if (generation.current !== mine) return
        switch (event.type) {
          case 'start':
            current.current = event.conversation_id
            setState((s) => ({ ...s, conversationId: event.conversation_id, title: s.title ?? event.title }))
            break
          case 'text':
            patch((t) => ({ ...t, text: t.text + event.delta }))
            break
          case 'tool':
            patch((t) => {
              const { type: _type, ...use } = event
              const at = t.tools.findIndex((u) => u.id && u.id === use.id)
              return { ...t, tools: at === -1 ? [...t.tools, use] : t.tools.map((u, n) => (n === at ? use : u)) }
            })
            break
          case 'card':
            patch((t) => ({ ...t, cards: [...t.cards, event.card] }))
            break
          case 'error':
            patch((t) => ({ ...t, error: event.message }))
            break
          case 'done':
            patch(() => event.turn)
            break
        }
      }

      let failure: string | null = null
      try {
        await ask({ message: text, conversation_id: current.current ?? undefined }, onEvent, abort.signal)
      } catch (error) {
        failure = abort.signal.aborted ? 'Stopped. This answer was not saved.' : errorMessage(error)
      }
      patch((t) => ({ ...t, streaming: false, error: t.error ?? failure }))
      if (controller.current === abort) {
        controller.current = null
        setStreaming(false)
      }
      refreshList()
    },
    [refreshList],
  )

  const stop = useCallback(() => controller.current?.abort(), [])

  return { ...state, streaming, send, stop, open, reset }
}
