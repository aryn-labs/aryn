import { translate as tr } from '@/i18n'
import { Component, type ReactNode } from 'react'
import { DataState } from './DataState'
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? (
      <DataState
        kind="error"
        title={tr('ui.studio_could_not_render_this_view')}
        description={tr('ui.reload_to_recover_your_workspace')}
        retry={() => window.location.reload()}
      />
    ) : (
      this.props.children
    )
  }
}
