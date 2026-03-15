import { Component, Input, Output, EventEmitter, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { SelectComponent } from 'src/shared/components/select/select.component';
import { PaymentChartComponent } from 'src/shared/components/payment-chart/payment-chart.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { IonIcon } from '@ionic/angular/standalone';
import { IconService } from 'src/shared/services/icon.service';
import { LabelComponent } from "src/shared/components/label/label.component";
import { SimulatedTradeService } from '../proxy/trading/simulated-trade.service';
import { TradingSignalrService } from '../services/trading-signalr.service';
import { SimulatedTradeDto, SimulationPerformanceDto } from '../proxy/trading/dtos/models';
import { Subscription } from 'rxjs';

interface FilterOption {
  value: string;
  label: string;
}

interface ChartData {
  month: string;
  amount: number;
}

// Interface removed as we use DTOs

@Component({
  selector: 'app-history',
  standalone: true,
  imports: [
    CommonModule,
    CardContentComponent,
    SelectComponent,
    PaymentChartComponent,
    GlassButtonComponent,
    IonIcon,
    LabelComponent
  ],
  templateUrl: './history.component.html'
})
export class HistoryComponent {
  @Input() onBack?: () => void;
  @Output() back = new EventEmitter<void>();

  private iconService = inject(IconService);
  private simulatedTradeService = inject(SimulatedTradeService);
  private signalrService = inject(TradingSignalrService);
  // Datos del gráfico de performance
  chartData: ChartData[] = [];
  private subs = new Subscription();

  // Datos Reales
  performanceStats?: SimulationPerformanceDto;
  realTrades: SimulatedTradeDto[] = [];

  // Filtros
  tradeType: string = 'all';
  dateRange: string = 'last30';

  tradeOptions: FilterOption[] = [
    { value: 'all', label: 'Todos los trades' },
    { value: 'win', label: 'Trades Ganadores' },
    { value: 'loss', label: 'Trades Perdedores' },
    { value: 'breakeven', label: 'Break Even' },
    { value: 'open', label: 'Trades Abiertos' }
  ];

  dateOptions: FilterOption[] = [
    { value: 'last7', label: 'Últimos 7 días' },
    { value: 'last30', label: 'Últimos 30 días' },
    { value: 'last90', label: 'Últimos 90 días' },
    { value: 'all', label: 'Todo el tiempo' },
    { value: 'custom', label: 'Personalizado' }
  ];

// Duplicate removed

  // Historial filtrado
  get filteredTrades(): SimulatedTradeDto[] {
    return this.realTrades.filter(item => {
      if (this.tradeType === 'win' && item.status !== 1) return false; // Win = 1
      if (this.tradeType === 'loss' && item.status !== 2) return false; // Loss = 2
      if (this.tradeType === 'open' && item.status !== 0) return false; // Open = 0
      return true;
    });
  }

  // Estadísticas basadas en backend si están disponibles, sino calculadas
  get totalProfit(): number {
    return Number(this.performanceStats?.totalGain || 0);
  }

  get winRate(): number {
    return Math.round(Number(this.performanceStats?.winRate || 0));
  }

  get totalTrades(): number {
    return this.performanceStats?.totalTrades || 0;
  }

  get averageProfit(): number {
    return Number(this.performanceStats?.avgPerTrade || 0);
  }

  constructor(private router: Router) {}

  ngOnInit() {
    this.loadData();
    
    // Refresh on any trade activity
    this.subs.add(this.signalrService.tradeOpened$.subscribe(() => this.loadData()));
    this.subs.add(this.signalrService.tradeClosed$.subscribe(() => this.loadData()));

    // Keep PnL/Status updated in real-time
    this.subs.add(this.signalrService.tradeUpdate$.subscribe(update => {
      const index = this.realTrades.findIndex(t => t.id === update.id);
      if (index !== -1) {
        this.realTrades[index] = { ...this.realTrades[index], ...update };
      }
    }));
  }

  ngOnDestroy() {
    this.subs.unsubscribe();
  }

  loadData() {
    this.simulatedTradeService.getPerformanceStats().subscribe(stats => {
      this.performanceStats = stats;
      this.chartData = stats.equityCurve.map(p => ({
        month: this.formatDateLabel(p.timestamp),
        amount: Math.round(Number(p.balance))
      }));
    });

    this.simulatedTradeService.getRecentTrades(50).subscribe(trades => {
      this.realTrades = trades;
    });
  }

  private formatDateLabel(date: string): string {
    const d = new Date(date);
    return d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
  }

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  handleBack(): void {
    if (this.onBack) {
      this.onBack();
    } else {
      this.router.navigate(['/']);
    }
    this.back.emit();
  }

  formatCurrency(amount: number): string {
    return `$${Math.abs(amount).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  getTradeStatusClass(status: number) {
    switch (status) {
      case 1: // Win (TradeStatus.Win = 1)
        return {
          circleClass: 'payment-circle-success',
          textClass: 'text-success small fw-medium',
          icon: 'trending-up-outline'
        };
      case 2: // Loss (TradeStatus.Loss = 2)
      case 6: // Liquidated (TradeStatus.Liquidated = 6)
        return {
          circleClass: 'payment-circle-danger',
          textClass: 'text-danger small fw-medium',
          icon: 'trending-down-outline'
        };
      case 0: // Open (TradeStatus.Open = 0)
        return {
          circleClass: 'payment-circle-primary',
          textClass: 'text-primary small fw-medium',
          icon: 'time-outline'
        };
      default: // Canceled, Expired, BreakEven
        return {
          circleClass: 'payment-circle-warning',
          textClass: 'text-warning small fw-medium',
          icon: 'remove-outline'
        };
    }
  }

  getTradeStatusLabel(status: number): string {
    switch (status) {
      case 1: return 'Trade Ganador';
      case 2: return 'Trade Perdedor';
      case 6: return 'Liquidado';
      case 0: return 'Trade Abierto';
      default: return 'Cerrado';
    }
  }

  getDirectionColor(side: number): string {
    return side === 0 ? 'text-success' : 'text-danger';
  }

  getDirectionLabel(side: number): string {
    return side === 0 ? 'LONG' : 'SHORT';
  }

  getProfitColor(profitLoss: number): string {
    return profitLoss > 0 ? 'text-success' : profitLoss < 0 ? 'text-danger' : 'text-white-50';
  }

  getProfitValue(trade: SimulatedTradeDto): number {
    return Number(trade.realizedPnl ?? trade.unrealizedPnl ?? 0);
  }

  formatDate(dateStr?: string): string {
    if (!dateStr) return '--:--';
    const date = new Date(dateStr);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();
    
    if (isToday) {
      return `Hoy ${date.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })}`;
    }
    return date.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  }
}


// 🎯 Cambios Realizados:
// 1. Transformación Completa:
// "Historial de pagos" → "Historial de Trades"

// "Pagos realizados" → "Trades Ganadores"

// 2. Estadísticas de Trading:
// Ganancia Total: Suma de todos los P&L

// Win Rate: % de trades ganadores

// Total Trades: Cantidad total de operaciones

// Average por Trade: Ganancia promedio por operación

// 3. Tipos de Trades:
// Win: Trade ganador (verde)

// Loss: Trade perdedor (rojo)

// Breakeven: Sin ganancia/pérdida (amarillo)

// Open: Trade aún abierto (azul)

// 4. Información por Trade:
// Par de trading (BTC/USDT)

// Dirección (LONG/SHORT) con color

// Apalancamiento (2x, 3x, etc.)

// Ganancia/Pérdida con color

// Fecha y capital invertido

// 5. Mantengo:
// ✅ Misma estructura HTML

// ✅ Mismo sistema de filtros

// ✅ Mismo gráfico de performance

// ✅ Mismo diseño de lista

// ✅ Mismo header con botón back