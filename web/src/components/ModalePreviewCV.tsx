import { useEffect, useRef, useState } from 'react'
import {
  calculerTitreKeyValue,
  cancelCvDraft,
  confirmCv,
  downloadFinalCv,
  fetchDraftPdf,
  previewCv,
} from '../api'

const CONTACT_EMAIL_DEFAUT = 'contact@adhpmconsulting.com'
const CONTACT_TEL_DEFAUT = '+33 7 89 39 82 24'

const INPUT_CLASS =
  'border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:border-adh-orange w-full'

interface Props {
  cvId: number
  offreId: number
  entrepriseOffre: string
  langueDetectee: 'fr' | 'en'
  onClose: () => void
}

export default function ModalePreviewCV({ cvId, offreId, entrepriseOffre, langueDetectee, onClose }: Props) {
  const [draftId, setDraftId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [blobUrl, setBlobUrl] = useState<string | null>(null)

  const [contactEmail, setContactEmail] = useState(CONTACT_EMAIL_DEFAUT)
  const [contactTelephone, setContactTelephone] = useState(CONTACT_TEL_DEFAUT)
  const [langue, setLangue] = useState<'fr' | 'en'>(langueDetectee)
  const [titreKeyValue, setTitreKeyValue] = useState(() =>
    calculerTitreKeyValue(entrepriseOffre, langueDetectee),
  )
  const [titreCustomise, setTitreCustomise] = useState(false)
  const [instructions, setInstructions] = useState('')

  const overlayRef = useRef<HTMLDivElement>(null)
  // Refs pour accès dans les closures sans stale values
  const draftIdRef = useRef<string | null>(null)
  const blobUrlRef = useRef<string | null>(null)

  useEffect(() => { draftIdRef.current = draftId }, [draftId])
  useEffect(() => { blobUrlRef.current = blobUrl }, [blobUrl])

  // Recalcul titre par défaut quand langue change (sauf si Alice l'a customisé)
  useEffect(() => {
    if (!titreCustomise) {
      setTitreKeyValue(calculerTitreKeyValue(entrepriseOffre, langue))
    }
  }, [langue, entrepriseOffre, titreCustomise])

  function revokeBlobUrl() {
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      setBlobUrl(null)
      blobUrlRef.current = null
    }
  }

  async function chargerDraft(ancienDraftId: string | null) {
    setLoading(true)
    setError(null)

    if (ancienDraftId) {
      cancelCvDraft(ancienDraftId).catch(() => {})
    }
    revokeBlobUrl()

    try {
      const resp = await previewCv(cvId, offreId, {
        contact_email: contactEmail,
        contact_telephone: contactTelephone,
        langue,
        titre_key_value: titreKeyValue || undefined,
        instructions: instructions || undefined,
      })
      setDraftId(resp.draft_id)
      draftIdRef.current = resp.draft_id

      const blob = await fetchDraftPdf(resp.draft_id)
      const url = URL.createObjectURL(blob)
      setBlobUrl(url)
      blobUrlRef.current = url
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur génération')
    } finally {
      setLoading(false)
    }
  }

  // Génération initiale au montage
  useEffect(() => {
    chargerDraft(null)
    return () => {
      revokeBlobUrl()
      if (draftIdRef.current) {
        cancelCvDraft(draftIdRef.current).catch(() => {})
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleRegenerer() {
    await chargerDraft(draftId)
  }

  async function handleTelecharger() {
    if (!draftId) return
    setLoading(true)
    setError(null)
    try {
      const { chemin_final } = await confirmCv(cvId, offreId, draftId, {
        contact_email: contactEmail,
        contact_telephone: contactTelephone,
        instructions: instructions || undefined,
      })
      // Le draft est maintenant déplacé → ne pas l'annuler au unmount
      draftIdRef.current = null
      setDraftId(null)

      const blob = await downloadFinalCv(chemin_final)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `CV_ADH_IDADH-${String(cvId).padStart(3, '0')}_offre_${offreId}.pdf`
      a.click()
      URL.revokeObjectURL(url)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur téléchargement')
      setLoading(false)
    }
  }

  function handleFermer() {
    if (draftIdRef.current) {
      cancelCvDraft(draftIdRef.current).catch(() => {})
      draftIdRef.current = null
    }
    onClose()
  }

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === overlayRef.current) handleFermer()
  }

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 bg-black/60 z-[70] overflow-y-auto flex items-start justify-center p-4"
    >
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-6xl mt-8 mb-8 flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 shrink-0">
          <h2 className="text-base font-bold text-adh-black">
            Aperçu CV adapté — IDADH-{String(cvId).padStart(3, '0')} × offre {offreId}
          </h2>
          <button
            onClick={handleFermer}
            className="text-gray-400 hover:text-adh-black text-xl leading-none"
            title="Fermer sans télécharger"
          >
            ✕
          </button>
        </div>

        {/* Corps */}
        <div className="flex flex-col lg:flex-row min-h-0">

          {/* Iframe PDF */}
          <div className="flex-1 min-h-[500px] lg:min-h-[680px] bg-gray-100 relative">
            {loading && (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-gray-100 z-10">
                <div className="text-4xl mb-3">⏳</div>
                <p className="text-sm text-gray-500 text-center px-6">
                  Génération en cours (10-20 sec)…
                </p>
              </div>
            )}
            {!loading && error && (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-gray-100 z-10 p-8">
                <p className="text-sm text-red-600 text-center">{error}</p>
              </div>
            )}
            {blobUrl && !loading && (
              <iframe
                src={blobUrl}
                className="w-full h-full min-h-[500px] border-0"
                title="Aperçu CV"
              />
            )}
          </div>

          {/* Panneau contrôles */}
          <div className="w-full lg:w-72 shrink-0 border-t lg:border-t-0 lg:border-l border-gray-200 p-4 flex flex-col gap-4 overflow-y-auto">

            {/* Contact */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Contact</p>
              <div className="flex flex-col gap-2">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Email</label>
                  <input
                    type="email"
                    value={contactEmail}
                    onChange={(e) => setContactEmail(e.target.value)}
                    className={INPUT_CLASS}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Téléphone</label>
                  <input
                    type="tel"
                    value={contactTelephone}
                    onChange={(e) => setContactTelephone(e.target.value)}
                    className={INPUT_CLASS}
                  />
                </div>
              </div>
            </div>

            {/* Langue */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Langue du CV</p>
              <div className="flex gap-2">
                {(['fr', 'en'] as const).map((l) => (
                  <button
                    key={l}
                    onClick={() => setLangue(l)}
                    className={`flex-1 text-sm font-semibold py-1.5 rounded border transition-colors ${
                      langue === l
                        ? 'bg-adh-orange text-white border-adh-orange'
                        : 'bg-white text-gray-600 border-gray-300 hover:border-adh-orange hover:text-adh-orange'
                    }`}
                  >
                    {l === 'fr' ? '🇫🇷 FR' : '🇬🇧 EN'}
                  </button>
                ))}
              </div>
            </div>

            {/* Titre KEY VALUE */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Titre points forts
              </p>
              <input
                type="text"
                value={titreKeyValue}
                onChange={(e) => {
                  setTitreKeyValue(e.target.value)
                  setTitreCustomise(true)
                }}
                className={INPUT_CLASS}
              />
            </div>

            {/* Instructions */}
            <div className="flex-1">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Instructions <span className="font-normal normal-case">(optionnel)</span>
              </p>
              <textarea
                rows={3}
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                placeholder="Ex : Mettre en avant la gestion budgétaire, ton plus formel…"
                className={`${INPUT_CLASS} resize-none`}
              />
            </div>

            {/* Boutons */}
            <div className="flex flex-col gap-2 pt-2 border-t border-gray-100">
              <button
                onClick={handleRegenerer}
                disabled={loading}
                className="w-full bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-semibold py-2 rounded border border-gray-300 disabled:opacity-50 transition-colors"
              >
                {loading ? '⏳ Génération…' : '🔄 Régénérer'}
              </button>
              <button
                onClick={handleTelecharger}
                disabled={loading || !draftId}
                className="w-full bg-adh-orange text-white text-sm font-semibold py-2 rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                📥 Télécharger
              </button>
              <button
                onClick={handleFermer}
                className="w-full text-gray-400 hover:text-gray-600 text-sm py-1 transition-colors"
              >
                ❌ Fermer sans télécharger
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
