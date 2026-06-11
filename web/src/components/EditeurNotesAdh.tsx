import { useRef, useState } from 'react'
import type { CV, NotesAdhUpdate } from '../api'
import { patchNotesAdh } from '../api'

type StatutRelation = 'actif' | 'en_pause' | 'place' | 'inactif'

const STATUT_OPTIONS: { value: StatutRelation; label: string }[] = [
  { value: 'actif',    label: 'Actif' },
  { value: 'en_pause', label: 'En pause' },
  { value: 'place',    label: 'Placé' },
  { value: 'inactif',  label: 'Inactif' },
]

const INPUT_CLASS =
  'border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-adh-orange w-full'

interface Props {
  cv: CV
  mode: 'inline' | 'modale'
  onSauvegarde: (cv: CV) => void
  onAnnuler: () => void
  onVoirOffres?: (cvId: number, nom: string) => void
}

export default function EditeurNotesAdh({ cv, mode, onSauvegarde, onAnnuler, onVoirOffres }: Props) {
  const [tjm_negocie, setTjmNegocie] = useState<number | null>(cv.tjm_negocie)
  const [salaire_negocie, setSalaireNegocie] = useState<number | null>(cv.salaire_negocie)
  const [postes_cibles, setPostesCibles] = useState(cv.postes_cibles ?? '')
  const [mobilite, setMobilite] = useState(cv.mobilite ?? '')
  const [disponibilite, setDisponibilite] = useState(cv.disponibilite ?? '')
  const [commentaires_adh, setCommentairesAdh] = useState(cv.commentaires_adh ?? '')
  const [statut_relation, setStatutRelation] = useState<StatutRelation>(
    (cv.statut_relation as StatutRelation) ?? 'actif',
  )
  const [date_dernier_contact, setDateDernierContact] = useState(cv.date_dernier_contact ?? '')
  const [profil_adh, setProfilAdh] = useState(cv.profil_adh ?? '')
  const [notes_experiences, setNotesExperiences] = useState(cv.notes_experiences ?? '')
  const [saving, setSaving] = useState(false)
  const overlayRef = useRef<HTMLDivElement>(null)

  async function handleSauvegarder() {
    const payload: NotesAdhUpdate = {}

    if (tjm_negocie !== cv.tjm_negocie) payload.tjm_negocie = tjm_negocie
    if (salaire_negocie !== cv.salaire_negocie) payload.salaire_negocie = salaire_negocie

    const initPostes = cv.postes_cibles ?? ''
    if (postes_cibles !== initPostes)
      payload.postes_cibles = postes_cibles === '' ? null : postes_cibles

    const initMobilite = cv.mobilite ?? ''
    if (mobilite !== initMobilite)
      payload.mobilite = mobilite === '' ? null : mobilite

    const initDispo = cv.disponibilite ?? ''
    if (disponibilite !== initDispo)
      payload.disponibilite = disponibilite === '' ? null : disponibilite

    const initComm = cv.commentaires_adh ?? ''
    if (commentaires_adh !== initComm)
      payload.commentaires_adh = commentaires_adh === '' ? null : commentaires_adh

    const initStatut: StatutRelation = (cv.statut_relation as StatutRelation) ?? 'actif'
    if (statut_relation !== initStatut) payload.statut_relation = statut_relation

    const initDate = cv.date_dernier_contact ?? ''
    if (date_dernier_contact !== initDate)
      payload.date_dernier_contact = date_dernier_contact === '' ? null : date_dernier_contact

    const initProfilAdh = cv.profil_adh ?? ''
    if (profil_adh !== initProfilAdh)
      payload.profil_adh = profil_adh === '' ? null : profil_adh

    const initNotesExp = cv.notes_experiences ?? ''
    if (notes_experiences !== initNotesExp)
      payload.notes_experiences = notes_experiences === '' ? null : notes_experiences

    if (Object.keys(payload).length === 0) {
      alert('Aucune modification')
      return
    }

    setSaving(true)
    try {
      const updated = await patchNotesAdh(cv.id, payload)
      onSauvegarde(updated)
    } catch (e) {
      console.error(e)
      alert('Erreur lors de la sauvegarde')
    } finally {
      setSaving(false)
    }
  }

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === overlayRef.current) onAnnuler()
  }

  const titre = `Profil ADH — ${cv.nom_candidat ?? cv.nom_fichier} · IDADH-${String(cv.id).padStart(3, '0')}`

  const contenu = (
    <div className={mode === 'modale' ? 'max-w-2xl mx-auto mt-20 mb-10 bg-white rounded-lg shadow-xl p-6' : ''}>
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-5">
        <div className="flex flex-col gap-2">
          <h2 className="text-lg font-bold text-adh-black">{titre}</h2>
          {onVoirOffres && (
            <button
              onClick={() => onVoirOffres(cv.id, cv.nom_candidat ?? cv.nom_fichier)}
              className="self-start text-xs text-gray-500 hover:text-adh-orange border border-gray-200 rounded px-2 py-1 hover:border-adh-orange transition-colors"
            >
              🎯 Voir ses offres compatibles
            </button>
          )}
        </div>
        {mode === 'modale' && (
          <button
            onClick={onAnnuler}
            className="text-gray-400 hover:text-adh-black text-xl leading-none shrink-0"
            title="Fermer"
          >
            ✕
          </button>
        )}
      </div>

      {/* Grille 2 colonnes */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        {/* Colonne 1 */}
        <div className="flex flex-col gap-3">
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">TJM négocié (€/j)</label>
            <input
              type="number"
              value={tjm_negocie ?? ''}
              onChange={(e) => setTjmNegocie(e.target.value === '' ? null : Number(e.target.value))}
              placeholder="ex: 800"
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Salaire négocié (€/an)</label>
            <input
              type="number"
              value={salaire_negocie ?? ''}
              onChange={(e) => setSalaireNegocie(e.target.value === '' ? null : Number(e.target.value))}
              placeholder="ex: 75000"
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Statut relation</label>
            <select
              value={statut_relation}
              onChange={(e) => setStatutRelation(e.target.value as StatutRelation)}
              className={INPUT_CLASS}
            >
              {STATUT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Dernier contact</label>
            <input
              type="date"
              value={date_dernier_contact}
              onChange={(e) => setDateDernierContact(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
        </div>

        {/* Colonne 2 */}
        <div className="flex flex-col gap-3">
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Postes ciblés</label>
            <textarea
              rows={2}
              value={postes_cibles}
              onChange={(e) => setPostesCibles(e.target.value)}
              placeholder="Chef de projet SAP, MOA Banque..."
              className={`${INPUT_CLASS} resize-none`}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Mobilité</label>
            <textarea
              rows={2}
              value={mobilite}
              onChange={(e) => setMobilite(e.target.value)}
              placeholder="Paris/IDF, remote 2j/sem..."
              className={`${INPUT_CLASS} resize-none`}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Disponibilité</label>
            <textarea
              rows={2}
              value={disponibilite}
              onChange={(e) => setDisponibilite(e.target.value)}
              placeholder="Libre dans 2 mois..."
              className={`${INPUT_CLASS} resize-none`}
            />
          </div>
        </div>
      </div>

      {/* Commentaires pleine largeur */}
      <div className="mb-4">
        <label className="block text-xs font-semibold text-gray-600 mb-1">Commentaires ADH</label>
        <textarea
          rows={5}
          value={commentaires_adh}
          onChange={(e) => setCommentairesAdh(e.target.value)}
          placeholder="Notes libres sur le candidat..."
          className={`${INPUT_CLASS} resize-none`}
        />
      </div>

      {/* Profil ADH personnalisé (CV adapté) */}
      <div className="mb-4">
        <label className="block text-xs font-semibold text-gray-600 mb-1">
          Profil personnalisé (CV adapté)
        </label>
        <textarea
          rows={4}
          value={profil_adh}
          onChange={(e) => setProfilAdh(e.target.value)}
          placeholder="Profil personnalisé (optionnel) — sinon le profil du CV original sera utilisé"
          className={`${INPUT_CLASS} resize-none`}
        />
      </div>

      {/* Notes expériences (CV adapté) */}
      <div className="mb-5">
        <label className="block text-xs font-semibold text-gray-600 mb-1">
          Notes expériences (CV adapté)
        </label>
        <textarea
          rows={4}
          value={notes_experiences}
          onChange={(e) => setNotesExperiences(e.target.value)}
          placeholder="Notes additionnelles sur les expériences (détails, autres versions de CV, réalisations clés...)"
          className={`${INPUT_CLASS} resize-none`}
        />
      </div>

      {/* Boutons */}
      <div className="flex items-center gap-4">
        <button
          onClick={handleSauvegarder}
          disabled={saving}
          className="bg-adh-orange text-white px-4 py-2 rounded text-sm font-semibold hover:opacity-90 disabled:opacity-60"
        >
          {saving ? 'Sauvegarde...' : 'Sauvegarder'}
        </button>
        <button
          onClick={onAnnuler}
          className="text-gray-500 text-sm hover:underline"
        >
          Annuler
        </button>
      </div>
    </div>
  )

  if (mode === 'modale') {
    return (
      <div
        ref={overlayRef}
        onClick={handleOverlayClick}
        className="fixed inset-0 bg-black/50 z-[60] overflow-y-auto"
      >
        {contenu}
      </div>
    )
  }

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mt-2">
      {contenu}
    </div>
  )
}
