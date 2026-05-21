import { useEffect, useRef, useState } from 'react'
import type { AnalyseIA, Candidat, CV } from '../api'
import { fetchAnalyseIA, fetchCVParId, fetchCandidats, lancerAnalyseIA } from '../api'
import EditeurNotesAdh from './EditeurNotesAdh'

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

function verdictClass(verdict: string): string {
  switch (verdict) {
    case 'Excellent candidat': return 'bg-green-700 text-white'
    case 'Bon candidat':       return 'bg-green-500 text-white'
    case 'Candidat partiel':   return 'bg-adh-orange text-white'
    default:                   return 'bg-gray-400 text-white'
  }
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

type AnalyseState = AnalyseIA | 'loading' | null

export default function ModaleCandidats({ offreId, titreOffre, onClose }: Props) {
  const [candidats, setCandidats] = useState<Candidat[]>([])
  const [loading, setLoading] = useState(true)
  const [seuilAffichage, setSeuilAffichage] = useState(30)
  const [candidatExpanded, setCandidatExpanded] = useState<number | null>(null)
  const [cvProfilOuvert, setCvProfilOuvert] = useState<CV | null>(null)
  const [analysesIA, setAnalysesIA] = useState<Record<number, AnalyseState>>({})
  const [analyseExpanded, setAnalyseExpanded] = useState<number | null>(null)
  const overlayRef = useRef<HTMLDivElement>(null)

  async function fetchCVComplet(cvId: number) {
    try {
      const cv = await fetchCVParId(cvId)
      setCvProfilOuvert(cv)
    } catch (e) {
      console.error(e)
      alert('Impossible de charger le profil ADH')
    }
  }

  useEffect(() => {
    fetchCandidats(offreId)
      .then(async (candidatsData) => {
        setCandidats(candidatsData)
        const analyses = await Promise.all(
          candidatsData.map(async (c) => {
            try {
              const a = await fetchAnalyseIA(c.cv_id, offreId)
              return { cvId: c.cv_id, analyse: a }
            } catch {
              return { cvId: c.cv_id, analyse: null }
            }
          })
        )
        const map: Record<number, AnalyseIA> = {}
        analyses.forEach(({ cvId, analyse }) => {
          if (analyse) map[cvId] = analyse
        })
        setAnalysesIA(map)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [offreId])

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === overlayRef.current) onClose()
  }

  function toggleExpand(cvId: number) {
    setCandidatExpanded((prev) => (prev === cvId ? null : cvId))
  }

  function toggleAnalyse(cvId: number) {
    setAnalyseExpanded((prev) => (prev === cvId ? null : cvId))
  }

  async function chargerAnalyse(cvId: number, forcer = false) {
    setAnalysesIA((prev) => ({ ...prev, [cvId]: 'loading' }))
    try {
      let analyse: AnalyseIA | null = null
      if (!forcer) {
        analyse = await fetchAnalyseIA(cvId, offreId)
      }
      if (!analyse) {
        analyse = await lancerAnalyseIA(cvId, offreId)
      }
      setAnalysesIA((prev) => ({ ...prev, [cvId]: analyse }))
      setAnalyseExpanded(cvId)
    } catch (e) {
      console.error(e)
      setAnalysesIA((prev) => ({ ...prev, [cvId]: null }))
      alert("L'analyse IA a échoué. Vérifiez que la clé ANTHROPIC_API_KEY est configurée.")
    }
  }

  function handleAnalyseBtnClick(cvId: number) {
    const state = analysesIA[cvId]
    if (state === undefined || state === null) {
      chargerAnalyse(cvId)
    } else if (state !== 'loading') {
      toggleAnalyse(cvId)
    }
  }

  const candidatsFiltres = candidats.filter((c) => c.score_global >= seuilAffichage)

  return (
    <>
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
              const analyseState = analysesIA[c.cv_id]
              const analyseOuverte = analyseExpanded === c.cv_id
              const analyse = (analyseState !== 'loading' && analyseState !== null && analyseState !== undefined)
                ? analyseState as AnalyseIA
                : null

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
                    <div className="flex gap-2 shrink-0 flex-wrap justify-end">
                      <button
                        onClick={() => toggleExpand(c.cv_id)}
                        className="text-xs text-gray-500 hover:text-adh-orange border border-gray-200 rounded px-2 py-1 hover:border-adh-orange transition-colors"
                      >
                        {expanded ? 'Masquer ▲' : 'Détail du score ▼'}
                      </button>
                      <button
                        onClick={() => handleAnalyseBtnClick(c.cv_id)}
                        disabled={analyseState === 'loading'}
                        className={`text-xs border rounded px-2 py-1 transition-colors ${
                          analyseState === 'loading'
                            ? 'text-gray-300 border-gray-200 cursor-not-allowed'
                            : analyse
                              ? 'text-adh-violet border-adh-violet hover:bg-adh-violet hover:text-white'
                              : 'text-gray-500 hover:text-adh-violet border-gray-200 hover:border-adh-violet'
                        }`}
                      >
                        {analyseState === 'loading'
                          ? '⏳ Analyse...'
                          : analyse
                            ? (analyseOuverte ? '✨ Analyse IA ▲' : '✨ Analyse IA ▼')
                            : '✨ Analyse IA'}
                      </button>
                      <button
                        onClick={() => fetchCVComplet(c.cv_id)}
                        className="text-xs text-gray-500 hover:text-adh-orange border border-gray-200 rounded px-2 py-1 hover:border-adh-orange transition-colors"
                      >
                        👤 Profil ADH
                      </button>
                    </div>
                  </div>

                  {expanded && (
                    <div className="mt-3 pt-3 border-t border-gray-100 flex flex-col gap-2">
                      <BarreScore label="Compétences" score={c.score_competences} info={compInfo} />
                      <BarreScore label="Domaine"     score={c.score_domaine} />
                      <BarreScore label="Expérience"  score={c.score_experience} />
                      <p className="text-[11px] text-gray-400 mt-2 italic leading-snug">
                        Score pré-filtre basé sur les mots-clés. Pour une évaluation
                        métier complète, lance l'analyse IA →
                      </p>
                    </div>
                  )}

                  {analyseOuverte && analyse && (
                    <div className="mt-3 pt-3 border-t border-gray-100">
                      {/* Verdict bandeau */}
                      <div className={`rounded px-3 py-2 mb-3 flex items-center justify-between gap-3 ${verdictClass(analyse.verdict)}`}>
                        <div className="flex items-center gap-3">
                          <span className="font-bold text-sm">{analyse.verdict}</span>
                          <span className="text-lg font-bold">{analyse.score_ia}%</span>
                        </div>
                        <button
                          onClick={() => chargerAnalyse(c.cv_id, true)}
                          className="text-xs opacity-80 hover:opacity-100 border border-white/50 rounded px-2 py-0.5 transition-opacity"
                          title="Relancer l'analyse IA"
                        >
                          🔄 Relancer
                        </button>
                      </div>

                      {/* Explication */}
                      <p className="text-xs text-gray-600 mb-3 leading-relaxed">{analyse.explication}</p>

                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {/* Points forts */}
                        {analyse.points_forts.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-green-700 mb-1">Points forts</p>
                            <ul className="flex flex-col gap-1">
                              {analyse.points_forts.map((p, i) => (
                                <li key={i} className="text-xs text-gray-600 flex gap-1.5">
                                  <span className="text-green-600 shrink-0">✓</span>
                                  <span>{p}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Points faibles */}
                        {analyse.points_faibles.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-adh-orange mb-1">Points d'attention</p>
                            <ul className="flex flex-col gap-1">
                              {analyse.points_faibles.map((p, i) => (
                                <li key={i} className="text-xs text-gray-600 flex gap-1.5">
                                  <span className="text-adh-orange shrink-0">⚠️</span>
                                  <span>{p}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>

                      {/* Questions à poser */}
                      {analyse.questions_a_poser.length > 0 && (
                        <div className="mt-3">
                          <p className="text-xs font-semibold text-gray-500 mb-1">Questions à poser</p>
                          <ul className="flex flex-col gap-1">
                            {analyse.questions_a_poser.map((q, i) => (
                              <li key={i} className="text-xs text-gray-600 flex gap-1.5">
                                <span className="text-gray-400 shrink-0">•</span>
                                <span>{q}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {analyse.date_analyse && (
                        <p className="text-[10px] text-gray-300 mt-2 text-right">
                          Analysé le {new Date(analyse.date_analyse).toLocaleDateString('fr-FR')}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>

    {cvProfilOuvert && (
      <EditeurNotesAdh
        cv={cvProfilOuvert}
        mode="modale"
        onSauvegarde={() => setCvProfilOuvert(null)}
        onAnnuler={() => setCvProfilOuvert(null)}
      />
    )}
    </>
  )
}
