import * as Primitive from '@radix-ui/react-dropdown-menu'
import type { ComponentProps } from 'react'
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'
export const DropdownMenu = Primitive.Root
export const DropdownMenuTrigger = Primitive.Trigger
export const DropdownMenuSeparator = Primitive.Separator
export const DropdownMenuLabel = Primitive.Label
export const DropdownMenuRadioGroup = Primitive.RadioGroup
export function DropdownMenuContent({
  className,
  sideOffset = 6,
  ...props
}: ComponentProps<typeof Primitive.Content>) {
  return (
    <Primitive.Portal>
      <Primitive.Content
        sideOffset={sideOffset}
        collisionPadding={12}
        className={cn('dropdown-content', className)}
        {...props}
      />
    </Primitive.Portal>
  )
}
export function DropdownMenuItem({ className, ...props }: ComponentProps<typeof Primitive.Item>) {
  return <Primitive.Item className={cn('dropdown-item', className)} {...props} />
}
export function DropdownMenuRadioItem({
  className,
  children,
  ...props
}: ComponentProps<typeof Primitive.RadioItem>) {
  return (
    <Primitive.RadioItem className={cn('dropdown-item', className)} {...props}>
      {children}
      <Primitive.ItemIndicator className="dropdown-indicator">
        <Check size={15} aria-hidden="true" />
      </Primitive.ItemIndicator>
    </Primitive.RadioItem>
  )
}
