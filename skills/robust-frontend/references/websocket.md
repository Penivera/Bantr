# WebSocket / Socket.io Reference

## Singleton Setup

```ts
// lib/socket.ts
import { io, Socket } from 'socket.io-client'

let socket: Socket | null = null

export function getSocket(): Socket {
  if (!socket) {
    socket = io(import.meta.env.VITE_WS_URL ?? 'http://localhost:3001', {
      transports: ['websocket'],
      autoConnect: false,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      timeout: 10_000,
    })

    // Global lifecycle logging (dev only)
    if (import.meta.env.DEV) {
      socket.on('connect', () => console.log('[socket] connected:', socket?.id))
      socket.on('disconnect', (reason) => console.log('[socket] disconnected:', reason))
      socket.on('connect_error', (err) => console.error('[socket] error:', err.message))
    }
  }
  return socket
}

export function disconnectSocket() {
  socket?.disconnect()
  socket = null
}
```

---

## Connection Hook

```tsx
// hooks/useSocketConnection.ts
import { useEffect, useState } from 'react'
import { getSocket } from '@/lib/socket'

export function useSocketConnection() {
  const [isConnected, setIsConnected] = useState(false)
  const socket = getSocket()

  useEffect(() => {
    function onConnect() { setIsConnected(true) }
    function onDisconnect() { setIsConnected(false) }

    socket.on('connect', onConnect)
    socket.on('disconnect', onDisconnect)
    socket.connect()

    return () => {
      socket.off('connect', onConnect)
      socket.off('disconnect', onDisconnect)
    }
  }, [socket])

  return { socket, isConnected }
}
```

---

## Event Subscription Hook

```tsx
// hooks/useSocketEvent.ts
import { useEffect, useCallback } from 'react'
import { getSocket } from '@/lib/socket'

export function useSocketEvent<T>(
  event: string,
  handler: (data: T) => void,
  deps: unknown[] = []
) {
  const socket = getSocket()
  const stableHandler = useCallback(handler, deps)

  useEffect(() => {
    socket.on(event, stableHandler)
    return () => { socket.off(event, stableHandler) }
  }, [event, stableHandler, socket])
}
```

---

## Emit Hook

```tsx
// hooks/useSocketEmit.ts
import { useCallback } from 'react'
import { getSocket } from '@/lib/socket'

export function useSocketEmit() {
  const socket = getSocket()

  const emit = useCallback(<T>(event: string, data?: T): void => {
    socket.emit(event, data)
  }, [socket])

  const emitWithAck = useCallback(<T, R>(event: string, data?: T): Promise<R> => {
    return new Promise((resolve, reject) => {
      socket.timeout(5000).emit(event, data, (err: Error, response: R) => {
        if (err) reject(err)
        else resolve(response)
      })
    })
  }, [socket])

  return { emit, emitWithAck }
}
```

---

## Rooms Pattern

```tsx
// Joining and leaving a room
function useChatRoom(roomId: string) {
  const socket = getSocket()

  useEffect(() => {
    socket.emit('room:join', { roomId })
    return () => { socket.emit('room:leave', { roomId }) }
  }, [roomId, socket])
}

// Usage in a chat feature
function ChatRoom({ roomId }: { roomId: string }) {
  useChatRoom(roomId)
  const dispatch = useAppDispatch()

  useSocketEvent<Message>('message:new', (msg) => {
    dispatch(addMessage(msg))
  }, [dispatch])

  // ...
}
```

---

## Redux Integration (real-time state)

```ts
// features/chat/slice.ts
import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface Message { id: string; text: string; senderId: string; timestamp: number }
interface ChatState { messages: Message[]; onlineUsers: string[] }

export const chatSlice = createSlice({
  name: 'chat',
  initialState: { messages: [], onlineUsers: [] } as ChatState,
  reducers: {
    addMessage: (state, { payload }: PayloadAction<Message>) => {
      state.messages.push(payload)
    },
    setOnlineUsers: (state, { payload }: PayloadAction<string[]>) => {
      state.onlineUsers = payload
    },
    userJoined: (state, { payload }: PayloadAction<string>) => {
      if (!state.onlineUsers.includes(payload)) state.onlineUsers.push(payload)
    },
    userLeft: (state, { payload }: PayloadAction<string>) => {
      state.onlineUsers = state.onlineUsers.filter(id => id !== payload)
    },
  },
})
```

```tsx
// features/chat/ChatProvider.tsx — wire socket events to Redux
export function ChatSocketProvider({ children }: { children: React.ReactNode }) {
  const dispatch = useAppDispatch()

  useSocketEvent<Message>('message:new', (msg) => dispatch(addMessage(msg)))
  useSocketEvent<string[]>('users:online', (users) => dispatch(setOnlineUsers(users)))
  useSocketEvent<string>('user:joined', (id) => dispatch(userJoined(id)))
  useSocketEvent<string>('user:left', (id) => dispatch(userLeft(id)))

  return <>{children}</>
}
```

---

## Auth / Token Handshake

```ts
// lib/socket.ts — pass auth token
export function getSocket(token?: string): Socket {
  if (!socket) {
    socket = io(import.meta.env.VITE_WS_URL, {
      auth: { token: token ?? localStorage.getItem('token') },
      transports: ['websocket'],
    })
  }
  return socket
}

// Re-auth after login (recreate socket)
export function reconnectWithToken(token: string) {
  socket?.disconnect()
  socket = null
  getSocket(token).connect()
}
```

---

## Typing Indicators Pattern

```tsx
function useTypingIndicator(roomId: string) {
  const { emit } = useSocketEmit()
  const [typingUsers, setTypingUsers] = useState<string[]>([])

  useSocketEvent<{ userId: string; isTyping: boolean }>('typing', ({ userId, isTyping }) => {
    setTypingUsers(prev =>
      isTyping ? [...new Set([...prev, userId])] : prev.filter(id => id !== userId)
    )
  })

  const sendTyping = useCallback(
    debounce((isTyping: boolean) => {
      emit('typing', { roomId, isTyping })
    }, 300),
    [roomId, emit]
  )

  return { typingUsers, sendTyping }
}
```

---

## Connection Status UI

```tsx
function ConnectionStatus() {
  const { isConnected } = useSocketConnection()
  return (
    <div className={cn('flex items-center gap-2 text-sm', isConnected ? 'text-green-500' : 'text-red-500')}>
      <span className={cn('size-2 rounded-full', isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500')} />
      {isConnected ? 'Connected' : 'Disconnected'}
    </div>
  )
}
```

---

## Server-side Reference (Node.js + Express)

```ts
// server.ts — for reference when building the backend counterpart
import { createServer } from 'http'
import { Server } from 'socket.io'
import express from 'express'

const app = express()
const httpServer = createServer(app)
const io = new Server(httpServer, {
  cors: { origin: 'http://localhost:5173', credentials: true },
})

io.use((socket, next) => {
  const token = socket.handshake.auth.token
  // verify token...
  next()
})

io.on('connection', (socket) => {
  socket.on('room:join', ({ roomId }) => socket.join(roomId))
  socket.on('room:leave', ({ roomId }) => socket.leave(roomId))
  socket.on('message:send', (msg) => {
    io.to(msg.roomId).emit('message:new', { ...msg, id: crypto.randomUUID(), timestamp: Date.now() })
  })
})

httpServer.listen(3001)
```
