import { Folder } from 'lucide-react'
export function HomeHeader({ projectName }: { projectName?: string }) {
  return (
    <div className="home-header">
      <p className="home-kicker">
        <Folder size={13} aria-hidden="true" />
        <span>{projectName ?? 'Home'}</span>
      </p>
      <h1>Your workspace</h1>
      <p>A clear place to build, continue, and manage your agent work.</p>
    </div>
  )
}
