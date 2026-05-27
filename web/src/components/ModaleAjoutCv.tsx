import { useRef, useState } from 'react'
import type { UploadEvent } from '../api'
import { uploaderCv } from '../api'

type Etape = 'upload' | 'progression' | 'resultat' | 'erreur'
type StepStatus = 'pending' | 'in_progress' | 'ok' | 'error'

interface EtapeProgression {
  step: string
  label: string
  status: StepStatus
  detail?: string
}

interface ResultatUpload {
  cv_id: number
  nom_candidat: string | null
  titre_courant: string | null
  annees_experience: number | null
  nb_competences: number
  nb_domaines: number
  nb_matchings: number
}

const ETAPES_INITIALES: EtapeProgression[] = [
  { step: 'upload',    label: 'Fichier sauvegardé',  status: 'pending' },
  { step: 'extract',   label: 'Texte extrait',        status: 'pending' },
  { step: 'profile',   label: 'Profilage IA',         status: 'pending' },
  { step: 'matchings', label: 'Calcul des matchings', status: 'pending' },
  { step: 'done',      label: 'Finalisation',         status: 'pending' },
]

function StepIcon({ status }: { status: StepStatus }) {
  switch (status) {
    case 'ok':          return <span className="text-green-600 text-lg">✅</span>
    case 'in_progress': return <span className="animate-pulse text-lg">⏳</span>
    case 'error':       return <span className="text-lg">❌</span>
    default:            return <span className="text-gray-400 text-lg">⏱️</span>
  }
}

interface Props {
  onClose: () => void
  onCvAjoute: (cvId: number) => void
}

export default function ModaleAjoutCv({ onClose, onCvAjoute }: Props) {
  const [etape, setEtape] = useState<Etape>('upload')
  const [fichier, setFichier] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [progression, setProgression] = useState<EtapeProgression[]>(
    ETAPES_INITIALES.map((e) => ({ ...e })),
  )
  const [resultat, setResultat] = useState<ResultatUpload | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === overlayRef.current && etape !== 'progression') onClose()
  }

  function validerFichier(f: File): string | null {
    if (!f.name.toLowerCase().endsWith('.pdf') && f.type !== 'application/pdf') {
      return 'Seuls les fichiers PDF sont acceptés'
    }
    if (f.size > 10 * 1024 * 1024) {
      return `Fichier trop volumineux (${(f.size / 1024 / 1024).toFixed(1)} MB, max 10 MB)`
    }
    return null
  }

  function mettreAJourStep(step: string, status: StepStatus, detail?: string) {
    setProgression((prev) =>
      prev.map((e) => (e.step === step ? { ...e, status, detail } : e)),
    )
  }

  async function demarrerUpload(f: File) {
    setFichier(f)
    setProgression(ETAPES_INITIALES.map((e) => ({ ...e })))
    setEtape('progression')

    let partiel: Partial<ResultatUpload> = {}

    function handleEvent(event: UploadEvent) {
      if (event.step === 'upload' && event.status === 'ok') {
        mettreAJourStep('upload', 'ok', event.message)
      } else if (event.step === 'extract') {
        if (event.status === 'ok') {
          mettreAJourStep('extract', 'ok', event.message)
        } else {
          mettreAJourStep('extract', 'error', event.message)
          setErreur(event.message)
          setEtape('erreur')
        }
      } else if (event.step === 'profile') {
        if (event.status === 'in_progress') {
          mettreAJourStep('profile', 'in_progress', event.message)
        } else if (event.status === 'ok') {
          const { nom_candidat, titre_courant, annees_experience, nb_competences, nb_domaines } = event.data
          partiel = { ...partiel, nom_candidat, titre_courant, annees_experience, nb_competences, nb_domaines }
          mettreAJourStep('profile', 'ok', nom_candidat ?? 'profil extrait')
        } else {
          mettreAJourStep('profile', 'error', event.message)
          setErreur(event.message)
          setEtape('erreur')
        }
      } else if (event.step === 'matchings') {
        if (event.status === 'in_progress') {
          mettreAJourStep('matchings', 'in_progress', event.message)
        } else if (event.status === 'ok') {
          partiel = { ...partiel, nb_matchings: event.data.nb_matchings }
          mettreAJourStep('matchings', 'ok', `${event.data.nb_matchings} matchings calculés`)
        } else {
          mettreAJourStep('matchings', 'error', event.message)
          setErreur(event.message)
          setEtape('erreur')
        }
      } else if (event.step === 'done' && event.status === 'ok') {
        partiel = { ...partiel, cv_id: event.data.cv_id }
        mettreAJourStep('done', 'ok')
        setResultat(partiel as ResultatUpload)
        setEtape('resultat')
      }
    }

    try {
      await uploaderCv(f, handleEvent)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Erreur inconnue'
      setErreur(msg)
      setEtape('erreur')
    }
  }

  function handleFileSelect(f: File) {
    const errValidation = validerFichier(f)
    if (errValidation) {
      setErreur(errValidation)
      setEtape('erreur')
      return
    }
    demarrerUpload(f)
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(true)
  }

  function handleDragLeave() {
    setDragOver(false)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFileSelect(f)
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (f) handleFileSelect(f)
  }

  function recommencer() {
    setEtape('upload')
    setFichier(null)
    setErreur(null)
    setResultat(null)
    setProgression(ETAPES_INITIALES.map((e) => ({ ...e })))
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 bg-black/50 z-50 overflow-y-auto"
    >
      <div className="max-w-lg mx-auto mt-24 mb-10 bg-white rounded-lg shadow-xl p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold text-adh-black">Ajouter un candidat</h2>
          {etape !== 'progression' && (
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-adh-black text-xl leading-none"
              title="Fermer"
            >
              ✕
            </button>
          )}
        </div>

        {/* ÉTAPE : upload */}
        {etape === 'upload' && (
          <>
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => inputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-10 flex flex-col items-center gap-3 cursor-pointer transition-colors ${
                dragOver
                  ? 'border-adh-orange bg-orange-50'
                  : 'border-gray-300 hover:border-adh-orange hover:bg-gray-50'
              }`}
            >
              <span className="text-4xl">📄</span>
              <p className="text-sm text-gray-600 text-center">
                Glisse un fichier PDF ici ou clique pour sélectionner
              </p>
              <p className="text-xs text-gray-400">Format accepté : .pdf, taille max 10 MB</p>
            </div>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              onChange={handleInputChange}
            />
          </>
        )}

        {/* ÉTAPE : progression */}
        {etape === 'progression' && (
          <>
            <p className="text-sm text-gray-500 mb-5 italic truncate">
              Ajout de {fichier?.name}
            </p>
            <ul className="flex flex-col gap-4">
              {progression.map((e) => (
                <li key={e.step} className="flex items-start gap-3">
                  <StepIcon status={e.status} />
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium ${e.status === 'error' ? 'text-red-500' : 'text-adh-black'}`}>
                      {e.label}
                    </p>
                    {e.detail && (
                      <p className="text-xs text-gray-500 mt-0.5 truncate">{e.detail}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}

        {/* ÉTAPE : résultat */}
        {etape === 'resultat' && resultat && (
          <>
            <div className="text-center mb-5">
              <p className="text-4xl mb-2">✅</p>
              <p className="font-bold text-adh-black text-lg">
                {resultat.nom_candidat ?? fichier?.name} ajouté !
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-4 flex flex-col gap-2 text-sm mb-6">
              <div className="flex gap-2">
                <span className="text-gray-400 w-44 shrink-0">Titre actuel</span>
                <span className="text-gray-700">{resultat.titre_courant ?? '—'}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-gray-400 w-44 shrink-0">Expérience</span>
                <span className="text-gray-700">
                  {resultat.annees_experience !== null ? `${resultat.annees_experience} ans` : '—'}
                </span>
              </div>
              <div className="flex gap-2">
                <span className="text-gray-400 w-44 shrink-0">Compétences détectées</span>
                <span className="text-gray-700">{resultat.nb_competences}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-gray-400 w-44 shrink-0">Domaines</span>
                <span className="text-gray-700">{resultat.nb_domaines}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-gray-400 w-44 shrink-0">Matchings calculés</span>
                <span className="text-gray-700">{resultat.nb_matchings}</span>
              </div>
            </div>
            <div className="flex gap-3 justify-end">
              <button
                onClick={onClose}
                className="text-sm text-gray-500 hover:text-adh-black border border-gray-300 rounded px-4 py-2 transition-colors"
              >
                Fermer
              </button>
              <button
                onClick={() => onCvAjoute(resultat.cv_id)}
                className="text-sm font-semibold bg-adh-orange text-white rounded px-4 py-2 hover:opacity-90 transition-opacity"
              >
                Compléter les Notes ADH →
              </button>
            </div>
          </>
        )}

        {/* ÉTAPE : erreur */}
        {etape === 'erreur' && (
          <div className="text-center">
            <p className="text-4xl mb-3">❌</p>
            <p className="font-bold text-adh-black mb-2">Erreur lors de l'ajout</p>
            <p className="text-sm text-gray-500 mb-6">{erreur}</p>
            <button
              onClick={recommencer}
              className="text-sm font-semibold bg-adh-orange text-white rounded px-4 py-2 hover:opacity-90"
            >
              Recommencer
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
