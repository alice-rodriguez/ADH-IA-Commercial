import type { Offre } from './types'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function fetchOffres(): Promise<Offre[]> {
  const response = await fetch(`${API_BASE_URL}/api/offres`, { credentials: 'include' })
  if (!response.ok) {
    throw new Error(`Erreur API ${response.status}: ${response.statusText}`)
  }
  return response.json()
}

export async function patchVue(id: number): Promise<Offre> {
  const r = await fetch(`${API_BASE_URL}/api/offres/${id}/vue`, { method: 'PATCH', credentials: 'include' })
  if (!r.ok) throw new Error(`Erreur PATCH /vue : ${r.status}`)
  return r.json()
}

export async function patchFavori(id: number, favori: boolean): Promise<Offre> {
  const r = await fetch(`${API_BASE_URL}/api/offres/${id}/favori`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ favori }),
    credentials: 'include',
  })
  if (!r.ok) throw new Error(`Erreur PATCH /favori : ${r.status}`)
  return r.json()
}

export async function patchStatut(id: number, statut: string): Promise<Offre> {
  const r = await fetch(`${API_BASE_URL}/api/offres/${id}/statut`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ statut }),
    credentials: 'include',
  })
  if (!r.ok) throw new Error(`Erreur PATCH /statut : ${r.status}`)
  return r.json()
}

export async function patchNotes(id: number, notes: string | null): Promise<Offre> {
  const r = await fetch(`${API_BASE_URL}/api/offres/${id}/notes`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes }),
    credentials: 'include',
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
  const r = await fetch(`${API_BASE_URL}/api/offres/compteurs-candidats?score_min=${scoreMin}`, { credentials: 'include' })
  if (!r.ok) throw new Error(`Erreur compteurs : ${r.status}`)
  const raw: Record<string, CompteurCandidat> = await r.json()
  return Object.fromEntries(Object.entries(raw).map(([k, v]) => [Number(k), v]))
}

export async function fetchCandidats(offreId: number): Promise<Candidat[]> {
  const r = await fetch(`${API_BASE_URL}/api/offres/${offreId}/candidats`, { credentials: 'include' })
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
  const r = await fetch(`${API_BASE_URL}/api/cvs`, { credentials: 'include' })
  if (!r.ok) throw new Error(`Erreur GET /api/cvs : ${r.status}`)
  return r.json()
}

export async function fetchCVParId(cvId: number): Promise<CV> {
  const r = await fetch(`${API_BASE_URL}/api/cvs/${cvId}`, { credentials: 'include' })
  if (!r.ok) throw new Error(`Erreur GET /api/cvs/${cvId} : ${r.status}`)
  return r.json()
}

export async function patchNotesAdh(cvId: number, notes: NotesAdhUpdate): Promise<CV> {
  const r = await fetch(`${API_BASE_URL}/api/cvs/${cvId}/notes-adh`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(notes),
    credentials: 'include',
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
  const r = await fetch(`${API_BASE_URL}/api/cvs/${cvId}/offres/${offreId}/analyse-ia`, { credentials: 'include' })
  if (!r.ok) throw new Error(`Erreur GET analyse IA : ${r.status}`)
  return r.json()
}

export async function lancerAnalyseIA(cvId: number, offreId: number): Promise<AnalyseIA> {
  const r = await fetch(`${API_BASE_URL}/api/cvs/${cvId}/offres/${offreId}/analyse-ia`, {
    method: 'POST',
    credentials: 'include',
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
    credentials: 'include',
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

// ── Matching CV → Offres ─────────────────────────────────────────────────────

export interface OffreMatch {
  offre_id: number
  titre: string
  entreprise: string | null
  lieu: string | null
  type_contrat: string | null
  url: string | null
  date_collecte: string | null
  score_global: number
  score_competences: number
  score_domaine: number
  score_experience: number
  score_contrat: number
  score_lieu: number
  details_json: string | null
}

export async function fetchOffresParCv(cvId: number, scoreMin: number = 30): Promise<OffreMatch[]> {
  const r = await fetch(`${API_BASE_URL}/api/cvs/${cvId}/offres?score_min=${scoreMin}`, { credentials: 'include' })
  if (!r.ok) throw new Error(`Erreur GET offres par CV : ${r.status}`)
  return r.json()
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export interface User {
  id: number
  username: string
  date_creation: string
}

export interface AuthMe {
  username: string
  user_id: number
}

export async function login(username: string, password: string): Promise<void> {
  const r = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    credentials: 'include',
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data.detail || `Erreur ${r.status}`)
  }
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE_URL}/api/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
}

export async function fetchMe(): Promise<AuthMe | null> {
  const r = await fetch(`${API_BASE_URL}/api/auth/me`, { credentials: 'include' })
  if (r.status === 401) return null
  if (!r.ok) throw new Error(`Erreur /me : ${r.status}`)
  return r.json()
}

export async function fetchUsers(): Promise<User[]> {
  const r = await fetch(`${API_BASE_URL}/api/users`, { credentials: 'include' })
  if (!r.ok) throw new Error(`Erreur GET /api/users : ${r.status}`)
  return r.json()
}

export async function creerUser(username: string, password: string): Promise<User> {
  const r = await fetch(`${API_BASE_URL}/api/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    credentials: 'include',
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data.detail || `Erreur ${r.status}`)
  }
  return r.json()
}

export async function supprimerUser(userId: number): Promise<void> {
  const r = await fetch(`${API_BASE_URL}/api/users/${userId}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data.detail || `Erreur ${r.status}`)
  }
}

export async function resetPassword(userId: number, newPassword: string): Promise<void> {
  const r = await fetch(`${API_BASE_URL}/api/users/${userId}/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_password: newPassword }),
    credentials: 'include',
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data.detail || `Erreur ${r.status}`)
  }
}
