# ADH Veille — Frontend

Interface web de consultation quotidienne des offres de missions IT collectées par le pipeline
de veille ADH PM Consulting. Construit avec React + Vite + TypeScript + Tailwind CSS.

## Pré-requis

- Node.js 18+
- npm 8+

## Installation locale

```bash
cd web
npm install
```

## Lancement en développement

```bash
npm run dev
```

## URL locale

```
http://localhost:5173
```

> L'API backend doit tourner sur http://localhost:8000 pour que les futurs endpoints
> fonctionnent. Voir [api/README.md](../api/README.md).

## Build de production

```bash
npm run build
```

Génère le bundle optimisé dans `web/dist/`.

## Charte graphique ADH

| Couleur | Hex       | Usage                       |
|---------|-----------|-----------------------------|
| Noir    | `#000000` | Header, textes principaux   |
| Blanc   | `#FFFFFF` | Fond général                |
| Orange  | `#ff914d` | Accents, scores, CTA        |
| Violet  | `#d6a9cf` | Accents secondaires, badges |

Ces couleurs sont configurées dans `tailwind.config.js` sous la clé `adh`.
