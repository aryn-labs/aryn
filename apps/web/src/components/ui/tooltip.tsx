import * as Primitive from '@radix-ui/react-tooltip'
import type { ReactNode } from 'react'
export const TooltipProvider = Primitive.Provider
export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Primitive.Root>
      <Primitive.Trigger asChild>{children}</Primitive.Trigger>
      <Primitive.Portal>
        <Primitive.Content className="tooltip-content" side="right" sideOffset={8}>
          {label}
          <Primitive.Arrow />
        </Primitive.Content>
      </Primitive.Portal>
    </Primitive.Root>
  )
}
