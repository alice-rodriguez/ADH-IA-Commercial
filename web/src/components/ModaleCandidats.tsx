import { useEffect, useRef, useState } from 'react'
import type { Candidat } from '../api'
import { fetchCandidats } from '../api'

const SEUILS = [30, 40, 50, 60]

function scoreBarClass(score: number): string {
  if (score >= 80) return 'bg-green-700'
  if (score >= 60) return 'bg-green-500'
  if (score >= 40) return 'bg-adh-orange'
  return 'bg-gray-400'
}

function scoreTextClass(score: number): string {
  if (score >= 80) return 'text-green-700'
  if (score >= 60) return 'text-green-500'
  if (score >= 40) return 'text-adh-orange'
  return 'text-gray-400'
}

interface BarreScoreProps {
  label: string
  score: number
  info?: string
}

function BarreScore({ label, score, info }: BarreScoreProps) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-gray-600 w-28 shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${scoreBarClass(score)}`}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className={`font-semibold w-8 text-right shrink-0 ${scoreTextClass(score)}`}>
        {score}%
      </span>
      {info && <span className="text-gray-400 shrink-0">{info}</span>}
    </div>
  )
}

interface Props {
  offreId: number
  titreOffre: string
  onClose: () => void
}

export default function ModaleCandidats({ offreId, titreOffre, onClose }: Props) {
  const [candidats, setCandidats] = useState<Candidat[]>([])
  const [loading, setLoading] = useState(true)
  const [seuilAffichage, setSeuilAffichage] = useState(40)
  const [candidatExpanded, setCandidatExpanded] = useState<number | null>(null)
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchCandidats(offreId)
      .then(setCandidats)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [offreId])

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === overlayRef.current) onClose()
  }

  function toggleExpand(cvId: number) {
    setCandidatExpanded((prev) => (prev === cvId ? null : cvId))
  }

  const candidatsFiltres = candidats.filter((c) => c.score_global >= seuilAffichage)

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 bg-black/50 z-50 overflow-y-auto"
    >
      <div className="max-w-2xl mx-auto mt-20 mb-10 bg-white rounded-lg shadow-xl p-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h2 className="text-lg font-bold text-adh-black">Candidats compatibles</h2>
            <p className="text-sm text-gray-500 italic mt-0.5">{titreOffre}</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-adh-black text-xl leading-none mt-0.5 shrink-0"
            title="Fermer"
          >
            ✕
          </button>
        </div>

        {/* Seuils */}
        <div className="flex items-center gap-2 mb-5">
          <span className="text-xs text-gray-500">Seuil :</span>
          {SEUILS.map((s) => (
            <button
              key={s}
              onClick={() => setSeuilAffichage(s)}
              className={`text-xs font-semibold px-3 py-1 rounded-full border transition-colors ${
                seuilAffichage === s
                  ? 'bg-adh-orange text-white border-adh-orange'
                  : 'bg-white text-gray-600 border-gray-300 hover:border-adh-orange hover:text-adh-orange'
              }`}
            >
              {s}%
            </button>
          ))}
        </div>

        {/* Contenu */}
        {loading ? (
          <p className="text-center text-gray-400 py-8">Chargement...</p>
        ) : candidatsFiltres.length === 0 ? (
          <p className="text-center text-gray-400 py-8">
            Aucun candidat avec score ≥ {seuilAffichage}%
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {candidatsFiltres.map((c) => {
              const expanded = candidatExpanded === c.cv_id
              let compInfo: string | undefined
              if (c.details_json) {
                try {
                  const d = JSON.parse(c.details_json)
                  if (d.nb_competences_cv) {
                    const trouvees = Math.round(c.score_competences * d.nb_competences_cv / 100)
                    compInfo = `(${trouvees}/${d.nb_competences_cv})`
                  }
                } catch { /* ignore */ }
              }
              return (
                <div key={c.cv_id} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-2xl font-bold leading-none ${scoreTextClass(c.score_global)}`}>
                          {c.score_global}%
                        </span>
                        {c.nom_candidat && (
                          <span className="font-semibold text-adh-black text-sm">{c.nom_candidat}</span>
                        )}
                      </div>
                      {c.titre_courant && (
                        <p className="text-xs text-gray-500 mt-0.5">{c.titre_courant}</p>
                      )}
                      <div className="flex gap-3 text-xs text-gray-400 mt-0.5">
                        {c.annees_experience !== null && (
                          <span>{c.annees_experience} ans d'exp.</span>
                        )}
                        {c.localisation_preferee && <span>{c.localisation_preferee}</span>}
                      </div>
                    </div>
                    <button
                      onClick={() => toggleExpand(c.cv_id)}
                      className="text-xs text-gray-500 hover:text-adh-orange shrink-0 border border-gray-200 rounded px-2 py-1 hover:border-adh-orange transition-colors"
                    >
                      {expanded ? 'Masquer ▲' : 'Détail du score ▼'}
                    </button>
                  </div>

                  {expanded && (
                    <div className="mt-3 pt-3 border-t border-gray-100 flex flex-col gap-2">
                      <BarreScore label="Compétences" score={c.score_competences} info={compInfo} />
                      <BarreScore label="Domaine"     score={c.score_domaine} />
                      <BarreScore label="Expérience"  score={c.score_experience} />
                      <BarreScore label="Contrat"     score={c.score_contrat} />
                      <BarreScore label="Lieu"        score={c.score_lieu} />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
