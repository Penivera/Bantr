# Stack Decisions Reference

## Build Tool: Vite vs TanStack Start

| Need | Choose |
|------|--------|
| Pure SPA, static site, component library | **Vite** |
| SSR, SEO, server functions, full-stack | **TanStack Start** |
| Fast prototype, no backend | **Vite** |
| Data fetching at route level (loaders) | **TanStack Start** |

**TanStack Start** uses TanStack Router under the hood — file-based routing, type-safe links, loader-based data fetching. Best for apps that need server-side rendering or server actions.

**Vite** is simpler, faster to set up, ideal for SPAs that talk to a separate API server.

---

## Animation Library Selection

| Scenario | Library |
|----------|---------|
| UI micro-interactions, layout animations, page transitions | Framer Motion |
| Complex sequenced timelines (intro animations, scroll-driven) | GSAP |
| Lightweight scroll reveal (marketing pages, landing pages) | AOS |
| 3D scenes, WebGL, particle systems | Three.js + React Three Fiber |
| Both scroll timeline AND React components | GSAP + Framer Motion |

**Combining libraries**: All four are compatible. A common pattern is:
- Framer Motion for interactive component states (hover, click, modal)
- GSAP for the hero / intro timeline
- AOS for below-the-fold scroll reveals
- Three.js for a 3D hero background or product viewer

---

## State: TanStack Query vs Redux

| State type | Tool |
|-----------|------|
| Data from an API endpoint | **TanStack Query** |
| Loading / error state for API calls | **TanStack Query** (built-in) |
| Sidebar open/closed | **Redux** |
| User auth session / JWT | **Redux** (or context) |
| Selected filters / active tab | **Redux** |
| Real-time data arriving from WebSocket | **Redux** (dispatch on socket event) |
| Form state | **React Hook Form** (local) |
| Paginated / infinite API data | **TanStack Query** |

**Rule of thumb**: If the data lives on a server and needs caching, invalidation, or background refresh → TanStack Query. If it's UI state that only exists on the client → Redux.

---

## Component Library Combinations

### Shadcn as the base (recommended default)
Shadcn gives you copy-paste components built on Radix UI, styled with Tailwind. Extend with:
- **Vaul** — mobile-friendly drawer / bottom sheet
- **Sonner** — beautiful toast notifications (replaces Shadcn's built-in)
- **Cmdk** — command palette (used by Shadcn's own command component)
- **TanStack Table** — headless data table, pair with Shadcn's Table styling
- **React Hook Form + Zod** — forms with schema validation

### If you need more accessibility control
- Replace or supplement Shadcn with **React Aria** (Adobe) for WCAG-compliant headless components
- **Headless UI** (Tailwind Labs) for simpler cases

### For data-heavy dashboards
- **Recharts** or **Victory** for charts (Tailwind-friendly)
- **TanStack Table** for complex tables with sorting/filtering
- **React Virtual** (TanStack) for virtualized long lists

---

## Socket.io vs Native WebSocket

Use **Socket.io** (this skill) when you need:
- Automatic reconnection
- Room/namespace support
- Fallback to polling
- Event-based API (not raw binary frames)

Use native **WebSocket** only when you control both ends and need raw performance with no overhead.
