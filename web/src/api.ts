import type { Offre } from './types'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function fetchOffres(): Promise<Offre[]> {
  const response = await fetch(`${API_BASE_URL}/api/offres`)
  if (!response.ok) {
    throw new Error(`Erreur API ${response.status}: ${response.statusText}`)
  }
  return response.json()
}

export async function patchVue(id: number): Promise<Offre> {
  const r = await fetch(`${API_BASE_URL}/api/offres/${id}/vue`, { method: 'PATCH' })
  if (!r.ok) throw new Error(`Erreur PATCH /vue : ${r.status}`)
  return r.json()
}

export async function patchFavori(id: number, favori: boolean): Promise<Offre> {
  const r = await fetch(`${API_BASE_URL}/api/offres/${id}/favori`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ favori }),
  })
  if (!r.ok) throw new Error(`Erreur PATCH /favori : ${r.status}`)
  return r.json()
}

export async function patchStatut(id: number, statut: string): Promise<Offre> {
  const r = await fetch(`${API_BASE_URL}/api/offres/${id}/statut`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ statut }),
  })
  if (!r.ok) throw new Error(`Erreur PATCH /statut : ${r.status}`)
  return r.json()
}

export async function patchNotes(id: number, notes: string | null): Promise<Offre> {
  const r = await fetch(`${API_BASE_URL}/api/offres/${id}/notes`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes }),
  })
  if (!r.ok) throw new Error(`Erreur PATCH /notes : ${r.status}`)
  return r.json()
}

export interface Candidat {
  cv_id: number
  nom_fichier: string
  nom_candidat: string | null
  titre_courant: string | null
  annees_experience: number | null
  localisation_preferee: string | null
  score_global: number
  score_competences: number
  score_domaine: number
  score_experience: number
  score_contrat: number
  score_lieu: number
  details_json: string | null
  date_calcul: string | null
}

export interface CompteurCandidat {
  nb: number
  top: number
}

export async function fetchCompteurs(scoreMin: number = 40): Promise<Record<number, CompteurCandidat>> {
  const r = await fetch(`${API_BASE_URL}/api/offres/compteurs-candidats?score_min=${scoreMin}`)
  if (!r.ok) throw new Error(`Erreur compteurs : ${r.status}`)
  const raw: Record<string, CompteurCandidat> = await r.json()
  // Les clés arrivent en string depuis JSON, on les recast en number
  return Object.fromEntries(Object.entries(raw).map(([k, v]) => [Number(k), v]))
}

export async function fetchCandidats(offreId: number): Promise<Candidat[]> {
  const r = await fetch(`${API_BASE_URL}/api/offres/${offreId}/candidats`)
  if (!r.ok) throw new Error(`Erreur candidats : ${r.status}`)
  return r.json()
}

export interface CV {
  id: number
  nom_fichier: string
  chemin_relatif: string
  date_ajout: string | null
  date_dernier_scan: string | null
  // Profilage Haiku
  nom_candidat: string | null
  titre_courant: string | null
  competences_techniques: string | null
  domaines: string | null
  annees_experience: number | null
  types_contrat_souhaites: string | null
  localisation_preferee: string | null
  tjm_moyen: number | null
  salaire_souhaite: number | null
  date_dernier_profilage: string | null
  // Notes ADH
  tjm_negocie: number | null
  salaire_negocie: number | null
  postes_cibles: string | null
  mobilite: string | null
  disponibilite: string | null
  commentaires_adh: string | null
  statut_relation: string | null
  date_dernier_contact: string | null
  date_modif_notes_adh: string | null
}

export interface NotesAdhUpdate {
  tjm_negocie?: number | null
  salaire_negocie?: number | null
  postes_cibles?: string | null
  mobilite?: string | null
  disponibilite?: string | null
  commentaires_adh?: string | null
  statut_relation?: 'actif' | 'en_pause' | 'place' | 'inactif'
  date_dernier_contact?: string | null
}

export async function fetchCVs(): Promise<CV[]> {
  const r = await fetch(`${API_BASE_URL}/api/cvs`)
  if (!r.ok) throw new Error(`Erreur GET /api/cvs : ${r.status}`)
  return r.json()
}

export async function fetchCVParId(cvId: number): Promise<CV> {
  const r = await fetch(`${API_BASE_URL}/api/cvs/${cvId}`)
  if (!r.ok) throw new Error(`Erreur GET /api/cvs/${cvId} : ${r.status}`)
  return r.json()
}

export async function patchNotesAdh(cvId: number, notes: NotesAdhUpdate): Promise<CV> {
  const r = await fetch(`${API_BASE_URL}/api/cvs/${cvId}/notes-adh`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(notes),
  })
  if (!r.ok) throw new Error(`Erreur PATCH /notes-adh : ${r.status}`)
  return r.json()
}

export interface AnalyseIA {
  score_ia: number
  verdict: string
  explication: string
  points_forts: string[]
  points_faibles: string[]
  questions_a_poser: string[]
  date_analyse: string | null
}

export async function fetchAnalyseIA(cvId: number, offreId: number): Promise<AnalyseIA | null> {
  const r = await fetch(`${API_BASE_URL}/api/cvs/${cvId}/offres/${offreId}/analyse-ia`)
  if (!r.ok) throw new Error(`Erreur GET analyse IA : ${r.status}`)
  return r.json()
}

export async function lancerAnalyseIA(cvId: number, offreId: number): Promise<AnalyseIA> {
  const r = await fetch(`${API_BASE_URL}/api/cvs/${cvId}/offres/${offreId}/analyse-ia`, {
    method: 'POST',
  })
  if (!r.ok) throw new Error(`Erreur POST analyse IA : ${r.status}`)
  return r.json()
}

export type UploadEvent =
  | { step: 'upload';    status: 'ok';          message: string }
  | { step: 'extract';   status: 'ok';          message: string }
  | { step: 'extract';   status: 'error';       message: string }
  | { step: 'profile';   status: 'in_progress'; message: string }
  | { step: 'profile';   status: 'ok';          data: { nom_candidat: string | null; titre_courant: string | null; annees_experience: number | null; nb_competences: number; nb_domaines: number } }
  | { step: 'profile';   status: 'error';       message: string }
  | { step: 'matchings'; status: 'in_progress'; message: string }
  | { step: 'matchings'; status: 'ok';          data: { nb_matchings: number } }
  | { step: 'matchings'; status: 'error';       message: string }
  | { step: 'done';      status: 'ok';          data: { cv_id: number } }

export async function uploaderCv(
  file: File,
  onEvent: (e: UploadEvent) => void,
): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)

  const r = await fetch(`${API_BASE_URL}/api/cvs/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!r.ok) {
    const txt = await r.text().catch(() => '')
    throw new Error(`HTTP ${r.status} : ${txt || r.statusText}`)
  }

  const reader = r.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const event = JSON.parse(line.slice(6)) as UploadEvent
        onEvent(event)
      } catch (e) {
        console.error('Parse SSE error :', e, line)
      }
    }
  }
}
