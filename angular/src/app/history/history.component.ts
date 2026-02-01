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

interface FilterOption {
  value: string;
  label: string;
}

interface ChartData {
  month: string;
  amount: number;
}

interface TradeHistoryItem {
  id: number;
  cryptoPair: string;
  action: 'win' | 'loss' | 'breakeven' | 'open';
  amount: number;
  profitLoss: number;
  date: string;
  direction: 'LONG' | 'SHORT';
  leverage: number;
}

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

  // Datos del gráfico de performance
  chartData: ChartData[] = [
    { month: 'Sep', amount: 850 },
    { month: 'Oct', amount: 1250 },
    { month: 'Nov', amount: 1800 },
    { month: 'Dic', amount: 2450 },
    { month: 'Ene', amount: 3250 }
  ];

  // Datos del historial de trades
  tradeHistory: TradeHistoryItem[] = [
    { id: 1, cryptoPair: 'BTC/USDT', action: 'win', amount: 1000, profitLoss: +245, date: 'Hoy 15:30', direction: 'LONG', leverage: 3 },
    { id: 2, cryptoPair: 'ETH/USDT', action: 'loss', amount: 500, profitLoss: -85, date: 'Hoy 14:15', direction: 'SHORT', leverage: 2 },
    { id: 3, cryptoPair: 'SOL/USDT', action: 'win', amount: 750, profitLoss: +180, date: 'Ayer 22:45', direction: 'LONG', leverage: 5 },
    { id: 4, cryptoPair: 'BNB/USDT', action: 'breakeven', amount: 300, profitLoss: 0, date: '15/01 18:20', direction: 'SHORT', leverage: 2 },
    { id: 5, cryptoPair: 'XRP/USDT', action: 'win', amount: 420, profitLoss: +95, date: '15/01 10:30', direction: 'LONG', leverage: 3 },
    { id: 6, cryptoPair: 'ADA/USDT', action: 'open', amount: 600, profitLoss: +42, date: '14/01 16:45', direction: 'LONG', leverage: 2 },
    { id: 7, cryptoPair: 'DOT/USDT', action: 'win', amount: 350, profitLoss: +78, date: '13/01 09:15', direction: 'SHORT', leverage: 3 },
    { id: 8, cryptoPair: 'AVAX/USDT', action: 'loss', amount: 450, profitLoss: -62, date: '12/01 21:30', direction: 'LONG', leverage: 4 },
  ];

  // Historial filtrado
  get filteredTrades(): TradeHistoryItem[] {
    return this.tradeHistory.filter(item => {
      if (this.tradeType !== 'all' && item.action !== this.tradeType) {
        return false;
      }
      // Aquí iría la lógica de filtrado por fecha en una app real
      return true;
    });
  }

  // Estadísticas
  get totalProfit(): number {
    return this.tradeHistory
      .filter(item => item.action !== 'open')
      .reduce((sum, item) => sum + item.profitLoss, 0);
  }

  get winRate(): number {
    const closedTrades = this.tradeHistory.filter(item => item.action !== 'open');
    const winningTrades = closedTrades.filter(item => item.action === 'win');
    return closedTrades.length > 0 ? Math.round((winningTrades.length / closedTrades.length) * 100) : 0;
  }

  get totalTrades(): number {
    return this.tradeHistory.length;
  }

  get averageProfit(): number {
    const closedTrades = this.tradeHistory.filter(item => item.action !== 'open');
    return closedTrades.length > 0 ? this.totalProfit / closedTrades.length : 0;
  }

  constructor(private router: Router) {}

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

  getTradeStatusClass(action: 'win' | 'loss' | 'breakeven' | 'open') {
    switch (action) {
      case 'win':
        return {
          circleClass: 'payment-circle-success',
          textClass: 'text-success small fw-medium',
          icon: 'trending-up-outline'
        };
      case 'loss':
        return {
          circleClass: 'payment-circle-danger',
          textClass: 'text-danger small fw-medium',
          icon: 'trending-down-outline'
        };
      case 'breakeven':
        return {
          circleClass: 'payment-circle-warning',
          textClass: 'text-warning small fw-medium',
          icon: 'remove-outline'
        };
      case 'open':
        return {
          circleClass: 'payment-circle-primary',
          textClass: 'text-primary small fw-medium',
          icon: 'time-outline'
        };
      default:
        return {
          circleClass: 'payment-circle-success',
          textClass: 'text-success small fw-medium',
          icon: 'trending-up-outline'
        };
    }
  }

  getTradeStatusLabel(action: 'win' | 'loss' | 'breakeven' | 'open'): string {
    switch (action) {
      case 'win':
        return 'Trade Ganador';
      case 'loss':
        return 'Trade Perdedor';
      case 'breakeven':
        return 'Break Even';
      case 'open':
        return 'Trade Abierto';
      default:
        return action;
    }
  }

  getDirectionColor(direction: 'LONG' | 'SHORT'): string {
    return direction === 'LONG' ? 'text-success' : 'text-danger';
  }

  getProfitColor(profitLoss: number): string {
    return profitLoss > 0 ? 'text-success' : profitLoss < 0 ? 'text-danger' : 'text-white-50';
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