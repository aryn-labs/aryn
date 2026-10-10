import {
  createRootRoute,
  createRoute,
  createRouter,
  createBrowserHistory,
  type RouterHistory,
} from '@tanstack/react-router'
import { AppShell } from '@/app/shell/AppShell'
import { HomePage } from '@/features/home/HomePage'
import { navigation } from '@/components/navigation/items'
import { FeatureScaffold, NotFound } from './pages'
const root = createRootRoute({ component: AppShell, notFoundComponent: NotFound })
const home = createRoute({ getParentRoute: () => root, path: '/', component: HomePage })
const routes = navigation
  .filter((item) => item.path !== '/')
  .map((item) =>
    createRoute({
      getParentRoute: () => root,
      path: item.path,
      component: () => <FeatureScaffold title={item.label} />,
    }),
  )
const tree = root.addChildren([home, ...routes])
export function createAppRouter(history: RouterHistory = createBrowserHistory()) {
  return createRouter({ routeTree: tree, history, defaultPreload: 'intent' })
}
declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof createAppRouter>
  }
}
