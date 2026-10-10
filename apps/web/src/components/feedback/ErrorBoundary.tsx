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
        title="Studio could not render this view"
        description="Reload to recover your workspace."
        retry={() => window.location.reload()}
      />
    ) : (
      this.props.children
    )
  }
}
