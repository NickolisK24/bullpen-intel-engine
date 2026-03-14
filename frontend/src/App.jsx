import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './components/dashboard/Dashboard'
import Bullpen from './components/bullpen/Bullpen'
import Prospects from './components/prospects/Prospects'
import Portfolio from './components/portfolio/Portfolio'

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell bg-noise">
        <Sidebar />
        <main className="flex-1 min-w-0 overflow-y-auto">
          <Routes>
            <Route path="/"          element={<Dashboard />} />
            <Route path="/bullpen"   element={<Bullpen />} />
            <Route path="/prospects" element={<Prospects />} />
            <Route path="/portfolio" element={<Portfolio />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
