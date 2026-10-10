import { Sparkles } from 'lucide-react'
export function GettingStarted() {
  return (
    <section className="home-section" aria-labelledby="getting-started-heading">
      <div className="home-section-heading">
        <h2 id="getting-started-heading">Getting Started</h2>
        <p>Your project is ready for its first definition.</p>
      </div>
      <div className="home-panel home-start">
        <Sparkles size={23} aria-hidden="true" />
        <div>
          <h3>Start with one clear job</h3>
          <p>
            Describe the work, choose an agent or workflow, then review the expected output and any
            integration needs.
          </p>
          <ol>
            <li>Shape your starting brief.</li>
            <li>Review the definition in its builder.</li>
            <li>Evaluate and obtain required approvals before publishing or running.</li>
          </ol>
        </div>
      </div>
    </section>
  )
}
