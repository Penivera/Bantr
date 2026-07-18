# TanStack Query Reference

## Core Concepts

- **QueryClient** — central cache, configured once, provided via `QueryClientProvider`
- **useQuery** — read data from server, auto-caches, background-refreshes
- **useMutation** — write data, then invalidate or update cache
- **queryOptions()** — factory for type-safe reusable query definitions (v5+)
- **Infinite queries** — paginated / infinite scroll data
- **Optimistic updates** — update UI before server confirms

---

## Query Options Pattern (recommended)

```ts
// features/users/api.ts
import { queryOptions, infiniteQueryOptions } from '@tanstack/react-query'
import { queryClient } from '@/lib/queryClient'
import axios from 'axios'
import type { User, PaginatedUsers } from './types'

// Reusable query definitions
export const usersQueryOptions = queryOptions({
  queryKey: ['users'],
  queryFn: (): Promise<User[]> => axios.get('/api/users').then(r => r.data),
})

export const userQueryOptions = (id: string) => queryOptions({
  queryKey: ['users', id],
  queryFn: (): Promise<User> => axios.get(`/api/users/${id}`).then(r => r.data),
  enabled: !!id,
})

export const usersInfiniteOptions = infiniteQueryOptions({
  queryKey: ['users', 'infinite'],
  queryFn: ({ pageParam }) =>
    axios.get(`/api/users?page=${pageParam}&limit=20`).then(r => r.data) as Promise<PaginatedUsers>,
  initialPageParam: 1,
  getNextPageParam: (last) => last.hasMore ? last.page + 1 : undefined,
})
```

---

## Mutations with Cache Updates

```ts
// features/users/api.ts (continued)
export function useCreateUser() {
  return useMutation({
    mutationFn: (data: CreateUserInput) =>
      axios.post<User>('/api/users', data).then(r => r.data),

    // Option A: invalidate → refetch from server
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

export function useUpdateUser() {
  return useMutation({
    mutationFn: ({ id, ...data }: UpdateUserInput) =>
      axios.patch<User>(`/api/users/${id}`, data).then(r => r.data),

    // Option B: optimistic update
    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: ['users', variables.id] })
      const previous = queryClient.getQueryData(userQueryOptions(variables.id).queryKey)
      queryClient.setQueryData(userQueryOptions(variables.id).queryKey, (old: User) => ({
        ...old, ...variables,
      }))
      return { previous }
    },
    onError: (_, variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(userQueryOptions(variables.id).queryKey, context.previous)
      }
    },
    onSettled: (_, __, variables) => {
      queryClient.invalidateQueries({ queryKey: ['users', variables.id] })
    },
  })
}

export function useDeleteUser() {
  return useMutation({
    mutationFn: (id: string) => axios.delete(`/api/users/${id}`),
    onSuccess: (_, id) => {
      // Remove from list cache immediately
      queryClient.setQueryData(['users'], (old: User[] | undefined) =>
        old?.filter(u => u.id !== id) ?? []
      )
    },
  })
}
```

---

## Using Queries in Components

```tsx
import { useQuery, useSuspenseQuery } from '@tanstack/react-query'

// Standard (handles loading/error manually)
function UserList() {
  const { data: users, isLoading, isError, error } = useQuery(usersQueryOptions)
  if (isLoading) return <Skeleton />
  if (isError) return <ErrorMessage error={error} />
  return <ul>{users.map(u => <UserCard key={u.id} user={u} />)}</ul>
}

// Suspense mode (wrap in <Suspense> + <ErrorBoundary>)
function UserListSuspense() {
  const { data: users } = useSuspenseQuery(usersQueryOptions)
  return <ul>{users.map(u => <UserCard key={u.id} user={u} />)}</ul>
}

// Infinite scroll
function InfiniteUsers() {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery(usersInfiniteOptions)

  return (
    <>
      {data?.pages.flatMap(p => p.items).map(u => <UserCard key={u.id} user={u} />)}
      {hasNextPage && (
        <button onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
          {isFetchingNextPage ? 'Loading...' : 'Load more'}
        </button>
      )}
    </>
  )
}
```

---

## SSR Prefetching (TanStack Start)

```tsx
// Route loader — prefetch before render
export const Route = createFileRoute('/users')({
  loader: async ({ context: { queryClient } }) => {
    await queryClient.ensureQueryData(usersQueryOptions)
    // Data is in cache when component renders
  },
  component: UserListSuspense,
})
```

---

## Real-time + TanStack Query (Socket.io integration)

```tsx
// Invalidate or update query cache on socket events
useEffect(() => {
  const socket = getSocket()
  socket.on('user:created', (user: User) => {
    queryClient.setQueryData(['users'], (old: User[] = []) => [...old, user])
  })
  socket.on('user:updated', (user: User) => {
    queryClient.setQueryData(['users', user.id], user)
    queryClient.setQueryData(['users'], (old: User[] = []) =>
      old.map(u => u.id === user.id ? user : u)
    )
  })
  return () => {
    socket.off('user:created')
    socket.off('user:updated')
  }
}, [])
```

---

## Query Key Conventions

```ts
// Hierarchical keys enable selective invalidation
['users']                          // all users
['users', userId]                  // single user
['users', userId, 'posts']         // user's posts
['posts', { status: 'published' }] // filtered

// Invalidate all user queries
queryClient.invalidateQueries({ queryKey: ['users'] })

// Invalidate only a specific user
queryClient.invalidateQueries({ queryKey: ['users', userId] })
```

---

## Global Error Handling

```ts
// lib/queryClient.ts
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      throwOnError: false, // set true to use Error Boundaries
      retry: (failureCount, error) => {
        if (error?.response?.status === 401) return false // don't retry auth errors
        return failureCount < 2
      },
    },
    mutations: {
      onError: (error) => {
        // Global toast notification
        toast.error(error?.response?.data?.message ?? 'Something went wrong')
      },
    },
  },
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (query.state.data !== undefined) {
        // Only show error toast if we previously had data (background refresh failed)
        toast.error('Failed to refresh data')
      }
    },
  }),
})
```
