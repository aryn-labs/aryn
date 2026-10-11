import { act, fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import i18n, { labelText } from '@/i18n'
import { HomeComposer } from '../components/HomeComposer'
import { greetingPeriod } from '../lib/home-state'

it('sends trimmed input with Enter but preserves Shift+Enter and IME composition', async () => {
  const onContinue = vi.fn()
  const change = vi.fn()
  const { rerender } = render(
    <HomeComposer compact value="  Hello  " onChange={change} onContinue={onContinue} />,
  )
  const input = screen.getByRole('textbox', { name: 'Message to ARYN' })
  fireEvent.keyDown(input, { key: 'Enter', shiftKey: true })
  fireEvent.keyDown(input, { key: 'Enter', isComposing: true })
  fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 })
  expect(onContinue).not.toHaveBeenCalled()
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(onContinue).toHaveBeenCalledExactlyOnceWith('Hello')
  rerender(<HomeComposer compact pending value="Hello" onChange={change} onContinue={onContinue} />)
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(onContinue).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button', { name: 'Sending…' })).toBeDisabled()
})

it('does not send blank input and exposes a concise disabled reason', async () => {
  const send = vi.fn()
  render(
    <HomeComposer
      compact
      value=" "
      onChange={vi.fn()}
      onContinue={send}
      disabled
      help="Model unavailable"
    />,
  )
  expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled()
  expect(screen.getByText('Model unavailable')).toBeInTheDocument()
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' })
  expect(send).not.toHaveBeenCalled()
})

it.each([
  [4, 'night'],
  [5, 'morning'],
  [10, 'morning'],
  [11, 'noon'],
  [14, 'noon'],
  [15, 'afternoon'],
  [18, 'afternoon'],
  [19, 'night'],
  [23, 'night'],
] as const)('uses local hour %i for %s', (hour, period) => {
  expect(greetingPeriod(hour)).toBe(period)
})

it('updates composer language without clearing user content', async () => {
  render(<HomeComposer compact value="Pesan pribadi" onChange={vi.fn()} onContinue={vi.fn()} />)
  await act(() => i18n.changeLanguage('id-ID'))
  expect(await screen.findByPlaceholderText('Tulis pesan Anda...')).toHaveValue('Pesan pribadi')
  expect(screen.getByRole('button', { name: 'Kirim pesan' })).toBeEnabled()
  expect(labelText('Workspace')).toBe('Ruang kerja')
  expect(labelText('Intelligence')).toBe('Kecerdasan')
  await act(() => i18n.changeLanguage('en-US'))
  expect(labelText('Workspace')).toBe('Workspace')
  expect(labelText('Intelligence')).toBe('Intelligence')
})
