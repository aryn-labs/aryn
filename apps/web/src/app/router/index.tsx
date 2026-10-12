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
import { WorkflowCatalog } from '@/features/workflows/WorkflowCatalog'
import { WorkflowEditor } from '@/features/workflows/WorkflowEditor'
import { RunsPage } from '@/features/runs/RunsPage'
import { AutomationsPage } from '@/features/automations/AutomationsPage'
import { AutomationBuilder } from '@/features/automations/AutomationBuilder'
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
  .filter(
    (item) =>
      !['/', '/projects', '/agents', '/workflows', '/runs', '/automations'].includes(item.path),
  )
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
const workflows = createRoute({
  getParentRoute: () => dashboard,
  path: '/workflows',
  component: WorkflowCatalog,
})
const workflowEditor = createRoute({
  getParentRoute: () => studio,
  path: '/workflows/$projectId/$workflowId',
  component: WorkflowEditor,
  validateSearch: (value: Record<string, unknown>): { run?: string } => ({
    run:
      typeof value.run === 'string' && /^workflow_run_[a-zA-Z0-9_-]{1,64}$/.test(value.run)
        ? value.run
        : undefined,
  }),
})
const identifier = (value: unknown) =>
  typeof value === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(value) ? value : undefined
const runs = createRoute({
  getParentRoute: () => dashboard,
  path: '/runs',
  component: RunsPage,
  validateSearch: (
    value: Record<string, unknown>,
  ): { project?: string; run?: string; runKind?: 'agent' | 'workflow' } => ({
    project: identifier(value.project),
    run: identifier(value.run),
    runKind:
      value.runKind === 'workflow' ? 'workflow' : value.runKind === 'agent' ? 'agent' : undefined,
  }),
})
const automations = createRoute({
  getParentRoute: () => dashboard,
  path: '/automations',
  component: AutomationsPage,
  validateSearch: (value: Record<string, unknown>): { project?: string; automation?: string } => ({
    project: identifier(value.project),
    automation: identifier(value.automation),
  }),
})
const automationBuilder = createRoute({
  getParentRoute: () => dashboard,
  path: '/automations/new',
  component: AutomationBuilder,
  validateSearch: (value: Record<string, unknown>): { project?: string; edit?: string } => ({
    project: identifier(value.project),
    edit: identifier(value.edit),
  }),
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
  dashboard.addChildren([
    home,
    chat,
    projects,
    agents,
    workflows,
    runs,
    automations,
    automationBuilder,
    ...projectRoutes,
    ...routes,
  ]),
  studio.addChildren([agentEditor, workflowEditor]),
])
export function createAppRouter(history: RouterHistory = createBrowserHistory()) {
  return createRouter({ routeTree: tree, history, defaultPreload: 'intent' })
}
declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof createAppRouter>
  }
}
