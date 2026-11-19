import { useEffect, useMemo, useState } from 'react'
import type { CompteurCandidat, OffreManuelleResultat } from '../api'
import { fetchCompteurs, fetchOffres } from '../api'
import Filtres from '../components/Filtres'
import ModaleAjoutOffre from '../components/ModaleAjoutOffre'
import ModaleCandidats from '../components/ModaleCandidats'
import OffreCard from '../components/OffreCard'
import type { Offre } from '../types'
import { filtrer, FILTRES_INITIAUX } from '../utils/filtrer'
import type { FiltresState } from '../utils/filtrer'

export default function PageOffres() {
  const [offres, setOffres] = useState<Offre[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filtres, setFiltres] = useState<FiltresState>(FILTRES_INITIAUX)
  const [compteurs, setCompteurs] = useState<Record<number, CompteurCandidat>>({})
  const [modaleOuverte, setModaleOuverte] = useState<{
    offreId: number
    titreOffre: string
    avertissement?: string
  } | null>(null)
  const [ajoutOuvert, setAjoutOuvert] = useState(false)

  // Les offres périmées ne sont chargées que si le filtre avancé les demande
  const afficherPerimees = filtres.afficherPerimees
  useEffect(() => {
    Promise.all([fetchOffres(afficherPerimees), fetchCompteurs(30, afficherPerimees)])
      .then(([offresData, compteursData]) => {
        setOffres(offresData)
        setCompteurs(compteursData)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [afficherPerimees])

  const idsAvecMatching = useMemo(
    () => new Set(Object.keys(compteurs).map(Number)),
    [compteurs],
  )

  const nbAvecMatching = idsAvecMatching.size

  const offresFiltrees = useMemo(
    () => filtrer(offres, filtres, idsAvecMatching),
    [offres, filtres, idsAvecMatching],
  )

  function handleUpdate(offre: Offre) {
    setOffres((prev) => prev.map((o) => (o.id === offre.id ? offre : o)))
  }

  function handleOuvrirCandidats(offreId: number, titreOffre: string) {
    setModaleOuverte({ offreId, titreOffre })
  }

  function handleOffreAjoutee(resultat: OffreManuelleResultat) {
    setAjoutOuvert(false)
    // L'offre (nouvelle ou mise à jour) en tête de liste, filtres remis à zéro pour qu'elle soit visible
    setOffres((prev) => [resultat.offre, ...prev.filter((o) => o.id !== resultat.id)])
    setFiltres(FILTRES_INITIAUX)
    fetchCompteurs(30).then(setCompteurs).catch(() => {})
    // Ouverture directe de la fiche de l'offre, avec ses candidats classés
    setModaleOuverte({
      offreId: resultat.id,
      titreOffre: resultat.titre,
      avertissement: resultat.structuration_reussie
        ? undefined
        : "L'offre est enregistrée, mais ses champs n'ont pas pu être structurés automatiquement : ils sont à compléter à la main.",
    })
  }

  return (
    <>
      {!loading && !error && offres.length > 0 && (
        <Filtres
          offres={offres}
          filtres={filtres}
          onChange={setFiltres}
          nbAffichees={offresFiltrees.length}
          nbAvecMatching={nbAvecMatching}
        />
      )}

      <main className="flex-1 p-6 md:p-8">
        <div className="flex justify-end mb-4">
          <button
            onClick={() => setAjoutOuvert(true)}
            className="text-sm font-semibold bg-adh-orange text-white rounded-lg px-4 py-2 hover:opacity-90 transition-opacity shadow"
          >
            + Ajouter une annonce
          </button>
        </div>

        {loading && (
          <p className="text-center text-gray-400 mt-16 text-lg">Chargement des offres...</p>
        )}

        {!loading && error && (
          <div className="max-w-lg mx-auto mt-16 text-center">
            <p className="text-red-500 font-medium mb-2">Impossible de charger les offres</p>
            <p className="text-gray-500 text-sm mb-1">{error}</p>
            <p className="text-gray-400 text-sm">
              Vérifiez que le backend est lancé :{' '}
              <span className="font-mono">http://localhost:8000/health</span>
            </p>
          </div>
        )}

        {!loading && !error && offres.length === 0 && (
          <p className="text-center text-gray-400 mt-16 text-lg">Aucune offre disponible pour le moment</p>
        )}

        {!loading && !error && offres.length > 0 && offresFiltrees.length === 0 && (
          <div className="text-center mt-16">
            <p className="text-gray-400 text-lg mb-3">Aucune offre ne correspond aux filtres</p>
            <button
              onClick={() => setFiltres(FILTRES_INITIAUX)}
              className="text-sm font-semibold text-adh-orange hover:underline"
            >
              Réinitialiser les filtres
            </button>
          </div>
        )}

        {!loading && !error && offresFiltrees.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {offresFiltrees.map((offre) => (
              <OffreCard
                key={offre.id}
                offre={offre}
                onUpdate={handleUpdate}
                compteur={compteurs[offre.id]}
                onOuvrirCandidats={handleOuvrirCandidats}
              />
            ))}
          </div>
        )}
      </main>

      {modaleOuverte && (
        <ModaleCandidats
          offreId={modaleOuverte.offreId}
          titreOffre={modaleOuverte.titreOffre}
          avertissement={modaleOuverte.avertissement}
          onClose={() => setModaleOuverte(null)}
        />
      )}

      {ajoutOuvert && (
        <ModaleAjoutOffre onClose={() => setAjoutOuvert(false)} onOffreAjoutee={handleOffreAjoutee} />
      )}
    </>
  )
}
