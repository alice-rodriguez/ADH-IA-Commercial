import { useState } from 'react'

const CLE_STORAGE = 'adh-offres-vues'

function charger(): Set<number> {
  try {
    const raw = localStorage.getItem(CLE_STORAGE)
    if (!raw) return new Set()
    return new Set(JSON.parse(raw) as number[])
  } catch {
    return new Set()
  }
}

export function useVues(): [Set<number>, (id: number) => void] {
  const [vues, setVues] = useState<Set<number>>(charger)

  function markVue(id: number) {
    setVues((prev) => {
      if (prev.has(id)) return prev
      const next = new Set(prev)
      next.add(id)
      try {
        localStorage.setItem(CLE_STORAGE, JSON.stringify(Array.from(next)))
      } catch {
        // localStorage indisponible, état en mémoire seulement
      }
      return next
    })
  }

  return [vues, markVue]
}
