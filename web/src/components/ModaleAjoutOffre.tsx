import { useRef, useState } from 'react'
import type { OffreManuelleResultat } from '../api'
import { ajouterOffreManuelle } from '../api'

type Onglet = 'texte' | 'lien'

const INPUT_CLASS =
  'border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-adh-orange w-full'

interface Props {
  onClose: () => void
  onOffreAjoutee: (resultat: OffreManuelleResultat) => void
}

export default function ModaleAjoutOffre({ onClose, onOffreAjoutee }: Props) {
  const [onglet, setOnglet] = useState<Onglet>('texte')
  const [texte, setTexte] = useState('')
  const [url, setUrl] = useState('')   // partagé entre les deux onglets
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState<string | null>(null)
  const overlayRef = useRef<HTMLDivElement>(null)

  const peutEnvoyer = onglet === 'texte' ? texte.trim() !== '' : url.trim() !== ''

  function handleOverlayClick(e: React.MouseEvent) {
    if (e.target === overlayRef.current && !envoi) onClose()
  }

  async function handleEnvoyer() {
    if (!peutEnvoyer || envoi) return
    setEnvoi(true)
    setErreur(null)
    try {
      const resultat = await ajouterOffreManuelle(
        onglet === 'texte'
          ? { texte: texte.trim(), url: url.trim() || null }
          : { texte: null, url: url.trim() },
      )
      onOffreAjoutee(resultat)
    } catch (e) {
      // Message de l'API affiché tel quel ; la saisie d'Alice est conservée
      setErreur(e instanceof Error ? e.message : String(e))
    } finally {
      setEnvoi(false)
    }
  }

  function classeOnglet(o: Onglet): string {
    return `flex-1 text-sm py-2 px-3 rounded border transition-colors ${
      onglet === o
        ? 'bg-adh-orange text-white border-adh-orange font-semibold'
        : 'bg-white text-gray-600 border-gray-300 hover:border-adh-orange'
    }`
  }

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 bg-black/50 z-50 overflow-y-auto"
    >
      <div className="max-w-2xl mx-auto mt-20 mb-10 bg-white rounded-lg shadow-xl p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-adh-black">Ajouter une annonce</h2>
          {!envoi && (
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-adh-black text-xl leading-none"
              title="Fermer"
            >
              ✕
            </button>
          )}
        </div>

        {/* Onglets */}
        <div className="flex gap-2 mb-5">
          <button onClick={() => setOnglet('texte')} disabled={envoi} className={classeOnglet('texte')}>
            📝 Texte
          </button>
          <button onClick={() => setOnglet('lien')} disabled={envoi} className={classeOnglet('lien')}>
            🔗 Lien
          </button>
        </div>

        {onglet === 'texte' && (
          <div className="flex flex-col gap-4">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Texte de l'annonce</label>
              <textarea
                value={texte}
                onChange={(e) => setTexte(e.target.value)}
                disabled={envoi}
                rows={14}
                placeholder="Collez ici le texte complet de l'annonce (intitulé, client, lieu, TJM, description…)"
                className={`${INPUT_CLASS} font-mono text-xs`}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">
                Lien d'origine <span className="font-normal text-gray-400">(facultatif)</span>
              </label>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={envoi}
                placeholder="https://…"
                className={INPUT_CLASS}
              />
            </div>
          </div>
        )}

        {onglet === 'lien' && (
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Lien de l'annonce</label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={envoi}
              placeholder="https://…"
              className={INPUT_CLASS}
            />
            <p className="text-xs text-gray-500 mt-2">
              Certains sites (LinkedIn, Indeed…) bloquent la lecture automatique. Dans ce cas, copiez
              le texte de l'annonce et collez-le dans l'onglet Texte.
            </p>
          </div>
        )}

        {erreur && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
            {erreur}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 mt-6">
          {envoi && (
            <span className="text-sm text-gray-500 flex items-center gap-2">
              <span className="animate-pulse">⏳</span> Analyse de l'annonce en cours…
            </span>
          )}
          {!envoi && (
            <button onClick={onClose} className="text-sm text-gray-500 hover:text-adh-black px-3 py-2">
              Annuler
            </button>
          )}
          <button
            onClick={handleEnvoyer}
            disabled={!peutEnvoyer || envoi}
            className="text-sm font-semibold bg-adh-orange text-white rounded px-4 py-2 hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Ajouter l'annonce
          </button>
        </div>
      </div>
    </div>
  )
}
