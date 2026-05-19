import type { Offre } from '../types'

export interface FiltresState {
  sources: string[]
  contrats: string[]
  statuts: string[]
  scoreMin: number | null
  periode: 'tout' | '7j' | '24h'
  motsCles: string
  lieu: string
  toggleVues: 'tout' | 'nouvelles'
  toggleFavoris: 'tout' | 'favoris'
  toggleMatching: 'tout' | 'matching'
}

export const FILTRES_INITIAUX: FiltresState = {
  sources: [],
  contrats: [],
  statuts: [],
  scoreMin: null,
  periode: 'tout',
  motsCles: '',
  lieu: '',
  toggleVues: 'tout',
  toggleFavoris: 'tout',
  toggleMatching: 'tout',
}

export function filtrer(
  offres: Offre[],
  f: FiltresState,
  idsAvecMatching?: Set<number>,
): Offre[] {
  return offres.filter((o) => {
    if (f.sources.length > 0 && o.source && !f.sources.includes(o.source)) {
      return false
    }

    if (f.contrats.length > 0) {
      const ctr = o.type_contrat_clarifie || o.type_contrat || ''
      const match = f.contrats.some((c) => new RegExp(c, 'i').test(ctr))
      if (!match) return false
    }

    if (f.statuts.length > 0 && !f.statuts.includes(o.statut)) return false

    if (f.scoreMin !== null) {
      if (o.score_ia === null || o.score_ia < f.scoreMin) return false
    }

    if (f.periode !== 'tout') {
      const date = new Date(o.date_collecte)
      const now = new Date()
      const diffMs = now.getTime() - date.getTime()
      const seuilMs = f.periode === '24h' ? 24 * 3600 * 1000 : 7 * 24 * 3600 * 1000
      if (diffMs > seuilMs) return false
    }

    if (f.motsCles.trim()) {
      const haystack = [o.titre, o.description, o.entreprise].join(' ').toLowerCase()
      const mots = f.motsCles.trim().toLowerCase().split(/\s+/)
      if (!mots.every((m) => haystack.includes(m))) return false
    }

    if (f.lieu.trim()) {
      if (!o.lieu || !o.lieu.toLowerCase().includes(f.lieu.trim().toLowerCase())) return false
    }

    if (f.toggleVues === 'nouvelles' && o.vue) return false

    if (f.toggleFavoris === 'favoris' && !o.favori) return false

    if (f.toggleMatching === 'matching') {
      if (!idsAvecMatching || !idsAvecMatching.has(o.id)) return false
    }

    return true
  })
}
