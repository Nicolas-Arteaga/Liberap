import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { ButtonComponent } from 'src/shared/components/button/button.component';

type SignalConfidence = 'alta' | 'media' | 'baja';
type TradeDirection = 'long' | 'short';

interface TradingSignal {
  id: number;
  name: string;          // Par de trading (ej: BTC/USDT)
  profitPotential: number; // Ganancia potencial en USDT
  confidence: SignalConfidence;
  direction: TradeDirection;
  entryPrice: number;
  analyzedDate: string;
  status: 'active' | 'completed' | 'expired';
}

@Component({
  selector: 'app-signals',
  standalone: true,
  imports: [CommonModule, CardIconComponent, ButtonComponent],
  templateUrl: './signals.component.html'
})
export class SignalsComponent {
  activeFilter: 'todos' | SignalConfidence = 'todos';
  
  allSignals: TradingSignal[] = [
    { 
      id: 1, 
      name: 'BTC/USDT - LONG', 
      profitPotential: 2450, 
      confidence: 'alta', 
      direction: 'long',
      entryPrice: 68500,
      analyzedDate: 'Hoy 15:30',
      status: 'active'
    },
    { 
      id: 2, 
      name: 'ETH/USDT - SHORT', 
      profitPotential: 1250, 
      confidence: 'media', 
      direction: 'short',
      entryPrice: 3850,
      analyzedDate: 'Hoy 14:15',
      status: 'active'
    },
    { 
      id: 3, 
      name: 'SOL/USDT - LONG', 
      profitPotential: 850, 
      confidence: 'alta', 
      direction: 'long',
      entryPrice: 185,
      analyzedDate: 'Ayer 22:45',
      status: 'completed'
    },
    { 
      id: 4, 
      name: 'BNB/USDT - SHORT', 
      profitPotential: 620, 
      confidence: 'baja', 
      direction: 'short',
      entryPrice: 320,
      analyzedDate: 'Ayer 18:20',
      status: 'expired'
    },
    { 
      id: 5, 
      name: 'XRP/USDT - LONG', 
      profitPotential: 420, 
      confidence: 'media', 
      direction: 'long',
      entryPrice: 0.58,
      analyzedDate: '15/01 10:30',
      status: 'completed'
    },
  ];

  // Propiedades computadas para las estadísticas
  get altaCount(): number {
    return this.allSignals.filter(s => s.confidence === 'alta').length;
  }

  get mediaCount(): number {
    return this.allSignals.filter(s => s.confidence === 'media').length;
  }

  get bajaCount(): number {
    return this.allSignals.filter(s => s.confidence === 'baja').length;
  }

  get completedCount(): number {
    return this.allSignals.filter(s => s.status === 'completed').length;
  }

  get totalProfit(): number {
    return this.allSignals.reduce((sum, s) => sum + s.profitPotential, 0);
  }

  get filteredSignals(): TradingSignal[] {
    if (this.activeFilter === 'todos') {
      return this.allSignals;
    }
    return this.allSignals.filter(s => s.confidence === this.activeFilter);
  }

  getConfidenceLabel(confidence: SignalConfidence): string {
    switch(confidence) {
      case 'alta': return 'Alta Confianza';
      case 'media': return 'Confianza Media';
      case 'baja': return 'Baja Confianza';
      default: return '';
    }
  }

  getConfidenceColor(confidence: SignalConfidence): 'danger' | 'warning' | 'success' {
    switch(confidence) {
      case 'alta': return 'success';
      case 'media': return 'warning';
      case 'baja': return 'danger';
      default: return 'success';
    }
  }

  getDirectionIcon(direction: TradeDirection): string {
    return direction === 'long' ? 'trending-up-outline' : 'trending-down-outline';
  }

  getDirectionColor(direction: TradeDirection): string {
    return direction === 'long' ? 'text-success' : 'text-danger';
  }

  getDirectionText(direction: TradeDirection): string {
    return direction === 'long' ? 'LONG' : 'SHORT';
  }

  getStatusColor(status: 'active' | 'completed' | 'expired'): string {
    switch(status) {
      case 'active': return 'text-success';
      case 'completed': return 'text-primary';
      case 'expired': return 'text-white-50';
      default: return 'text-white-50';
    }
  }

  getStatusText(status: 'active' | 'completed' | 'expired'): string {
    switch(status) {
      case 'active': return 'Activa';
      case 'completed': return 'Completada';
      case 'expired': return 'Expirada';
      default: return '';
    }
  }

  formatCurrency(value: number): string {
    return `$${value.toLocaleString('es-AR')}`;
  }

  formatPrice(value: number): string {
    return value >= 100 ? `$${value.toLocaleString('es-AR')}` : `$${value.toFixed(2)}`;
  }
}


// Cambios Realizados:
// 1. Interfaz transformada:
// InterestAnalysis → TradingSignal

// interestRate → profitPotential (ganancia en USDT)

// status: 'abusiva' | 'elevada' | 'legal' → confidence: 'alta' | 'media' | 'baja'

// type: BankProduct → direction: 'long' | 'short'

// Agregué entryPrice y status (active/completed/expired)

// 2. Lógica adaptada:
// Filtros: "Abusivas/Elevadas/Legal" → "Alta/Media/Baja Confianza"

// Colores: Peligro/Advertencia/Éxito → Éxito/Advertencia/Peligro (invertidos para trading)

// Iconos: tarjetas/cash → trending-up/down

// 3. Visual mejorado:
// Cada señal muestra:

// Par + dirección (LONG/SHORT)
// Precio de entrada
// Ganancia potencial grande
// Estado + fecha
// Stats finales: Total, Completadas, Ganancia Total

// 4. Mantengo:
// ✅ Misma estructura HTML

// ✅ Mismo sistema de filtros

// ✅ Mismo diseño de cards

// ✅ Mismo espaciado y clases