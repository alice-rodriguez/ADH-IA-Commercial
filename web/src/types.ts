export interface Offre {
  id: number
  titre: string
  entreprise: string | null
  lieu: string | null
  type_contrat: string | null
  type_contrat_clarifie: string | null
  source: string | null
  url: string | null
  description: string | null
  resume_ia: string | null
  score_ia: number | null
  tjm_min: number | null
  tjm_max: number | null
  salaire_min: number | null
  salaire_max: number | null
  date_collecte: string
  vue: boolean
  favori: boolean
  statut: string
  notes: string | null
}
