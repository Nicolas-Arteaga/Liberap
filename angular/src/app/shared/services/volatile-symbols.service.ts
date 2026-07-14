import { Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { BINANCE_FUTURES_PAIRS } from '../models/models-shared';

interface BinanceTickerLite {
  symbol: string;
  priceChangePercent: number;
}

/**
 * Fuente única de "cuáles símbolos mirar" para cualquier scan manual del
 * frontend. Reemplaza la lista estática BINANCE_FUTURES_PAIRS (~100 pares
 * fijos, nunca incluye un token nuevo/volátil) por un ranking en vivo
 * contra /market/tickers — mismo criterio que ya usa el watchlist del
 * agente (config.py: _fetch_top_volatile_symbols) y el "Top Scan" de
 * Nexus-15 (Nexus15AppService.AnalyzeTopAvailableAsync).
 */
@Injectable({ providedIn: 'root' })
export class VolatileSymbolsService {
  private readonly pythonUrl = (environment as { pythonAiUrl?: string }).pythonAiUrl ?? 'http://localhost:8005';

  getMostVolatile(limit: number): Promise<string[]> {
    return fetch(`${this.pythonUrl}/market/tickers`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((tickers: BinanceTickerLite[]) => {
        if (!Array.isArray(tickers) || tickers.length === 0) throw new Error('sin tickers');
        return [...tickers]
          .sort((a, b) => Math.abs(b.priceChangePercent) - Math.abs(a.priceChangePercent))
          .slice(0, limit)
          .map(t => t.symbol);
      })
      .catch((e) => {
        console.error('[VolatileSymbols] No se pudo traer tickers para rankear volatilidad, uso lista estática:', e);
        return BINANCE_FUTURES_PAIRS.slice(0, limit);
      });
  }
}
