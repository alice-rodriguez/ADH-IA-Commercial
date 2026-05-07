import { useEffect, useState } from 'react'
import { fetchOffres } from './api'
import OffreCard from './components/OffreCard'
import type { Offre } from './types'

function App() {
  const [offres, setOffres] = useState<Offre[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchOffres()
      .then(setOffres)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      <header className="bg-adh-black flex items-center gap-4 px-6 py-4">
        <img src="/picto-adh.png" alt="Pictogramme ADH" className="h-10" />
        <img src="/logo-adh.png" alt="Logo ADH" className="h-8" />
      </header>

      <main className="flex-1 p-6 md:p-8">
        {loading && (
          <p className="text-center text-gray-400 mt-16 text-lg">Chargement des offres...</p>
        )}

        {!loading && error && (
          <div className="max-w-lg mx-auto mt-16 text-center">
            <p className="text-red-500 font-medium mb-2">Impossible de charger les offres</p>
            <p className="text-gray-500 text-sm mb-1">{error}</p>
            <p className="text-gray-400 text-sm">
              Vérifiez que le backend est lancé :{' '}
              <span className="font-mono">http://localhost:8000/health</span>
            </p>
          </div>
        )}

        {!loading && !error && offres.length === 0 && (
          <p className="text-center text-gray-400 mt-16 text-lg">Aucune offre disponible pour le moment</p>
        )}

        {!loading && !error && offres.length > 0 && (
          <>
            <h2 className="text-lg font-semibold text-adh-black mb-6">
              {offres.length} offre{offres.length > 1 ? 's' : ''} collectée{offres.length > 1 ? 's' : ''}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {offres.map((offre) => (
                <OffreCard key={offre.id} offre={offre} />
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  )
}

export default App
