---
name: robust-frontend
description: Build production-grade, robust frontend applications using a modern stack including Framer Motion, Three.js, AOS, GSAP for animation; Shadcn/UI and other component libraries; TanStack Query for server state; TanStack Start or Vite as the build tool; component-based design; Tailwind CSS; Redux for global state; and WebSocket with Socket.io for real-time features. Use this skill whenever the user wants to build a full frontend app, a complex React component, a real-time dashboard, an animated landing page, a data-fetching UI, or any frontend that involves state management, animations, or live data. Trigger even if only some of these technologies are mentioned — this skill covers the full stack of modern frontend tooling.
---

# Robust Frontend Skill

This skill guides building production-grade frontend applications using a curated modern stack. Follow the phases in order. Read the relevant reference files before writing code.

---

## Phase 0 — Understand the Project

Before any code, answer:
1. **Build tool**: Vite (SPA/library) or TanStack Start (SSR/full-stack)?
2. **Animations needed**: Framer Motion (React), GSAP (timeline/complex), Three.js (3D), AOS (scroll reveal)?
3. **Real-time**: Does the app need WebSocket / Socket.io?
4. **State shape**: Local state only, or global Redux store + TanStack Query?
5. **UI components**: Shadcn/UI base + which extras (Radix, React Aria, Headless UI)?

Read **`references/stack-decisions.md`** for selection guidance.

---

## Phase 1 — Project Scaffold

### Vite (SPA)
```bash
npm create vite@latest my-app -- --template react-ts
cd my-app
npm install
```

### TanStack Start (SSR / full-stack)
```bash
npx create-tsrouter-app@latest my-app --template react-start
cd my-app
npm install
```

Then install the full stack:
```bash
# Core UI
npm install tailwindcss @tailwindcss/vite
npx shadcn@latest init

# State
npm install @reduxjs/toolkit react-redux
npm install @tanstack/react-query @tanstack/react-query-devtools

# Animation
npm install framer-motion gsap @gsap/react
npm install three @types/three @react-three/fiber @react-three/drei
npm install aos @types/aos

# Real-time
npm install socket.io-client

# Utilities
npm install axios zod react-hook-form @hookform/resolvers
```

Read **`references/scaffold.md`** for full config files (tailwind.config, tsconfig, vite.config, tanstack-start.config).

---

## Phase 2 — Architecture & Folder Structure

Use a **feature-based** component architecture:

```
src/
├── app/                  # App shell, providers, router
│   ├── providers.tsx     # All context providers composed here
│   ├── router.tsx        # TanStack Router or React Router config
│   └── store.ts          # Redux store
├── features/             # One folder per domain feature
│   └── [feature]/
│       ├── components/   # Feature-specific components
│       ├── hooks/        # Custom hooks
│       ├── api.ts        # TanStack Query definitions
│       ├── slice.ts      # Redux slice
│       └── types.ts
├── components/           # Shared/global components
│   ├── ui/               # Shadcn-generated components (never edit directly)
│   └── common/           # App-wide reusable components
├── lib/                  # Utilities, constants, helpers
│   ├── socket.ts         # Socket.io singleton
│   └── queryClient.ts    # TanStack Query client config
├── hooks/                # Global custom hooks
├── styles/               # Global CSS, Tailwind base overrides
└── types/                # Shared TypeScript types
```

**Key rules:**
- Every feature is self-contained; cross-feature imports go through `components/` or `lib/`
- UI components from Shadcn live in `components/ui/` — never modify them directly, extend via wrapper components
- One Redux slice per feature; combine in `app/store.ts`

---

## Phase 3 — Providers Setup

Compose all providers in `app/providers.tsx`:

```tsx
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { Provider as ReduxProvider } from 'react-redux'
import { queryClient } from '@/lib/queryClient'
import { store } from '@/app/store'

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ReduxProvider store={store}>
      <QueryClientProvider client={queryClient}>
        {children}
        <ReactQueryDevtools initialIsOpen={false} />
      </QueryClientProvider>
    </ReduxProvider>
  )
}
```

---

## Phase 4 — Animation Patterns

Read **`references/animations.md`** for full patterns. Quick reference:

### Framer Motion — component-level animations
```tsx
import { motion, AnimatePresence } from 'framer-motion'

// Page transition
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  exit={{ opacity: 0, y: -20 }}
  transition={{ duration: 0.3, ease: 'easeOut' }}
/>

// Stagger children
const container = { hidden: {}, show: { transition: { staggerChildren: 0.1 } } }
const item = { hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }
```

### GSAP — complex timelines, scroll triggers
```tsx
import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
gsap.registerPlugin(ScrollTrigger, useGSAP)

useGSAP(() => {
  gsap.from('.hero-text', {
    y: 60, opacity: 0, duration: 1, ease: 'power3.out',
    scrollTrigger: { trigger: '.hero', start: 'top 80%' }
  })
}, { scope: containerRef })
```

### AOS — declarative scroll reveal (HTML attribute-driven)
```tsx
import AOS from 'aos'
import 'aos/dist/aos.css'
useEffect(() => { AOS.init({ duration: 800, once: true }) }, [])
// Usage: <div data-aos="fade-up" data-aos-delay="100">
```

### Three.js — 3D scenes with React Three Fiber
```tsx
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Environment } from '@react-three/drei'
<Canvas camera={{ position: [0, 0, 5] }}>
  <ambientLight intensity={0.5} />
  <mesh><boxGeometry /><meshStandardMaterial /></mesh>
  <OrbitControls />
  <Environment preset="city" />
</Canvas>
```

**Animation selection guide:**
- UI transitions & gestures → **Framer Motion**
- Complex sequenced timelines, scroll-driven → **GSAP**
- Lightweight scroll reveal with zero config → **AOS**
- 3D / WebGL / particle systems → **Three.js + R3F**
- Combine freely; they don't conflict

---

## Phase 5 — TanStack Query (Server State)

Read **`references/tanstack-query.md`** for advanced patterns. Core setup:

```ts
// lib/queryClient.ts
import { QueryClient } from '@tanstack/react-query'
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60 * 1000, retry: 2, refetchOnWindowFocus: false },
    mutations: { onError: (err) => console.error(err) },
  },
})
```

```ts
// features/posts/api.ts
import { queryOptions, useMutation } from '@tanstack/react-query'
import axios from 'axios'

export const postsQueryOptions = queryOptions({
  queryKey: ['posts'],
  queryFn: () => axios.get('/api/posts').then(r => r.data),
})

export function useCreatePost() {
  return useMutation({
    mutationFn: (data: PostInput) => axios.post('/api/posts', data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['posts'] }),
  })
}
```

**Rules:**
- All server state lives in TanStack Query — never in Redux
- Redux is for UI state, user session, feature flags, real-time ephemeral state
- Use `queryOptions()` helper for type-safe, reusable query definitions
- Prefetch in route loaders (TanStack Start) for SSR: `await queryClient.prefetchQuery(postsQueryOptions)`

---

## Phase 6 — Redux (Client / UI State)

```ts
// features/sidebar/slice.ts
import { createSlice, PayloadAction } from '@reduxjs/toolkit'
interface SidebarState { isOpen: boolean; activeTab: string }
const initialState: SidebarState = { isOpen: true, activeTab: 'home' }

export const sidebarSlice = createSlice({
  name: 'sidebar',
  initialState,
  reducers: {
    toggle: (state) => { state.isOpen = !state.isOpen },
    setTab: (state, action: PayloadAction<string>) => { state.activeTab = action.payload },
  },
})
export const { toggle, setTab } = sidebarSlice.actions
```

```ts
// app/store.ts
import { configureStore } from '@reduxjs/toolkit'
import { sidebarSlice } from '@/features/sidebar/slice'
export const store = configureStore({ reducer: { sidebar: sidebarSlice.reducer } })
export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
```

Always create typed hooks:
```ts
// hooks/redux.ts
import { useDispatch, useSelector } from 'react-redux'
import type { RootState, AppDispatch } from '@/app/store'
export const useAppDispatch = () => useDispatch<AppDispatch>()
export const useAppSelector = <T>(selector: (state: RootState) => T) => useSelector(selector)
```

---

## Phase 7 — WebSocket with Socket.io

Read **`references/websocket.md`** for full real-time patterns. Core singleton:

```ts
// lib/socket.ts
import { io, Socket } from 'socket.io-client'
let socket: Socket | null = null
export function getSocket(): Socket {
  if (!socket) {
    socket = io(import.meta.env.VITE_WS_URL ?? 'http://localhost:3001', {
      transports: ['websocket'],
      autoConnect: false,
    })
  }
  return socket
}
```

Custom hook pattern:
```tsx
// hooks/useSocket.ts
export function useSocket<T>(event: string, handler: (data: T) => void) {
  const socket = getSocket()
  useEffect(() => {
    if (!socket.connected) socket.connect()
    socket.on(event, handler)
    return () => { socket.off(event, handler) }
  }, [event, handler])
  return socket
}
```

Integrate with Redux for real-time state:
```tsx
const dispatch = useAppDispatch()
useSocket<Message>('new-message', (msg) => dispatch(addMessage(msg)))
```

---

## Phase 8 — Shadcn + Component Library Patterns

```bash
# Add components as needed
npx shadcn@latest add button card dialog table form input select
```

**Extension pattern** — never modify Shadcn files directly:
```tsx
// components/common/AppButton.tsx
import { Button, ButtonProps } from '@/components/ui/button'
import { cn } from '@/lib/utils'
interface AppButtonProps extends ButtonProps { loading?: boolean }
export function AppButton({ loading, children, className, ...props }: AppButtonProps) {
  return (
    <Button className={cn('gap-2', className)} disabled={loading || props.disabled} {...props}>
      {loading && <Spinner className="size-4 animate-spin" />}
      {children}
    </Button>
  )
}
```

Additional libraries that pair well with Shadcn:
- **Radix UI** primitives (Shadcn is built on these — use directly for unstyled control)
- **React Aria** (Adobe) — accessibility-first headless components
- **Headless UI** — Tailwind-native unstyled components
- **Vaul** — drawer/bottom sheet
- **Sonner** — toast notifications
- **Cmdk** — command palette
- **React Table** (TanStack Table) — headless data tables

---

## Phase 9 — Tailwind CSS Conventions

```ts
// tailwind.config.ts
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: 'hsl(var(--brand))', foreground: 'hsl(var(--brand-foreground))' },
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.4s ease-out',
      },
      keyframes: {
        fadeIn: { from: { opacity: '0' }, to: { opacity: '1' } },
        slideUp: { from: { transform: 'translateY(1rem)', opacity: '0' }, to: { transform: 'translateY(0)', opacity: '1' } },
      },
    },
  },
}
```

**Conventions:**
- Use `cn()` from `@/lib/utils` for conditional classes (clsx + tailwind-merge)
- Define design tokens as CSS variables in `globals.css`, map to Tailwind theme
- Use `@layer components` for repeated complex patterns
- Never use arbitrary values (`[32px]`) for anything that should be a design token

---

## Phase 10 — Quality Checklist

Before delivering code, verify:

- [ ] All providers composed in `app/providers.tsx`
- [ ] TypeScript strict mode on; no `any` types
- [ ] TanStack Query handles all async server state
- [ ] Redux only for client/UI/real-time ephemeral state
- [ ] Socket singleton — no duplicate connections
- [ ] Animations use `useGSAP` (not raw `useEffect`) for GSAP; cleanup on unmount for all
- [ ] Three.js scenes dispose geometries/materials on unmount
- [ ] Shadcn components never modified directly; extended via wrappers
- [ ] `cn()` used for all conditional Tailwind classes
- [ ] Feature folders are self-contained
- [ ] Error boundaries around async/animated sections
- [ ] Loading states for all async operations

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/stack-decisions.md` | Choosing between tools, explaining tradeoffs |
| `references/scaffold.md` | Full config files for Vite / TanStack Start |
| `references/animations.md` | Advanced animation patterns and combos |
| `references/tanstack-query.md` | Query patterns, optimistic updates, SSR prefetch |
| `references/websocket.md` | Full Socket.io patterns, rooms, reconnection |
