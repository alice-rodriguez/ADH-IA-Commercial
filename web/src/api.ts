import type { Offre } from './types'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function fetchOffres(): Promise<Offre[]> {
  const response = await fetch(`${API_BASE_URL}/api/offres`)
  if (!response.ok) {
    throw new Error(`Erreur API ${response.status}: ${response.statusText}`)
  }
  return response.json()
}
