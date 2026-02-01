import { Component, AfterViewInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { IconService } from 'src/shared/services/icon.service';
import { RouterLink } from '@angular/router';

// Mantengo la misma interfaz pero para trading
interface TradingSignal {
  name: string;          // Par de trading (ej: BTC/USDT)
  amount: number;        // Ganancia potencial en USDT
  icon: string;          // Icono de la cripto
  status: 'alta' | 'media' | 'baja';  // Confianza de la señal
}

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [
    CommonModule,
    CardContentComponent,
    CardIconComponent,
    GlassButtonComponent,
    RouterLink
  ],
  templateUrl: './home.component.html'
})
export class HomeComponent implements AfterViewInit {
  private iconService = inject(IconService);

  // Estado del usuario
  hasActiveStrategies = false;            // false = usuario nuevo
  totalPotentialProfit = 0;               // Ganancia potencial total

  // Mock de señales de trading
  recentSignals: TradingSignal[] = [
    { name: 'BTC/USDT - LONG', amount: 2450, icon: 'trending-up-outline', status: 'alta' },
    { name: 'ETH/USDT - SHORT', amount: 1250, icon: 'trending-down-outline', status: 'media' },
    { name: 'SOL/USDT - LONG', amount: 850, icon: 'trending-up-outline', status: 'alta' },
    { name: 'BNB/USDT - SHORT', amount: 620, icon: 'trending-down-outline', status: 'baja' },
  ];

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
    this.updateDashboard();
  }

  private updateDashboard() {
    if (this.recentSignals.length > 0) {
      this.hasActiveStrategies = true;
      this.totalPotentialProfit = this.recentSignals.reduce((sum, a) => sum + a.amount, 0);
    }
  }

  getStatusLabel(status: 'alta' | 'media' | 'baja'): string {
    switch (status) {
      case 'alta': return 'Alta Confianza';
      case 'media': return 'Confianza Media';
      case 'baja': return 'Baja Confianza';
      default: return '';
    }
  }

  getStatusColor(status: 'alta' | 'media' | 'baja'): 'danger' | 'warning' | 'success' {
    switch (status) {
      case 'alta': return 'success';    // Verde para alta confianza
      case 'media': return 'warning';   // Amarillo para media
      case 'baja': return 'danger';     // Rojo para baja
      default: return 'success';
    }
  }
}


// 📋 Mapeo de Rutas y Componentes (Solo nombres)
// Mantengo exactamente la misma estructura de archivos, solo renombro las rutas:

// Archivo Original	Nueva Ruta	Nuevo Propósito
// home.component	/home	✅ YA LISTO - Home de trading
// profile.component	/profile	Perfil de trader (conectar APIs, etc.)
// debts.component	/signals	Lista de señales detectadas
// add-debt.component	/configure	Configurar estrategia de trading
// debt-detail.component	/signal-detail	Detalle de una señal específica
// generate-letter.component	/execute-trade	Ejecutar trade manual
// negotiate-debt.component	❌ ELIMINAR	No aplica para trading
// NUEVO	/dashboard	Dashboard con super gráfico
// NUEVO	/alerts	Sistema de alertas 1-2-3-4
// NUEVO	/backtesting	Probar estrategias históricas
// 🔧 Cambios Mínimos Necesarios
// En app-routing.module.ts:

 