"""
Moteur de matching offre ↔ CV — 100% gratuit, basé sur TF-IDF.

TF-IDF = technique mathématique qui mesure la similarité entre deux textes.
Pas d'IA nécessaire : assez performant pour comparer des CVs à des offres.
Coût : 0 €
"""

import logging

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class MoteurMatching:
    def __init__(self, profils: list[dict]):
        """
        profils : liste de {'nom_fichier': ..., 'nom_candidat': ..., 'texte': ...}
        """
        self.profils = profils
        self.vectorizer = None
        self.matrix_cvs = None

        if profils:
            self._indexer()

    def _indexer(self):
        """Convertit tous les CVs en vecteurs numériques."""
        textes = [p["texte"] for p in self.profils]
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),       # Considère les bi-grammes ("chef projet", "business analyst")
            max_features=8000,
            sublinear_tf=True,        # Réduit l'importance des mots trop fréquents
            min_df=1,
        )
        self.matrix_cvs = self.vectorizer.fit_transform(textes)
        logger.info("Index de matching créé pour %d CV(s)", len(self.profils))

    def trouver_meilleurs_profils(self, offre: dict, top_n: int = 3) -> list[dict]:
        """
        Retourne les N candidats les mieux adaptés à l'offre.

        Résultat : liste de dicts {'nom_candidat': ..., 'score_matching': ..., 'nom_fichier': ...}
        """
        if not self.profils or self.vectorizer is None:
            return []

        texte_offre = f"{offre.get('titre', '')} {offre.get('description', '')} {offre.get('resume_ia', '')}"
        vecteur_offre = self.vectorizer.transform([texte_offre])

        similarites = cosine_similarity(vecteur_offre, self.matrix_cvs).flatten()

        indices_tries = np.argsort(similarites)[::-1][:top_n]

        resultats = []
        for idx in indices_tries:
            score = float(similarites[idx])
            if score > 0.05:  # Seuil minimal pour éviter les matchings sans sens
                resultats.append({
                    "nom_candidat": self.profils[idx]["nom_candidat"],
                    "nom_fichier": self.profils[idx]["nom_fichier"],
                    "score_matching": round(score * 100, 1),  # En pourcentage
                })

        return resultats
