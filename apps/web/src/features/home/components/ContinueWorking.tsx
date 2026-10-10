import { HomeResourceRow } from './HomeResourceRow'
import type { HomeResource } from '../lib/home-state'
import { ApiError } from '@/lib/api/client'
export function ContinueWorking({
  agents,
  workflows,
  onOpen,
  workflowsError,
}: {
  agents: HomeResource[]
  workflows: HomeResource[]
  onOpen: (item: HomeResource) => void
  workflowsError?: Error | null
}) {
  if (!agents.length && !workflows.length && !workflowsError) return null
  return (
    <section className="home-section" aria-labelledby="continue-heading">
      <div className="home-section-heading">
        <h2 id="continue-heading">Continue Working</h2>
        <p>Pick up a definition or inspect your recent work.</p>
      </div>
      <div className="home-columns">
        <section className="home-panel" aria-labelledby="agents-heading">
          <div className="home-panel-heading">
            <h3 id="agents-heading">Your Agents</h3>
            <p>Recent agent definitions in this project</p>
          </div>
          {agents.length ? (
            agents.map((item) => <HomeResourceRow key={item.id} item={item} onOpen={onOpen} />)
          ) : (
            <p className="home-list-empty">No agent definitions yet.</p>
          )}
        </section>
        <section className="home-panel" aria-labelledby="workflows-heading">
          <div className="home-panel-heading">
            <h3 id="workflows-heading">Your Workflows</h3>
            <p>Latest workflow definitions</p>
          </div>
          {workflowsError ? (
            <p className="home-list-empty" role="status">
              {workflowsError instanceof ApiError && [404, 501].includes(workflowsError.status)
                ? 'Workflow definitions are unavailable on this server.'
                : 'Workflow definitions could not be loaded.'}
            </p>
          ) : workflows.length ? (
            workflows.map((item) => <HomeResourceRow key={item.id} item={item} onOpen={onOpen} />)
          ) : (
            <p className="home-list-empty">No workflow definitions yet.</p>
          )}
        </section>
      </div>
    </section>
  )
}
