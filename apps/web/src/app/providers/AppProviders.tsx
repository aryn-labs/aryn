import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ApiError } from '@/lib/api/client'
import { TooltipProvider } from '@/components/ui/tooltip'
import { WorkspaceProvider } from './WorkspaceProvider'
import { ShellProvider } from './ShellProvider'
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      retry: (count, error) =>
        !(error instanceof ApiError && [401, 403, 404].includes(error.status)) && count < 1,
    },
  },
})
export function AppProviders({
  children,
  client = queryClient,
}: {
  children: ReactNode
  client?: QueryClient
}) {
  return (
    <QueryClientProvider client={client}>
      <WorkspaceProvider>
        <ShellProvider>
          <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
        </ShellProvider>
      </WorkspaceProvider>
    </QueryClientProvider>
  )
}
