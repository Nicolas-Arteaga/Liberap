import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { StrategyProfileService } from '../../services/strategy-profile.service';
import { StrategyProfileDto, SimulatedTradeDto } from '../../../proxy/trading/dtos/models';
import { IonIcon } from '@ionic/angular/standalone';
import { finalize } from 'rxjs/operators';
import { SimulatedTradeService } from '../../../proxy/trading/simulated-trade.service';

@Component({
  selector: 'app-strategies-dashboard',
  standalone: true,
  imports: [CommonModule, IonIcon],
  templateUrl: './strategies-dashboard.component.html',
  styleUrls: ['./strategies-dashboard.component.scss']
})
export class StrategiesDashboardComponent implements OnInit {
  private service = inject(StrategyProfileService);
  private tradeService = inject(SimulatedTradeService);
  private router = inject(Router);

  profiles: StrategyProfileDto[] = [];
  trades: SimulatedTradeDto[] = [];
  standardStats = {
    winRate: 0,
    totalTrades: 0,
    netPnL: 0,
    avgRR: 0,
    evidenceDays: 0
  };
  isLoading = false;

  ngOnInit() {
    this.loadProfiles();
  }

  loadProfiles() {
    this.isLoading = true;
    this.service.getAll()
      .subscribe(data => {
        this.profiles = data.filter(p => p.id !== '00000000-0000-0000-0000-000000000000');
        this.loadTrades();
      });
  }

  loadTrades() {
    this.tradeService.getTradeHistory()
      .pipe(finalize(() => this.isLoading = false))
      .subscribe(history => {
        this.trades = history;
        this.enrichProfilesWithStats();
      });
  }

  enrichProfilesWithStats() {
    // A strategy ranking must be based on realized currency PnL.  Summing
    // per-trade ROI percentages mixes margins/leverage and is not portfolio PnL.
    // Only closed trades are evidence for performance.
    const closedTrades = this.trades.filter(t => !!t.closedAt);
    const evidenceDays = (trades: SimulatedTradeDto[]): number => {
      const dates = trades
        .map(t => t.closedAt ? new Date(t.closedAt).getTime() : NaN)
        .filter(Number.isFinite);
      if (dates.length < 2) return dates.length ? 1 : 0;
      return Math.max(1, Math.ceil((Math.max(...dates) - Math.min(...dates)) / 86_400_000));
    };

    // Calculate for Standard (Legacy) - strategyProfileId is null or Guid.Empty
    const standardTrades = closedTrades.filter(t => !t.strategyProfileId || t.strategyProfileId === '00000000-0000-0000-0000-000000000000');
    if (standardTrades.length > 0) {
      const wins = standardTrades.filter(t => (t.realizedPnl || 0) > 0).length;
      this.standardStats = {
        winRate: (wins / standardTrades.length) * 100,
        totalTrades: standardTrades.length,
        netPnL: standardTrades.reduce((acc, t) => acc + (t.realizedPnl || 0), 0),
        avgRR: 0,
        evidenceDays: evidenceDays(standardTrades)
      };
    }

    this.profiles.forEach(p => {
      const pTrades = closedTrades.filter(t => t.strategyProfileId === p.id);
      if (pTrades.length > 0) {
        const wins = pTrades.filter(t => (t.realizedPnl || 0) > 0).length;
        p.winRate = (wins / pTrades.length) * 100;
        p.totalTrades = pTrades.length;
        p.netPnL = pTrades.reduce((acc, t) => acc + (t.realizedPnl || 0), 0);
        p.avgRR = 0; 
        (p as StrategyProfileDto & { evidenceDays?: number }).evidenceDays = evidenceDays(pTrades);
      } else {
        p.winRate = 0;
        p.totalTrades = 0;
        p.netPnL = 0;
        p.avgRR = 0;
        (p as StrategyProfileDto & { evidenceDays?: number }).evidenceDays = 0;
      }
    });
  }

  onNewStrategy() {
    this.router.navigate(['/strategies/new']);
  }

  onEdit(id: string) {
    this.router.navigate(['/strategies/edit', id]);
  }

  onDuplicate(id: string) {
    this.service.duplicate(id).subscribe(() => this.loadProfiles());
  }

  onDelete(id: string) {
    if (confirm('¿Estás seguro de eliminar este perfil de estrategia?')) {
      this.service.delete(id).subscribe(() => this.loadProfiles());
    }
  }

  onToggle(id: string) {
    this.service.toggleActive(id).subscribe(() => {
      const p = this.profiles.find(x => x.id === id);
      if (p) p.isActive = !p.isActive;
    });
  }

  viewPerformance(id: string) {
    this.router.navigate(['/strategies/performance', id]);
  }

  trackById(index: number, profile: StrategyProfileDto) {
    return profile.id;
  }

  get activeProfilesCount() {
    return this.profiles.filter(p => p.isActive).length;
  }

  get totalNetPnL() {
    return this.profiles.reduce((acc, curr) => acc + (curr.netPnL || 0), 0);
  }

  get totalTrades() {
    return this.profiles.reduce((acc, curr) => acc + (curr.totalTrades || 0), 0);
  }

  get globalWinRate() {
    const active = this.profiles.filter(p => (p.totalTrades || 0) > 0);
    if (!active.length) return 0;
    return active.reduce((acc, p) => acc + (p.winRate || 0), 0) / active.length;
  }

  get bestProfile(): StrategyProfileDto | null {
    if (!this.profiles.length) return null;
    return [...this.profiles].sort((a, b) => (b.netPnL || 0) - (a.netPnL || 0))[0];
  }

  profileEvidenceDays(profile: StrategyProfileDto): number {
    return (profile as StrategyProfileDto & { evidenceDays?: number }).evidenceDays || 0;
  }

  profileIdentity(profile: StrategyProfileDto): string {
    // The id suffix makes reconstructed profiles with the same display name
    // distinguishable until the user deliberately renames/merges them.
    return `${profile.name || 'Sin nombre'} · ${profile.id?.slice(0, 8) || 'sin-id'}`;
  }
}
