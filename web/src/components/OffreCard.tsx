import { useState } from 'react'
import type { CompteurCandidat } from '../api'
import { patchFavori, patchNotes, patchStatut, patchVue } from '../api'
import type { Offre } from '../types'

const CONTRAT_COLORS: Array<[RegExp, string]> = [
  [/freelance|indépendant|independant/i, 'bg-adh-orange text-white'],
  [/cdi/i,                                'bg-green-500 text-white'],
  [/cdd/i,                                'bg-adh-violet text-adh-black'],
  [/stage|alternance|apprentissage/i,     'bg-blue-300 text-adh-black'],
]

function contratBadgeClass(contrat: string | null): string {
  if (!contrat) return 'bg-gray-300 text-adh-black'
  for (const [regex, classes] of CONTRAT_COLORS) {
    if (regex.test(contrat)) return classes
  }
  return 'bg-gray-300 text-adh-black'
}

const SOURCE_COLORS: Record<string, string> = {
  'APEC': 'bg-blue-500 text-white',
  'Free-Work': 'bg-orange-400 text-white',
  'Welcome to the Jungle': 'bg-green-500 text-white',
}

function sourceBadgeClass(source: string | null): string {
  if (!source) return 'bg-gray-400 text-white'
  return SOURCE_COLORS[source] || 'bg-gray-400 text-white'
}

function scoreColor(score: number | null): string {
  if (score === null) return ''
  if (score >= 80) return 'text-adh-orange'
  if (score >= 60) return 'text-orange-300'
  return 'text-gray-400'
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`
}

function excerpt(offre: Offre): string {
  const text = offre.resume_ia || offre.description || 'Pas de description'
  return text.length > 200 ? text.slice(0, 200) + '…' : text
}

const STATUT_OPTIONS = [
  { label: 'Nouveau',  value: 'nouveau' },
  { label: 'En cours', value: 'en_cours' },
  { label: 'Envoyé',   value: 'envoye' },
  { label: 'Rejeté',   value: 'rejete' },
]

const STATUT_SELECT_CLASS: Record<string, string> = {
  nouveau:  'bg-gray-100 text-gray-700',
  en_cours: 'bg-blue-100 text-blue-700',
  envoye:   'bg-green-100 text-green-700',
  rejete:   'bg-red-100 text-red-700',
}

interface Props {
  offre: Offre
  onUpdate: (offre: Offre) => void
  compteur?: CompteurCandidat
  onOuvrirCandidats?: (offreId: number, titreOffre: string) => void
}

export default function OffreCard({ offre, onUpdate, compteur, onOuvrirCandidats }: Props) {
  const [editingNotes, setEditingNotes] = useState(false)
  const [notesText, setNotesText] = useState(offre.notes ?? '')

  const déjaVue = offre.vue

  async function handleFavori() {
    const prev = offre.favori
    onUpdate({ ...offre, favori: !prev })
    try {
      const updated = await patchFavori(offre.id, !prev)
      onUpdate(updated)
    } catch (e) {
      console.error(e)
      onUpdate({ ...offre, favori: prev })
      alert('Erreur lors de la mise à jour du favori')
    }
  }

  async function handleVoir(e: React.MouseEvent<HTMLAnchorElement>) {
    e.preventDefault()
    if (!offre.vue) {
      onUpdate({ ...offre, vue: true })
      try {
        const updated = await patchVue(offre.id)
        onUpdate(updated)
      } catch (err) {
        console.error(err)
      }
    }
    if (offre.url) window.open(offre.url, '_blank', 'noopener,noreferrer')
  }

  async function handleStatut(e: React.ChangeEvent<HTMLSelectElement>) {
    const nouvelleValeur = e.target.value
    onUpdate({ ...offre, statut: nouvelleValeur })
    try {
      const updated = await patchStatut(offre.id, nouvelleValeur)
      onUpdate(updated)
    } catch (err) {
      console.error(err)
      onUpdate(offre)
      alert('Erreur lors de la mise à jour du statut')
    }
  }

  async function handleSauvegarderNotes() {
    const notes = notesText.trim() || null
    onUpdate({ ...offre, notes })
    try {
      const updated = await patchNotes(offre.id, notes)
      onUpdate(updated)
      setEditingNotes(false)
    } catch (err) {
      console.error(err)
      onUpdate(offre)
      alert('Erreur lors de la sauvegarde des notes')
    }
  }

  function handleAnnulerNotes() {
    setNotesText(offre.notes ?? '')
    setEditingNotes(false)
  }

  return (
    <div className={`bg-white border border-gray-200 rounded-lg shadow-md hover:shadow-lg transition-shadow p-5 flex flex-col gap-3 ${déjaVue ? 'opacity-70' : ''}`}>

      {/* Ligne source + score + favori */}
      <div className="flex items-start justify-between gap-2">
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${sourceBadgeClass(offre.source)}`}>
          {offre.source || 'Source inconnue'}
        </span>
        <div className="flex items-center gap-2">
          {offre.score_ia !== null && (
            <span className={`text-2xl font-bold leading-none ${scoreColor(offre.score_ia)}`}>
              {offre.score_ia}
            </span>
          )}
          <button
            onClick={handleFavori}
            title={offre.favori ? 'Retirer des favoris' : 'Ajouter aux favoris'}
            className="text-adh-orange hover:scale-110 transition-transform flex items-center"
          >
            <svg
              className="w-5 h-5"
              viewBox="0 0 24 24"
              fill={offre.favori ? 'currentColor' : 'none'}
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Titre + entreprise */}
      <div>
        <h3 className="text-xl font-bold text-adh-black leading-tight">{offre.titre}</h3>
        {offre.entreprise && (
          <p className="text-sm text-gray-600 mt-0.5">{offre.entreprise}</p>
        )}
      </div>

      {/* Métadonnées */}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {offre.type_contrat && (
          <span className={`${contratBadgeClass(offre.type_contrat_clarifie || offre.type_contrat)} text-xs font-medium px-2 py-0.5 rounded-full`}>
            {offre.type_contrat_clarifie || offre.type_contrat}
          </span>
        )}
        {offre.lieu && (
          <span className="text-gray-500">{offre.lieu}</span>
        )}
        <span className="text-gray-400 ml-auto">{formatDate(offre.date_collecte)}</span>
      </div>

      {/* Description */}
      <p className="text-sm text-gray-600 flex-1">{excerpt(offre)}</p>

      {/* Statut */}
      <select
        value={offre.statut}
        onChange={handleStatut}
        className={`text-xs px-2 py-1 rounded border border-gray-200 cursor-pointer ${STATUT_SELECT_CLASS[offre.statut] ?? 'bg-gray-100 text-gray-700'}`}
      >
        {STATUT_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      {/* Notes */}
      <div>
        {editingNotes ? (
          <div className="flex flex-col gap-2">
            <textarea
              value={notesText}
              onChange={(e) => setNotesText(e.target.value)}
              rows={3}
              autoFocus
              placeholder="Vos notes..."
              className="text-sm border border-gray-300 rounded p-2 w-full focus:outline-none focus:border-adh-orange resize-none"
            />
            <div className="flex gap-2">
              <button
                onClick={handleSauvegarderNotes}
                className="text-xs font-semibold text-white bg-adh-orange px-3 py-1 rounded hover:opacity-90"
              >
                Sauvegarder
              </button>
              <button
                onClick={handleAnnulerNotes}
                className="text-xs text-gray-500 hover:underline"
              >
                Annuler
              </button>
            </div>
          </div>
        ) : offre.notes ? (
          <div className="flex items-start gap-2">
            <p className="text-xs italic text-gray-500 flex-1">{offre.notes}</p>
            <button
              onClick={() => { setNotesText(offre.notes ?? ''); setEditingNotes(true) }}
              title="Modifier la note"
              className="text-xs text-gray-400 hover:text-adh-orange shrink-0"
            >
              ✎
            </button>
          </div>
        ) : (
          <button
            onClick={() => { setNotesText(''); setEditingNotes(true) }}
            className="text-xs text-gray-400 hover:text-adh-orange"
          >
            + Ajouter note
          </button>
        )}
      </div>

      {/* Badge candidats compatibles */}
      {compteur && compteur.nb >= 1 && onOuvrirCandidats && (
        <button
          onClick={() => onOuvrirCandidats(offre.id, offre.titre)}
          className="text-sm font-medium text-adh-orange bg-orange-50 hover:bg-orange-100 px-3 py-2 rounded-md text-left transition-colors"
        >
          🎯 {compteur.nb} candidat{compteur.nb > 1 ? 's' : ''} compatible{compteur.nb > 1 ? 's' : ''}{' '}
          <span className="text-gray-500">· Top : {compteur.top}%</span>
        </button>
      )}

      {/* Bouton voir */}
      {offre.url ? (
        <a
          href={offre.url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={handleVoir}
          className="mt-auto inline-block text-sm font-semibold text-adh-orange hover:underline"
        >
          Voir l'offre →
        </a>
      ) : (
        <span className="mt-auto text-sm text-gray-300 cursor-not-allowed">
          Voir l'offre →
        </span>
      )}
    </div>
  )
}
