import { Injectable, signal } from '@angular/core';

/**
 * Favoritos de estrategias — persistidos en localStorage, compartidos entre
 * Dashboard e Historial (pedido 2026-08-16: una estrellita para marcar
 * cualquier estrategia como favorita desde cualquiera de las dos pantallas,
 * que aparezca primero en ambas). No hay concepto de "favorito" en el
 * backend -- es puramente de UI/cliente, no vale la pena un campo en DB
 * para esto.
 */
const STORAGE_KEY = 'verge_favorite_strategies';

@Injectable({ providedIn: 'root' })
export class FavoriteStrategiesService {
  private readonly favorites = signal<Set<string>>(this.load());

  private load(): Set<string> {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? new Set(JSON.parse(raw)) : new Set();
    } catch {
      return new Set();
    }
  }

  private persist(): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...this.favorites()]));
    } catch {
      // localStorage no disponible (modo privado, cuota llena) -- degrada
      // a "sin favoritos persistentes" en vez de romper la UI.
    }
  }

  isFavorite(id: string | null | undefined): boolean {
    if (!id) return false;
    return this.favorites().has(id);
  }

  toggle(id: string | null | undefined): void {
    if (!id) return;
    const next = new Set(this.favorites());
    if (next.has(id)) next.delete(id);
    else next.add(id);
    this.favorites.set(next);
    this.persist();
  }

  /** Ordena favoritos primero, preservando el orden relativo dentro de cada grupo. */
  sortFavoritesFirst<T>(items: T[], idFn: (item: T) => string | null | undefined): T[] {
    const favs = this.favorites();
    return [...items].sort((a, b) => {
      const fa = favs.has(idFn(a) || '') ? 1 : 0;
      const fb = favs.has(idFn(b) || '') ? 1 : 0;
      return fb - fa;
    });
  }
}
