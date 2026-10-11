import {
  createRootRoute,
  createRoute,
  createRouter,
  createBrowserHistory,
  type RouterHistory,
} from '@tanstack/react-router'
import { AppShell } from '@/app/shell/AppShell'
import { ChatPage } from '@/features/chat/ChatPage'
import { HomePage } from '@/features/home/HomePage'
import { ProjectsPage } from '@/features/projects/ProjectsPage'
import { ProjectWorkspace } from '@/features/projects/ProjectWorkspace'
import { navigation } from '@/components/navigation/items'
import { FeatureScaffold, NotFound } from './pages'
const root = createRootRoute({ component: AppShell, notFoundComponent: NotFound })
const home = createRoute({ getParentRoute: () => root, path: '/', component: HomePage })
const routes = navigation
  .filter((item) => item.path !== '/' && item.path !== '/projects')
  .map((item) =>
    createRoute({
      getParentRoute: () => root,
      path: item.path,
      component: () => <FeatureScaffold title={item.label} />,
    }),
  )
const chat = createRoute({
  getParentRoute: () => root,
  path: '/chat/$conversationId',
  component: ChatPage,
})
const projects = createRoute({
  getParentRoute: () => root,
  path: '/projects',
  component: ProjectsPage,
})
const validateProjectSearch = (value: Record<string, unknown>): { selection?: string } => ({
  selection:
    typeof value.selection === 'string' && value.selection.length <= 100
      ? value.selection
      : undefined,
})
const projectDetail = createRoute({
  getParentRoute: () => root,
  path: '/projects/$projectId',
  component: ProjectWorkspace,
  validateSearch: validateProjectSearch,
})
const projectWork = createRoute({
  getParentRoute: () => root,
  path: '/projects/$projectId/work',
  component: ProjectWorkspace,
  validateSearch: validateProjectSearch,
})
const projectTeam = createRoute({
  getParentRoute: () => root,
  path: '/projects/$projectId/team',
  component: ProjectWorkspace,
  validateSearch: validateProjectSearch,
})
const projectResults = createRoute({
  getParentRoute: () => root,
  path: '/projects/$projectId/results',
  component: ProjectWorkspace,
  validateSearch: validateProjectSearch,
})
const projectActivity = createRoute({
  getParentRoute: () => root,
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
const tree = root.addChildren([home, chat, projects, ...projectRoutes, ...routes])
export function createAppRouter(history: RouterHistory = createBrowserHistory()) {
  return createRouter({ routeTree: tree, history, defaultPreload: 'intent' })
}
declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof createAppRouter>
  }
}
