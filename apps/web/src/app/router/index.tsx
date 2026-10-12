import {
  createRootRoute,
  createRoute,
  createRouter,
  createBrowserHistory,
  type RouterHistory,
} from '@tanstack/react-router'
import { AppShell } from '@/app/shell/AppShell'
import { StudioShell } from '@/app/studio/StudioShell'
import { RootLayout } from './RootLayout'
import { ChatPage } from '@/features/chat/ChatPage'
import { HomePage } from '@/features/home/HomePage'
import { ProjectsPage } from '@/features/projects/ProjectsPage'
import { ProjectWorkspace } from '@/features/projects/ProjectWorkspace'
import { AgentCatalog } from '@/features/agents/AgentCatalog'
import { AgentEditor } from '@/features/agents/AgentEditor'
import { navigation } from '@/components/navigation/items'
import { FeatureScaffold, NotFound } from './pages'
const root = createRootRoute({
  component: RootLayout,
  notFoundComponent: () => (
    <AppShell>
      <NotFound />
    </AppShell>
  ),
})
const dashboard = createRoute({ getParentRoute: () => root, id: 'dashboard', component: AppShell })
const studio = createRoute({ getParentRoute: () => root, id: 'studio', component: StudioShell })
const home = createRoute({ getParentRoute: () => dashboard, path: '/', component: HomePage })
const routes = navigation
  .filter((item) => item.path !== '/' && item.path !== '/projects' && item.path !== '/agents')
  .map((item) =>
    createRoute({
      getParentRoute: () => dashboard,
      path: item.path,
      component: () => <FeatureScaffold title={item.label} />,
    }),
  )
const chat = createRoute({
  getParentRoute: () => dashboard,
  path: '/chat/$conversationId',
  component: ChatPage,
})
const projects = createRoute({
  getParentRoute: () => dashboard,
  path: '/projects',
  component: ProjectsPage,
})
const agents = createRoute({
  getParentRoute: () => dashboard,
  path: '/agents',
  component: AgentCatalog,
})
const agentEditor = createRoute({
  getParentRoute: () => studio,
  path: '/agents/$projectId/$blueprintId',
  component: AgentEditor,
})
const validateProjectSearch = (value: Record<string, unknown>): { selection?: string } => ({
  selection:
    typeof value.selection === 'string' && value.selection.length <= 100
      ? value.selection
      : undefined,
})
const projectDetail = createRoute({
  getParentRoute: () => dashboard,
  path: '/projects/$projectId',
  component: ProjectWorkspace,
  validateSearch: validateProjectSearch,
})
const projectWork = createRoute({
  getParentRoute: () => dashboard,
  path: '/projects/$projectId/work',
  component: ProjectWorkspace,
  validateSearch: validateProjectSearch,
})
const projectTeam = createRoute({
  getParentRoute: () => dashboard,
  path: '/projects/$projectId/team',
  component: ProjectWorkspace,
  validateSearch: validateProjectSearch,
})
const projectResults = createRoute({
  getParentRoute: () => dashboard,
  path: '/projects/$projectId/results',
  component: ProjectWorkspace,
  validateSearch: validateProjectSearch,
})
const projectActivity = createRoute({
  getParentRoute: () => dashboard,
  path: '/projects/$projectId/activity',
  component: ProjectWorkspace,
  validateSearch: validateProjectSearch,
})
const projectRoutes = [
  projectDetail,
  projectWork,
  projectTeam,
  projectResults,
  projectActivity,
] as const
const tree = root.addChildren([
  dashboard.addChildren([home, chat, projects, agents, ...projectRoutes, ...routes]),
  studio.addChildren([agentEditor]),
])
export function createAppRouter(history: RouterHistory = createBrowserHistory()) {
  return createRouter({ routeTree: tree, history, defaultPreload: 'intent' })
}
declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof createAppRouter>
  }
}
