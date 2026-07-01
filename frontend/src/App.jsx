import { useEffect } from 'react'
import { BrowserRouter, Navigate, Routes, Route } from 'react-router-dom'
import { Analytics } from '@vercel/analytics/react'
import Sidebar from './components/Sidebar'
import Footer from './components/layout/Footer'
import Home from './components/home/Home'
import Stories from './components/stories/Stories'
import Dashboard from './components/dashboard/Dashboard'
import Bullpen from './components/bullpen/Bullpen'
import About from './components/about/About'
import HowToRead from './components/guide/HowToRead'
import Methodology from './components/methodology/Methodology'
import DataTrust from './components/trust/DataTrust'
import PrivatePosts from './components/posts/PrivatePosts'
import SignIn from './components/auth/SignIn'
import VerifySignIn from './components/auth/VerifySignIn'
import ProductIntelligenceAdmin from './components/admin/ProductIntelligenceAdmin'
import { PRIVATE_POSTS_PATH } from './components/posts/privatePostsView'
import { ADMIN_PRODUCT_EVENTS_PATH } from './utils/adminProductEvents'
import { cleanupLaunchPreferredTeamStorage } from './utils/preferredTeam'

export const APP_ROUTES = [
  { path: '/', Component: Home },
  { path: '/today', redirectTo: '/' },
  { path: '/dashboard', Component: Dashboard },
  { path: '/bullpen', Component: Bullpen },
  { path: '/stories', Component: Stories },
  { path: '/about', Component: About },
  { path: '/how-to-read', Component: HowToRead },
  { path: '/methodology', Component: Methodology },
  { path: '/trust', Component: DataTrust },
  { path: '/signin', Component: SignIn },
  { path: '/auth/verify', Component: VerifySignIn },
  { path: ADMIN_PRODUCT_EVENTS_PATH, Component: ProductIntelligenceAdmin },
  { path: PRIVATE_POSTS_PATH, Component: PrivatePosts },
  { path: '*', redirectTo: '/' },
]

export function AppRoutes() {
  return (
    <Routes>
      {APP_ROUTES.map(({ path, Component, redirectTo }) => (
        <Route
          key={path}
          path={path}
          element={redirectTo ? <Navigate to={redirectTo} replace /> : <Component />}
        />
      ))}
    </Routes>
  )
}

export default function App() {
  useEffect(() => {
    cleanupLaunchPreferredTeamStorage()
  }, [])

  return (
    <BrowserRouter>
      <div className="app-shell bg-noise flex-col lg:flex-row">
        <Sidebar />
        <main className="flex-1 min-w-0 lg:ml-56">
          <AppRoutes />
          <Footer />
        </main>
      </div>
      <Analytics />
    </BrowserRouter>
  )
}
