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
