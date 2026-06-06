import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Analytics } from '@vercel/analytics/react'
import Sidebar from './components/Sidebar'
import Dashboard from './components/dashboard/Dashboard'
import Bullpen from './components/bullpen/Bullpen'
import Prospects from './components/prospects/Prospects'
import Methodology from './components/methodology/Methodology'
import DataTrust from './components/trust/DataTrust'

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell bg-noise flex-col lg:flex-row">
        <Sidebar />
        <main className="flex-1 min-w-0">
          <Routes>
            <Route path="/"            element={<Dashboard />} />
            <Route path="/bullpen"     element={<Bullpen />} />
            <Route path="/prospects"   element={<Prospects />} />
            <Route path="/methodology" element={<Methodology />} />
            <Route path="/trust"       element={<DataTrust />} />
          </Routes>
        </main>
      </div>
      <Analytics />
    </BrowserRouter>
  )
}