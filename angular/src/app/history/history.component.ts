import { Component, Input, Output, EventEmitter, inject, ChangeDetectionStrategy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { PaymentChartComponent } from 'src/shared/components/payment-chart/payment-chart.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { IonIcon } from '@ionic/angular/standalone';
import { IconService } from 'src/shared/services/icon.service';
import { SimulatedTradeService } from '../proxy/trading/simulated-trade.service';
import { TradingSignalrService } from '../services/trading-signalr.service';
import { SimulatedTradeDto, SimulationPerformanceDto } from '../proxy/trading/dtos/models';
import { Subscription, debounceTime, Subject } from 'rxjs';
import { PaginatorComponent } from '../shared/components/paginator/paginator.component';
import { StrategyProfileService } from '../strategies/services/strategy-profile.service';
import { StrategyProfileDto } from '../proxy/trading/dtos/models';

interface ChartData {
  month: string;
  amount: number;
  isGain?: boolean;
}

// Precalculated trade status data – avoids creating new objects per render cycle
const TRADE_STATUS_MAP: Record<number, { circleClass: string; textClass: string; icon: string }> = {
  0: { circleClass: 'payment-circle-primary',  textClass: 'text-primary small fw-medium', icon: 'time-outline' },
  1: { circleClass: 'payment-circle-success',  textClass: 'text-success small fw-medium', icon: 'trending-up-outline' },
  2: { circleClass: 'payment-circle-danger',   textClass: 'text-danger small fw-medium',  icon: 'trending-down-outline' },
  6: { circleClass: 'payment-circle-danger',   textClass: 'text-danger small fw-medium',  icon: 'trending-down-outline' },
};
const TRADE_STATUS_FALLBACK = { circleClass: 'payment-circle-warning', textClass: 'text-warning small fw-medium', icon: 'remove-outline' };

const TRADE_STATUS_LABEL: Record<number, string> = {
  0: 'Trade Abierto',
  1: 'Trade Ganador',
  2: 'Trade Perdedor',
  6: 'Liquidado',
};

@Component({
  selector: 'app-history',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    CardContentComponent,
    PaymentChartComponent,
    GlassButtonComponent,
    IonIcon,
    PaginatorComponent,
    FormsModule
  ],
  templateUrl: './history.component.html',
  styleUrls: ['./history.component.scss']
})
export class HistoryComponent {
  @Input() onBack?: () => void;
  @Output() back = new EventEmitter<void>();

  private iconService  = inject(IconService);
  private tradeService = inject(SimulatedTradeService);
  private signalr      = inject(TradingSignalrService);
  private strategyService = inject(StrategyProfileService);
  private cdr          = inject(ChangeDetectorRef);

  // ── Chart data ────────────────────────────────────────────────────────────
  chartData: ChartData[] = [];
  private subs = new Subscription();

  // ── Raw data ──────────────────────────────────────────────────────────────
  performanceStats?: SimulationPerformanceDto;
  realTrades: SimulatedTradeDto[] = [];
  strategies: StrategyProfileDto[] = [];

  // ── Strategy lookup Map (O(1) vs O(n) find) ───────────────────────────────
  private strategyMap = new Map<string, StrategyProfileDto>();

  // ── Filter state ──────────────────────────────────────────────────────────
  strategyFilter: string = 'all';

  // ── Pagination ────────────────────────────────────────────────────────────
  currentPage: number = 1;
  pageSize: number = 10;

  // ── Cached computed values (recalculated only when data/filter changes) ───
  _filteredTrades: SimulatedTradeDto[] = [];
  _paginatedTrades: SimulatedTradeDto[] = [];
  _strategyChipOptions: { value: string; label: string; color: string }[] = [];
  _totalProfit  = 0;
  _winRate      = 0;
  _totalTrades  = 0;
  _averageProfit = 0;

  // ── Debounce subject for SignalR full-reloads ─────────────────────────────
  private reloadTrigger$ = new Subject<void>();

  // ── Public accessors (template-facing, no computation) ───────────────────
  get filteredTrades()      { return this._filteredTrades; }
  get paginatedTrades()     { return this._paginatedTrades; }
  get strategyChipOptions() { return this._strategyChipOptions; }
  get totalProfit()         { return this._totalProfit; }
  get winRate()             { return this._winRate; }
  get totalTrades()         { return this._totalTrades; }
  get averageProfit()       { return this._averageProfit; }

  // ── Lifecycle ─────────────────────────────────────────────────────────────
  constructor(private router: Router) {}

  ngOnInit() {
    // Debounce full reloads: merge rapid SignalR bursts into one call
    this.subs.add(
      this.reloadTrigger$.pipe(debounceTime(800)).subscribe(() => this.loadData())
    );

    this.loadData();

    // Trigger debounced reload on open/close events
    this.subs.add(this.signalr.tradeOpened$.subscribe(() => this.reloadTrigger$.next()));
    this.subs.add(this.signalr.tradeClosed$.subscribe(() => this.reloadTrigger$.next()));

    // Patch single trade in-place (no full reload needed)
    this.subs.add(this.signalr.tradeUpdate$.subscribe(update => {
      const idx = this.realTrades.findIndex(t => t.id === update.id);
      if (idx !== -1) {
        this.realTrades[idx] = { ...this.realTrades[idx], ...update };
        this.recomputeAll();
        this.cdr.markForCheck();
      }
    }));
  }

  ngOnDestroy() {
    this.subs.unsubscribe();
    this.reloadTrigger$.complete();
  }

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  // ── Data loading ──────────────────────────────────────────────────────────
  loadData() {
    // Load trades
    this.tradeService.getRecentTrades(1000).subscribe({
      next: trades => {
        this.realTrades = trades.sort((a, b) => {
          const da = new Date(a.closedAt || a.openedAt || '').getTime();
          const db = new Date(b.closedAt || b.openedAt || '').getTime();
          return db - da;
        });
        this.recomputeAll();
        this.cdr.markForCheck();
      },
      error: () => this.cdr.markForCheck()
    });

    // Load strategies once (only reload if empty)
    if (this.strategies.length === 0) {
      this.strategyService.getAll().subscribe({
        next: data => {
          this.strategies = data;
          this.strategyMap.clear();
          data.forEach(s => this.strategyMap.set(s.id, s));
          this.recomputeAll();
          this.cdr.markForCheck();
        },
        error: () => {}
      });
    }
  }

  private buildChartData(trades: SimulatedTradeDto[]) {
    const closed = [...trades]
      .filter(t => t.status === 1 || t.status === 2 || t.status === 6)
      .sort((a, b) =>
        new Date(a.closedAt || a.openedAt || '').getTime() -
        new Date(b.closedAt || b.openedAt || '').getTime()
      );

    const newData = closed.map(t => ({
      month: this.formatDateLabel(t.closedAt || t.openedAt || ''),
      amount: t.realizedPnl || 0,
      isGain: (t.realizedPnl || 0) >= 0
    }));

    // Avoid updating the reference if data has not changed, preventing chart flashing
    if (this.areChartsEqual(this.chartData, newData)) {
      return;
    }

    this.chartData = newData;
  }

  private areChartsEqual(a: ChartData[], b: ChartData[]): boolean {
    if (!a || !b || a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (a[i].month !== b[i].month || a[i].amount !== b[i].amount || a[i].isGain !== b[i].isGain) {
        return false;
      }
    }
    return true;
  }

  // ── Single-pass recompute (called after data/filter changes) ──────────────
  private recomputeAll() {
    // 1. Filter
    const filtered = this.strategyFilter === 'all'
      ? this.realTrades.filter(t => this.isStrategyActive(t.strategyProfileId))
      : this.realTrades.filter(t => {
          if (this.strategyFilter === '00000000-0000-0000-0000-000000000000') {
            return (!t.strategyProfileId || t.strategyProfileId === '00000000-0000-0000-0000-000000000000') && this.isStrategyActive(t.strategyProfileId);
          }
          return t.strategyProfileId === this.strategyFilter && this.isStrategyActive(t.strategyProfileId);
        });

    this._filteredTrades = filtered;

    // 2. Rebuild chart from filtered trades (so timeline respects active strategy)
    this.buildChartData(filtered);

    // 3. Paginate
    const start = (this.currentPage - 1) * this.pageSize;
    this._paginatedTrades = filtered.slice(start, start + this.pageSize);

    // 4. Stats – single pass over filtered array
    let profit = 0, wins = 0, closedCount = 0;
    for (const t of filtered) {
      profit += t.realizedPnl || 0;
      if (t.status === 1 || t.status === 2 || t.status === 6) {
        closedCount++;
        if (t.status === 1) wins++;
      }
    }
    this._totalProfit   = profit;
    this._totalTrades   = filtered.length;
    this._winRate       = closedCount > 0 ? Math.round((wins / closedCount) * 100) : 0;
    this._averageProfit = closedCount > 0 ? profit / closedCount : 0;

    // 5. Chip options (stable when strategies haven't changed)
    this._strategyChipOptions = this.strategies.map(s => ({
      value: s.id,
      label: s.name,
      color: s.color || '#00C47D'
    }));
  }

  // ── Public actions ─────────────────────────────────────────────────────────
  setStrategyFilter(value: string) {
    this.strategyFilter = value;
    this.currentPage = 1;
    this.recomputeAll();
  }

  resetPage() {
    this.currentPage = 1;
    this.recomputeAll();
  }

  onPageChange(page: number) {
    this.currentPage = page;
    this.recomputeAll();
  }

  onPageSizeChange(size: number) {
    this.pageSize = size;
    this.currentPage = 1;
    this.recomputeAll();
  }

  // ── TrackBy ──────────────────────────────────────────────────────────────
  trackByTradeId(_: number, trade: SimulatedTradeDto): string {
    return trade.id;
  }

  trackByStrategyId(_: number, opt: { value: string }): string {
    return opt.value;
  }

  // ── Template helpers (pure lookups, no computation) ───────────────────────
  getTradeStatusClass(status: number) {
    return TRADE_STATUS_MAP[status] ?? TRADE_STATUS_FALLBACK;
  }

  getTradeStatusLabel(status: number): string {
    return TRADE_STATUS_LABEL[status] ?? 'Cerrado';
  }

  getDirectionColor(side: number): string {
    return side === 0 ? 'text-success' : 'text-danger';
  }

  getDirectionLabel(side: number): string {
    return side === 0 ? 'LONG' : 'SHORT';
  }

  getProfitColor(pnl: number): string {
    return pnl > 0 ? 'text-success' : pnl < 0 ? 'text-danger' : 'text-white-50';
  }

  getProfitValue(trade: SimulatedTradeDto): number {
    return Number(trade.realizedPnl ?? trade.unrealizedPnl ?? 0);
  }

  // O(1) strategy lookup via Map
  getStrategyLabel(id?: string): string {
    if (!id || id === '00000000-0000-0000-0000-000000000000') return 'Standard Scalping';
    return this.strategyMap.get(id)?.name || 'Unknown';
  }

  getStrategyColor(id?: string): string {
    if (!id || id === '00000000-0000-0000-0000-000000000000') return '#3B82F6';
    return this.strategyMap.get(id)?.color || '#00C47D';
  }

  isStrategyActive(id?: string): boolean {
    if (!id || id === '00000000-0000-0000-0000-000000000000') return true;
    const strategy = this.strategyMap.get(id);
    // Si la estrategia no existe en el map, mostrar los trades (fallback seguro)
    if (!strategy) return true;
    return strategy.isActive;
  }

  formatCurrency(amount: number): string {
    const sign = amount < 0 ? '-' : amount > 0 ? '+' : '';
    return `${sign}$${Math.abs(amount).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  formatDate(dateStr?: string): string {
    if (!dateStr) return '--:--';
    const date = new Date(dateStr);
    const now  = new Date();
    if (date.toDateString() === now.toDateString()) {
      return `Hoy ${date.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })}`;
    }
    return date.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  }

  private formatDateLabel(date: string): string {
    return new Date(date).toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
  }

  getMaxAdversePriceDisplay(trade: SimulatedTradeDto): string {
    if (!trade.maxAdversePrice) return '';
    
    // Calcular la distancia adversa en USDT desde el entry price
    let adverseDistance: number;
    if (trade.side === 0) {
      // LONG: adverse es menor que entry (bajó)
      adverseDistance = trade.maxAdversePrice - trade.entryPrice;
    } else {
      // SHORT: adverse es mayor que entry (subió)
      adverseDistance = trade.entryPrice - trade.maxAdversePrice;
    }
    
    const sign = adverseDistance < 0 ? '-' : '';
    return `${sign}$${Math.abs(adverseDistance).toFixed(2)}`;
  }

  getMaxAdversePriceColor(trade: SimulatedTradeDto): string {
    if (!trade.maxAdversePrice) return '';
    
    // Calcular la distancia adversa
    let adverseDistance: number;
    if (trade.side === 0) {
      adverseDistance = trade.maxAdversePrice - trade.entryPrice;
    } else {
      adverseDistance = trade.entryPrice - trade.maxAdversePrice;
    }
    
    // Si la distancia es negativa (adversa), mostrar en warning
    return adverseDistance < 0 ? 'text-warning' : 'text-white-50';
  }

  viewInChart(symbol: string): void {
    this.router.navigate(['/dashboard'], { queryParams: { symbol: symbol.replace('/', '') } });
  }

  handleBack(): void {
    if (this.onBack) this.onBack();
    else this.router.navigate(['/']);
    this.back.emit();
  }
}