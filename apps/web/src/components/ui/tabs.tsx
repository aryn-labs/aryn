import * as Primitive from '@radix-ui/react-tabs'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'
export const Tabs = Primitive.Root
export const TabsContent = Primitive.Content
export function TabsList({ className, ...props }: ComponentProps<typeof Primitive.List>) {
  return <Primitive.List className={cn('tabs-list', className)} {...props} />
}
export function TabsTrigger({ className, ...props }: ComponentProps<typeof Primitive.Trigger>) {
  return <Primitive.Trigger className={cn('tabs-trigger', className)} {...props} />
}
