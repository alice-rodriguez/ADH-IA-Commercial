import { useEffect, useState } from 'react'
import type { CV } from '../api'
import { fetchCVs } from '../api'
import EditeurNotesAdh from '../components/EditeurNotesAdh'
import ModaleAjoutCv from '../components/ModaleAjoutCv'
import ModaleOffres from '../components/ModaleOffres'

const STATUT_BADGE: Record<string, string> = {
  actif:    'bg-green-100 text-green-700',
  en_pause: 'bg-gray-100 text-gray-600',
  place:    'bg-blue-100 text-blue-700',
  inactif:  'bg-red-100 text-red-700',
}

const STATUT_LABEL: Record<string, string> = {
  actif:    'Actif',
  en_pause: 'En pause',
  place:    'Placé',
  inactif:  'Inactif',
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`
}

export default function PageCandidats() {
  const [cvs, setCvs] = useState<CV[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [cvSelectionneId, setCvSelectionneId] = useState<number | null>(null)
  const [modaleAjoutOuverte, setModaleAjoutOuverte] = useState(false)
  const [modaleOffresCv, setModaleOffresCv] = useState<{ cvId: number; nom: string } | null>(null)

  useEffect(() => {
    fetchCVs()
      .then(setCvs)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  function handleSauvegarde(updated: CV) {
    setCvs((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
    setCvSelectionneId(null)
  }

  async function handleCvAjoute(cvId: number) {
    const nouvelleListe = await fetchCVs().catch(() => cvs)
    setCvs(nouvelleListe)
    setModaleAjoutOuverte(false)
    setCvSelectionneId(cvId)
  }

  const statut = (cv: CV) => cv.statut_relation ?? 'actif'

  return (
    <>
    <main className="flex-1 p-6 md:p-8">
      {/* En-tête de page */}
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-adh-black">
            Mes candidats — {cvs.length} CV{cvs.length > 1 ? 's' : ''}
          </h1>
          {!loading && cvs.length > 0 && (
            <p className="text-sm text-gray-500 mt-1">
              Cliquez sur une ligne pour éditer le profil ADH
            </p>
          )}
        </div>
        <button
          onClick={() => setModaleAjoutOuverte(true)}
          className="bg-adh-orange text-white text-sm font-semibold px-4 py-2 rounded hover:opacity-90 shrink-0"
        >
          + Ajouter un candidat
        </button>
      </div>

      {loading && (
        <p className="text-center text-gray-400 mt-16 text-lg">Chargement des candidats...</p>
      )}

      {!loading && error && (
        <div className="max-w-lg mx-auto mt-16 text-center">
          <p className="text-red-500 font-medium mb-2">Impossible de charger les candidats</p>
          <p className="text-gray-500 text-sm">{error}</p>
        </div>
      )}

      {!loading && !error && cvs.length === 0 && (
        <div className="max-w-lg mx-auto mt-16 text-center">
          <p className="text-gray-400 text-lg mb-2">Aucun candidat en BDD.</p>
          <p className="text-gray-400 text-sm mb-4">
            Utilise le bouton <span className="font-semibold text-adh-orange">+ Ajouter un candidat</span> ou lance{' '}
            <span className="font-mono bg-gray-100 px-1.5 py-0.5 rounded">python -m src.cvs.scan</span>.
          </p>
        </div>
      )}

      {!loading && !error && cvs.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs font-bold uppercase text-gray-500">
              <tr>
                <th className="text-left px-4 py-3">Nom</th>
                <th className="text-left px-4 py-3">Titre</th>
                <th className="text-left px-4 py-3">Statut</th>
                <th className="text-left px-4 py-3">TJM</th>
                <th className="text-left px-4 py-3">Lieu / Mobilité</th>
                <th className="text-left px-4 py-3">Dernier contact</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {cvs.map((cv) => (
                <>
                  <tr
                    key={cv.id}
                    onClick={() => setCvSelectionneId(cv.id === cvSelectionneId ? null : cv.id)}
                    className={`hover:bg-orange-50 cursor-pointer transition-colors ${
                      cvSelectionneId === cv.id ? 'bg-orange-50' : ''
                    }`}
                  >
                    <td className="px-4 py-3 font-medium text-adh-black">
                      {cv.nom_candidat ?? cv.nom_fichier}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {cv.titre_courant ?? <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUT_BADGE[statut(cv)] ?? 'bg-gray-100 text-gray-600'}`}>
                        {STATUT_LABEL[statut(cv)] ?? statut(cv)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {cv.tjm_negocie !== null ? (
                        <span>{cv.tjm_negocie}€</span>
                      ) : cv.tjm_moyen !== null ? (
                        <span className="text-gray-400">({cv.tjm_moyen}€)</span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {cv.mobilite ? (
                        cv.mobilite
                      ) : cv.localisation_preferee ? (
                        <span className="text-gray-400">({cv.localisation_preferee})</span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {formatDate(cv.date_dernier_contact)}
                    </td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => setModaleOffresCv({ cvId: cv.id, nom: cv.nom_candidat ?? cv.nom_fichier })}
                        className="text-xs text-gray-500 hover:text-adh-orange border border-gray-200 rounded px-2 py-1 hover:border-adh-orange transition-colors whitespace-nowrap"
                      >
                        🎯 Offres compatibles
                      </button>
                    </td>
                  </tr>

                  {cvSelectionneId === cv.id && (
                    <tr key={`editor-${cv.id}`}>
                      <td colSpan={7} className="px-4 pb-4">
                        <EditeurNotesAdh
                          cv={cv}
                          mode="inline"
                          onSauvegarde={handleSauvegarde}
                          onAnnuler={() => setCvSelectionneId(null)}
                          onVoirOffres={(cvId, nom) => setModaleOffresCv({ cvId, nom })}
                        />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>

    {modaleAjoutOuverte && (
      <ModaleAjoutCv
        onClose={() => setModaleAjoutOuverte(false)}
        onCvAjoute={handleCvAjoute}
      />
    )}

    {modaleOffresCv && (
      <ModaleOffres
        cvId={modaleOffresCv.cvId}
        nomCandidat={modaleOffresCv.nom}
        onClose={() => setModaleOffresCv(null)}
      />
    )}
    </>
  )
}
