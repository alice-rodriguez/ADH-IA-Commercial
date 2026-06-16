import { useEffect, useRef, useState } from 'react'
import type { AnalyseIA, OffreMatch } from '../api'
import { fetchAnalyseIA, fetchOffresParCv, getLangueCV, lancerAnalyseIA } from '../api'
import ModalePreviewCV from './ModalePreviewCV'

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
  cvId: number
  nomCandidat: string
  onClose: () => void
}

type AnalyseState = AnalyseIA | 'loading' | null

export default function ModaleOffres({ cvId, nomCandidat, onClose }: Props) {
  const [offres, setOffres] = useState<OffreMatch[]>([])
  const [loading, setLoading] = useState(true)
  const [seuilAffichage, setSeuilAffichage] = useState(30)
  const [offreExpanded, setOffreExpanded] = useState<number | null>(null)
  const [analysesIA, setAnalysesIA] = useState<Record<number, AnalyseState>>({})
  const [analyseExpanded, setAnalyseExpanded] = useState<number | null>(null)
  const [previewCv, setPreviewCv] = useState<{ offreId: number; entrepriseOffre: string; langueDetectee: 'fr' | 'en' } | null>(null)
  const [openingPreviewFor, setOpeningPreviewFor] = useState<number | null>(null)
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchOffresParCv(cvId)
      .then(async (offresData) => {
        setOffres(offresData)
        const analyses = await Promise.all(
          offresData.map(async (o) => {
            try {
              const a = await fetchAnalyseIA(cvId, o.offre_id)
              return { offreId: o.offre_id, analyse: a }
            } catch {
              return { offreId: o.offre_id, analyse: null }
            }
          })
        )
        const map: Record<number, AnalyseIA> = {}
        analyses.forEach(({ offreId, analyse }) => {
          if (analyse) map[offreId] = analyse
        })
        setAnalysesIA(map)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [cvId])

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === overlayRef.current) onClose()
  }

  function toggleExpand(offreId: number) {
    setOffreExpanded((prev) => (prev === offreId ? null : offreId))
  }

  function toggleAnalyse(offreId: number) {
    setAnalyseExpanded((prev) => (prev === offreId ? null : offreId))
  }

  async function chargerAnalyse(offreId: number, forcer = false) {
    setAnalysesIA((prev) => ({ ...prev, [offreId]: 'loading' }))
    try {
      let analyse: AnalyseIA | null = null
      if (!forcer) {
        analyse = await fetchAnalyseIA(cvId, offreId)
      }
      if (!analyse) {
        analyse = await lancerAnalyseIA(cvId, offreId)
      }
      setAnalysesIA((prev) => ({ ...prev, [offreId]: analyse }))
      setAnalyseExpanded(offreId)
    } catch (e) {
      console.error(e)
      setAnalysesIA((prev) => ({ ...prev, [offreId]: null }))
      alert("L'analyse IA a échoué. Vérifiez que la clé ANTHROPIC_API_KEY est configurée.")
    }
  }

  function handleAnalyseBtnClick(offreId: number) {
    const state = analysesIA[offreId]
    if (state === undefined || state === null) {
      chargerAnalyse(offreId)
    } else if (state !== 'loading') {
      toggleAnalyse(offreId)
    }
  }

  async function handleOuvrirPreview(offreId: number, entreprise: string) {
    setOpeningPreviewFor(offreId)
    try {
      const langue = await getLangueCV(cvId)
      setPreviewCv({ offreId, entrepriseOffre: entreprise, langueDetectee: langue })
    } catch {
      setPreviewCv({ offreId, entrepriseOffre: entreprise, langueDetectee: 'fr' })
    } finally {
      setOpeningPreviewFor(null)
    }
  }

  const offresFiltrees = offres.filter((o) => o.score_global >= seuilAffichage)

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
            <h2 className="text-lg font-bold text-adh-black">Offres compatibles</h2>
            <p className="text-sm text-gray-500 italic mt-0.5">{nomCandidat}</p>
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
        ) : offresFiltrees.length === 0 ? (
          <p className="text-center text-gray-400 py-8">
            Aucune offre avec score ≥ {seuilAffichage}%
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {offresFiltrees.map((o) => {
              const expanded = offreExpanded === o.offre_id
              const analyseState = analysesIA[o.offre_id]
              const analyseOuverte = analyseExpanded === o.offre_id
              const analyse = (analyseState !== 'loading' && analyseState !== null && analyseState !== undefined)
                ? analyseState as AnalyseIA
                : null

              let compInfo: string | undefined
              if (o.details_json) {
                try {
                  const d = JSON.parse(o.details_json)
                  if (d.nb_competences_cv) {
                    const trouvees = Math.round(o.score_competences * d.nb_competences_cv / 100)
                    compInfo = `(${trouvees}/${d.nb_competences_cv})`
                  }
                } catch { /* ignore */ }
              }

              return (
                <div key={o.offre_id} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-2xl font-bold leading-none ${scoreTextClass(o.score_global)}`}>
                          {o.score_global}%
                        </span>
                        <span className="font-semibold text-adh-black text-sm truncate">{o.titre}</span>
                      </div>
                      {o.entreprise && (
                        <p className="text-xs text-gray-500 mt-0.5">{o.entreprise}</p>
                      )}
                      <div className="flex gap-3 text-xs text-gray-400 mt-0.5 flex-wrap">
                        {o.lieu && <span>{o.lieu}</span>}
                        {o.type_contrat && <span>{o.type_contrat}</span>}
                        {o.date_collecte && (
                          <span>{new Date(o.date_collecte).toLocaleDateString('fr-FR')}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2 shrink-0 flex-wrap justify-end">
                      <button
                        onClick={() => toggleExpand(o.offre_id)}
                        className="text-xs text-gray-500 hover:text-adh-orange border border-gray-200 rounded px-2 py-1 hover:border-adh-orange transition-colors"
                      >
                        {expanded ? 'Masquer ▲' : 'Détail du score ▼'}
                      </button>
                      <button
                        onClick={() => handleAnalyseBtnClick(o.offre_id)}
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
                      {o.url && (
                        <a
                          href={o.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-gray-500 hover:text-adh-orange border border-gray-200 rounded px-2 py-1 hover:border-adh-orange transition-colors"
                        >
                          Voir l'offre →
                        </a>
                      )}
                    </div>
                  </div>

                  {expanded && (
                    <div className="mt-3 pt-3 border-t border-gray-100 flex flex-col gap-2">
                      <BarreScore label="Compétences" score={o.score_competences} info={compInfo} />
                      <BarreScore label="Domaine"     score={o.score_domaine} />
                      <BarreScore label="Expérience"  score={o.score_experience} />
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
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => chargerAnalyse(o.offre_id, true)}
                            className="text-xs opacity-80 hover:opacity-100 border border-white/50 rounded px-2 py-0.5 transition-opacity"
                            title="Relancer l'analyse IA"
                          >
                            🔄 Relancer
                          </button>
                          <button
                            onClick={() => handleOuvrirPreview(o.offre_id, o.entreprise || '')}
                            disabled={openingPreviewFor === o.offre_id}
                            className="text-xs opacity-80 hover:opacity-100 border border-white/50 rounded px-2 py-0.5 transition-opacity disabled:opacity-40"
                            title="Générer le CV adapté ADH"
                          >
                            {openingPreviewFor === o.offre_id ? '⏳ Chargement...' : '📄 Générer CV adapté'}
                          </button>
                        </div>
                      </div>
                      {/* Explication */}
                      <p className="text-xs text-gray-600 mb-3 leading-relaxed">{analyse.explication}</p>

                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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

    {previewCv && (
      <ModalePreviewCV
        cvId={cvId}
        offreId={previewCv.offreId}
        entrepriseOffre={previewCv.entrepriseOffre}
        langueDetectee={previewCv.langueDetectee}
        onClose={() => setPreviewCv(null)}
      />
    )}
    </>
  )
}
