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
