import { useState } from 'react'
import PageCandidats from './pages/PageCandidats'
import PageOffres from './pages/PageOffres'

type Page = 'offres' | 'candidats'

function App() {
  const [page, setPage] = useState<Page>('offres')

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
        </nav>
      </header>

      {page === 'offres' && <PageOffres />}
      {page === 'candidats' && <PageCandidats />}
    </div>
  )
}

export default App
