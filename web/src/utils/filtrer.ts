import type { Offre } from '../types'

export interface FiltresState {
  sources: string[]
  contrats: string[]
  scoreMin: number | null
  periode: 'tout' | '7j' | '24h'
}

export const FILTRES_INITIAUX: FiltresState = {
  sources: [],
  contrats: [],
  scoreMin: null,
  periode: 'tout',
}

export function filtrer(offres: Offre[], f: FiltresState): Offre[] {
  return offres.filter((o) => {
    if (f.sources.length > 0 && o.source && !f.sources.includes(o.source)) {
      return false
    }

    if (f.contrats.length > 0) {
      const ctr = o.type_contrat_clarifie || o.type_contrat || ''
      const match = f.contrats.some((c) => new RegExp(c, 'i').test(ctr))
      if (!match) return false
    }

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

    return true
  })
}
