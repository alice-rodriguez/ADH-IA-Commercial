import type { Offre } from '../types'

const SOURCE_COLORS: Record<string, string> = {
  'APEC': 'bg-blue-500 text-white',
  'Free-Work': 'bg-orange-400 text-white',
  'Welcome to the Jungle': 'bg-green-500 text-white',
}

function sourceBadgeClass(source: string | null): string {
  if (!source) return 'bg-gray-400 text-white'
  return SOURCE_COLORS[source] || 'bg-gray-400 text-white'
}

function scoreColor(score: number | null): string {
  if (score === null) return ''
  if (score >= 80) return 'text-adh-orange'
  if (score >= 60) return 'text-orange-300'
  return 'text-gray-400'
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`
}

function excerpt(offre: Offre): string {
  const text = offre.resume_ia || offre.description || 'Pas de description'
  return text.length > 200 ? text.slice(0, 200) + '…' : text
}

interface Props {
  offre: Offre
}

export default function OffreCard({ offre }: Props) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-md hover:shadow-lg transition-shadow p-5 flex flex-col gap-3">

      {/* Ligne source + score */}
      <div className="flex items-start justify-between gap-2">
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${sourceBadgeClass(offre.source)}`}>
          {offre.source || 'Source inconnue'}
        </span>
        {offre.score_ia !== null && (
          <span className={`text-2xl font-bold leading-none ${scoreColor(offre.score_ia)}`}>
            {offre.score_ia}
          </span>
        )}
      </div>

      {/* Titre + entreprise */}
      <div>
        <h3 className="text-xl font-bold text-adh-black leading-tight">{offre.titre}</h3>
        {offre.entreprise && (
          <p className="text-sm text-gray-600 mt-0.5">{offre.entreprise}</p>
        )}
      </div>

      {/* Métadonnées */}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {offre.type_contrat && (
          <span className="bg-adh-violet text-adh-black text-xs font-medium px-2 py-0.5 rounded-full">
            {offre.type_contrat_clarifie || offre.type_contrat}
          </span>
        )}
        {offre.lieu && (
          <span className="text-gray-500">{offre.lieu}</span>
        )}
        <span className="text-gray-400 ml-auto">{formatDate(offre.date_collecte)}</span>
      </div>

      {/* Description */}
      <p className="text-sm text-gray-600 flex-1">{excerpt(offre)}</p>

      {/* Bouton */}
      {offre.url ? (
        <a
          href={offre.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-auto inline-block text-sm font-semibold text-adh-orange hover:underline"
        >
          Voir l'offre →
        </a>
      ) : (
        <span className="mt-auto text-sm text-gray-300 cursor-not-allowed">
          Voir l'offre →
        </span>
      )}
    </div>
  )
}
