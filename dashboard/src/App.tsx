import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Repositories from './pages/Repositories'
import RepoDetail from './pages/RepoDetail'
import ReviewDetail from './pages/ReviewDetail'
import Analytics from './pages/Analytics'
import Settings from './pages/Settings'
import Login from './pages/Login'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/repos" element={<Repositories />} />
        <Route path="/repos/:repoId" element={<RepoDetail />} />
        <Route path="/repos/:repoId/reviews/:prId" element={<ReviewDetail />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}
