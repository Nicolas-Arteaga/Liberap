import { Injectable, inject } from '@angular/core';
import { StrategyProfileService as ProxyService } from '../../proxy/trading/strategy-profile.service';
import { CreateUpdateStrategyProfileDto, StrategyProfileDto } from '../../proxy/trading/dtos/models';
import { map } from 'rxjs/operators';
import { Observable, of } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class StrategyProfileService {
  private proxy = inject(ProxyService);

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
    // Mock performance data for now as requested by UI structure
    // In a real scenario, this would call a backend endpoint
    return of({
      equityCurve: [100, 105, 102, 110, 108, 115],
      winRate: 65.4,
      totalTrades: 42,
      netPnL: 15.2,
      avgRR: 2.1,
      topSymbols: [
        { symbol: 'BTCUSDT', pnl: 120 },
        { symbol: 'ETHUSDT', pnl: 85 },
        { symbol: 'SOLUSDT', pnl: -30 }
      ]
    });
  }
}
