import { useEffect, useState } from 'react'
import { AuthProvider, useAuth } from './auth/AuthContext'
import PageCandidats from './pages/PageCandidats'
import PageLogin from './pages/PageLogin'
import PageOffres from './pages/PageOffres'
import PageUsers from './pages/PageUsers'

type Page = 'login' | 'offres' | 'candidats' | 'users'

function AppInner() {
  const { user, isLoading, logout } = useAuth()
  const [page, setPage] = useState<Page>('offres')

  useEffect(() => {
    if (!isLoading && !user) setPage('login')
    if (!isLoading && user && page === 'login') setPage('offres')
  }, [isLoading, user])

  if (isLoading) {
    return (
      <div className="min-h-screen bg-adh-black flex items-center justify-center">
        <div className="text-white text-sm">Chargement…</div>
      </div>
    )
  }

  if (page === 'login') {
    return <PageLogin onLoggedIn={() => setPage('offres')} />
  }

  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      <header className="bg-adh-black flex items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-center gap-4">
          <img src="/picto-adh.png" alt="Pictogramme ADH" className="h-10" />
          <img src="/logo-adh.png" alt="Logo ADH" className="h-8" />
        </div>
        <nav className="flex items-center gap-6">
          <button
            onClick={() => setPage('offres')}
            className={page === 'offres' ? 'text-adh-orange font-semibold' : 'text-white hover:text-adh-orange transition-colors'}
          >
            Offres
          </button>
          <button
            onClick={() => setPage('candidats')}
            className={page === 'candidats' ? 'text-adh-orange font-semibold' : 'text-white hover:text-adh-orange transition-colors'}
          >
            Candidats
          </button>
          <button
            onClick={() => setPage('users')}
            className={page === 'users' ? 'text-adh-orange font-semibold' : 'text-white hover:text-adh-orange transition-colors'}
          >
            Utilisateurs
          </button>
        </nav>
        <div className="flex items-center gap-3">
          <span className="text-gray-400 text-sm">{user?.username}</span>
          <button
            onClick={logout}
            className="text-white text-sm border border-white/30 rounded-lg px-3 py-1 hover:bg-white/10 transition-colors"
          >
            Déconnexion
          </button>
        </div>
      </header>

      {page === 'offres' && <PageOffres />}
      {page === 'candidats' && <PageCandidats />}
      {page === 'users' && <PageUsers />}
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  )
}

export default App
