import { BrowserRouter, Navigate, Routes, Route } from 'react-router-dom'
import { Analytics } from '@vercel/analytics/react'
import Sidebar from './components/Sidebar'
import Home from './components/home/Home'
import Stories from './components/stories/Stories'
import Dashboard from './components/dashboard/Dashboard'
import Bullpen from './components/bullpen/Bullpen'
import Prospects from './components/prospects/Prospects'
import Methodology from './components/methodology/Methodology'
import DataTrust from './components/trust/DataTrust'
import PrivatePosts from './components/posts/PrivatePosts'
import { PRIVATE_POSTS_PATH } from './components/posts/privatePostsView'

export const APP_ROUTES = [
  { path: '/', Component: Home },
  { path: '/today', redirectTo: '/' },
  { path: '/stories', Component: Stories },
  { path: '/dashboard', Component: Dashboard },
  { path: '/bullpen', Component: Bullpen },
  { path: '/prospects', Component: Prospects },
  { path: '/methodology', Component: Methodology },
  { path: '/trust', Component: DataTrust },
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
  return (
    <BrowserRouter>
      <div className="app-shell bg-noise flex-col lg:flex-row">
        <Sidebar />
        <main className="flex-1 min-w-0">
          <AppRoutes />
        </main>
      </div>
      <Analytics />
    </BrowserRouter>
  )
}
