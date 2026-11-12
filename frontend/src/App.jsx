import { Link, NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import { useSocketEvents } from './context/SocketContext'
import { ConnectionBadge, Loading } from './components/ui'
import { LoginPage, SignupPage } from './pages/AuthPages'
import Dashboard from './pages/Dashboard'
import Projects from './pages/Projects'
import ProjectPage from './pages/ProjectPage'
import Assigned from './pages/Assigned'

function Layout({ children }) {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  // If I'm removed from / my project is deleted while I'm on its page, bounce to the project list.
  useSocketEvents((e) => {
    if ((e.type === 'project.removed' || e.type === 'project.deleted') && location.pathname.startsWith(`/projects/${e.project_id}`)) {
      nav('/projects')
    }
  })
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">TaskFlow</Link>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/projects">Projects</NavLink>
          <NavLink to="/assigned">Assigned to me</NavLink>
        </nav>
        <div className="spacer" />
        <ConnectionBadge />
        <span className="who">{user.name}</span>
        <button className="btn" onClick={logout}>Log out</button>
      </header>
      <main className="container">{children}</main>
    </>
  )
}

function Protected({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <Loading label="Restoring session…" />
  if (!user) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

function Guest({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <Loading />
  return user ? <Navigate to="/" replace /> : children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Guest><LoginPage /></Guest>} />
      <Route path="/signup" element={<Guest><SignupPage /></Guest>} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/projects" element={<Protected><Projects /></Protected>} />
      <Route path="/projects/:id" element={<Protected><ProjectPage /></Protected>} />
      <Route path="/assigned" element={<Protected><Assigned /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
