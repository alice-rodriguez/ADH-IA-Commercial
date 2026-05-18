import { useMemo } from 'react'
import type { Offre } from '../types'
import { FILTRES_INITIAUX } from '../utils/filtrer'
import type { FiltresState } from '../utils/filtrer'

const SOURCE_COLORS: Record<string, string> = {
  'APEC': 'bg-blue-500 text-white',
  'Free-Work': 'bg-orange-400 text-white',
  'Welcome to the Jungle': 'bg-green-500 text-white',
}

const CONTRAT_COLORS: Array<[RegExp, string]> = [
  [/freelance|indépendant|independant/i, 'bg-adh-orange text-white'],
  [/cdi/i,                                'bg-green-500 text-white'],
  [/cdd/i,                                'bg-adh-violet text-adh-black'],
  [/stage|alternance|apprentissage/i,     'bg-blue-300 text-adh-black'],
]

const STATUT_OPTIONS = [
  { label: 'Nouveau',  value: 'nouveau',  classes: 'bg-gray-300 text-adh-black' },
  { label: 'En cours', value: 'en_cours', classes: 'bg-blue-300 text-adh-black' },
  { label: 'Envoyé',   value: 'envoye',   classes: 'bg-green-300 text-adh-black' },
  { label: 'Rejeté',   value: 'rejete',   classes: 'bg-red-300 text-adh-black' },
]

function sourceBadgeClass(source: string): string {
  return SOURCE_COLORS[source] || 'bg-gray-400 text-white'
}

function contratBadgeClass(contrat: string): string {
  for (const [regex, classes] of CONTRAT_COLORS) {
    if (regex.test(contrat)) return classes
  }
  return 'bg-gray-300 text-adh-black'
}

const SCORE_OPTIONS: { label: string; value: number | null }[] = [
  { label: 'Tout', value: null },
  { label: '≥ 60', value: 60 },
  { label: '≥ 80', value: 80 },
]

const PERIODE_OPTIONS: { label: string; value: FiltresState['periode'] }[] = [
  { label: 'Tout', value: 'tout' },
  { label: '7 jours', value: '7j' },
  { label: '24h', value: '24h' },
]

interface Props {
  offres: Offre[]
  filtres: FiltresState
  onChange: (filtres: FiltresState) => void
  nbAffichees: number
}

export default function Filtres({ offres, filtres, onChange, nbAffichees }: Props) {
  const sources = useMemo(() => {
    const set = new Set<string>()
    offres.forEach((o) => { if (o.source) set.add(o.source) })
    return Array.from(set).sort()
  }, [offres])

  const contrats = useMemo(() => {
    const set = new Set<string>()
    offres.forEach((o) => {
      const c = o.type_contrat_clarifie || o.type_contrat
      if (c) set.add(c)
    })
    return Array.from(set).sort()
  }, [offres])

  const nbNouvelles = useMemo(
    () => offres.filter((o) => !o.vue).length,
    [offres]
  )

  const nbFavoris = useMemo(
    () => offres.filter((o) => o.favori).length,
    [offres]
  )

  function toggleSource(source: string) {
    const next = filtres.sources.includes(source)
      ? filtres.sources.filter((s) => s !== source)
      : [...filtres.sources, source]
    onChange({ ...filtres, sources: next })
  }

  function toggleContrat(contrat: string) {
    const next = filtres.contrats.includes(contrat)
      ? filtres.contrats.filter((c) => c !== contrat)
      : [...filtres.contrats, contrat]
    onChange({ ...filtres, contrats: next })
  }

  function toggleStatut(statut: string) {
    const next = filtres.statuts.includes(statut)
      ? filtres.statuts.filter((s) => s !== statut)
      : [...filtres.statuts, statut]
    onChange({ ...filtres, statuts: next })
  }

  const isFiltreActif = nbAffichees < offres.length

  return (
    <div className="sticky top-0 z-10 bg-white border-b shadow-sm p-4">
      <div className="flex flex-wrap gap-6 md:items-start">

        {/* Source */}
        <div>
          <p className="text-xs font-bold uppercase text-gray-500 mb-1">Source</p>
          <div className="flex flex-wrap gap-2">
            {sources.map((src) => (
              <label key={src} className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={filtres.sources.includes(src)}
                  onChange={() => toggleSource(src)}
                  className="w-3.5 h-3.5 accent-[#ff914d]"
                />
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${sourceBadgeClass(src)}`}>
                  {src}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* Contrat */}
        <div>
          <p className="text-xs font-bold uppercase text-gray-500 mb-1">Contrat</p>
          <div className="flex flex-wrap gap-2">
            {contrats.map((ctr) => (
              <label key={ctr} className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={filtres.contrats.includes(ctr)}
                  onChange={() => toggleContrat(ctr)}
                  className="w-3.5 h-3.5 accent-[#ff914d]"
                />
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${contratBadgeClass(ctr)}`}>
                  {ctr}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* Statut */}
        <div>
          <p className="text-xs font-bold uppercase text-gray-500 mb-1">Statut</p>
          <div className="flex flex-wrap gap-2">
            {STATUT_OPTIONS.map((opt) => (
              <label key={opt.value} className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={filtres.statuts.includes(opt.value)}
                  onChange={() => toggleStatut(opt.value)}
                  className="w-3.5 h-3.5 accent-[#ff914d]"
                />
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${opt.classes}`}>
                  {opt.label}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* Score IA */}
        <div>
          <p className="text-xs font-bold uppercase text-gray-500 mb-1">Score IA</p>
          <div className="flex gap-1">
            {SCORE_OPTIONS.map((opt) => (
              <button
                key={opt.label}
                onClick={() => onChange({ ...filtres, scoreMin: opt.value })}
                className={`text-xs px-3 py-1 rounded-full border font-medium transition-colors ${
                  filtres.scoreMin === opt.value
                    ? 'bg-adh-orange text-white border-adh-orange'
                    : 'bg-white text-adh-black border-gray-300 hover:border-adh-orange'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Période */}
        <div>
          <p className="text-xs font-bold uppercase text-gray-500 mb-1">Période</p>
          <div className="flex gap-1">
            {PERIODE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => onChange({ ...filtres, periode: opt.value })}
                className={`text-xs px-3 py-1 rounded-full border font-medium transition-colors ${
                  filtres.periode === opt.value
                    ? 'bg-adh-orange text-white border-adh-orange'
                    : 'bg-white text-adh-black border-gray-300 hover:border-adh-orange'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Mots-clés */}
        <div>
          <p className="text-xs font-bold uppercase text-gray-500 mb-1">Mots-clés</p>
          <div className="relative">
            <svg
              className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none"
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
            </svg>
            <input
              type="text"
              value={filtres.motsCles}
              onChange={(e) => onChange({ ...filtres, motsCles: e.target.value })}
              placeholder="SAP, MOA banque..."
              className="w-56 pl-7 pr-2 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:border-adh-orange"
            />
          </div>
        </div>

        {/* Lieu */}
        <div>
          <p className="text-xs font-bold uppercase text-gray-500 mb-1">Lieu</p>
          <input
            type="text"
            value={filtres.lieu}
            onChange={(e) => onChange({ ...filtres, lieu: e.target.value })}
            placeholder="Paris, remote..."
            className="w-40 px-2 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:border-adh-orange"
          />
        </div>

        {/* Vues */}
        <div>
          <p className="text-xs font-bold uppercase text-gray-500 mb-1">Vues</p>
          <div className="flex gap-1">
            {(['tout', 'nouvelles'] as const).map((val) => (
              <button
                key={val}
                onClick={() => onChange({ ...filtres, toggleVues: val })}
                className={`text-xs px-3 py-1 rounded-full border font-medium transition-colors ${
                  filtres.toggleVues === val
                    ? 'bg-adh-orange text-white border-adh-orange'
                    : 'bg-white text-adh-black border-gray-300 hover:border-adh-orange'
                }`}
              >
                {val === 'tout' ? 'Tout' : `Nouvelles (${nbNouvelles})`}
              </button>
            ))}
          </div>
        </div>

        {/* Favoris */}
        <div>
          <p className="text-xs font-bold uppercase text-gray-500 mb-1">Favoris</p>
          <div className="flex gap-1">
            {(['tout', 'favoris'] as const).map((val) => (
              <button
                key={val}
                onClick={() => onChange({ ...filtres, toggleFavoris: val })}
                className={`text-xs px-3 py-1 rounded-full border font-medium transition-colors ${
                  filtres.toggleFavoris === val
                    ? 'bg-adh-orange text-white border-adh-orange'
                    : 'bg-white text-adh-black border-gray-300 hover:border-adh-orange'
                }`}
              >
                {val === 'tout' ? 'Tout' : `★ Favoris (${nbFavoris})`}
              </button>
            ))}
          </div>
        </div>

        {/* Compteur + reset */}
        <div className="ml-auto flex items-center gap-3 self-center">
          <span className="text-sm text-gray-500">
            <span className="font-semibold text-adh-black">{nbAffichees}</span>
            {' '}affichée{nbAffichees > 1 ? 's' : ''} sur {offres.length}
          </span>
          {isFiltreActif && (
            <button
              onClick={() => onChange(FILTRES_INITIAUX)}
              className="text-xs font-semibold text-adh-orange hover:underline"
            >
              Réinitialiser les filtres
            </button>
          )}
        </div>

      </div>
    </div>
  )
}
