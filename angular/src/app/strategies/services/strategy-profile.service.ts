import { Injectable, inject } from '@angular/core';
import { StrategyProfileService as ProxyService } from '../../proxy/trading/strategy-profile.service';
import { SimulatedTradeService as ProxyTradeService } from '../../proxy/trading/simulated-trade.service';
import { CreateUpdateStrategyProfileDto, StrategyProfileDto } from '../../proxy/trading/dtos/models';
import { map } from 'rxjs/operators';
import { Observable, of } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class StrategyProfileService {
  private proxy = inject(ProxyService);
  private tradeService = inject(ProxyTradeService);

  getAll() {
    return this.proxy.getList();
  }

  getById(id: string) {
    return this.proxy.get(id);
  }

  create(profile: CreateUpdateStrategyProfileDto) {
    return this.proxy.create(profile);
  }

  update(id: string, profile: CreateUpdateStrategyProfileDto) {
    return this.proxy.update(id, profile);
  }

  delete(id: string) {
    return this.proxy.delete(id);
  }

  toggleActive(id: string) {
    return this.proxy.toggleActive(id);
  }

  duplicate(id: string) {
    return this.getById(id).pipe(
      map(p => {
        const copy: CreateUpdateStrategyProfileDto = {
          ...p,
          name: `${p.name} (Copia)`,
          isActive: false
        };
        return copy;
      }),
      map(copy => this.create(copy))
    );
  }

  getPerformance(id: string): Observable<any> {
    return this.tradeService.getTradeHistory().pipe(
      map(history => {
        // Filter history by strategy (Standard Scalping uses null id)
        const profileId = id === 'standard' ? null : id;
        const trades = history.filter(t => t.strategyProfileId === profileId);

        if (trades.length === 0) {
          return {
            winRate: 0,
            totalTrades: 0,
            netPnL: 0,
            avgRR: 0,
            topSymbols: [],
            equityCurve: []
          };
        }

        const wins = trades.filter(t => (t.realizedPnl || 0) > 0).length;
        const netPnL = trades.reduce((acc, t) => acc + (t.roiPercentage || 0), 0);
        
        // Calculate Top Symbols
        const symbolStats = trades.reduce((acc: any, t) => {
          if (!t.symbol) return acc;
          acc[t.symbol] = (acc[t.symbol] || 0) + (t.realizedPnl || 0);
          return acc;
        }, {});

        const topSymbols = Object.keys(symbolStats)
          .map(symbol => ({ symbol, pnl: symbolStats[symbol] }))
          .sort((a, b) => b.pnl - a.pnl)
          .slice(0, 5);

        // Simple equity curve (cumulative ROI)
        let cumulative = 100;
        const equityCurve = trades.map(t => {
          cumulative += (t.roiPercentage || 0);
          return cumulative;
        });

        return {
          winRate: (wins / trades.length) * 100,
          totalTrades: trades.length,
          netPnL: netPnL,
          avgRR: trades.reduce((acc, t) => acc + (t.roiPercentage || 0), 0) / trades.length, // Rough avg ROI
          topSymbols: topSymbols,
          equityCurve: equityCurve,
          allTrades: trades.sort((a, b) => new Date(b.openedAt!).getTime() - new Date(a.openedAt!).getTime())
        };
      })
    );
  }
}
