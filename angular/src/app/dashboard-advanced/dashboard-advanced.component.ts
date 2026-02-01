import { Component, inject, AfterViewInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { InputComponent } from 'src/shared/components/input/input.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { LabelComponent } from 'src/shared/components/label/label.component';
import { ToggleComponent } from 'src/shared/components/toggle/toggle.component';
import { IonIcon } from '@ionic/angular/standalone';
import { IconService } from 'src/shared/services/icon.service';

interface MarketMetric {
  name: string;
  value: number;
  change: number;
  icon: string;
}

interface ActiveAlert {
  id: number;
  type: 'preparation' | 'buy' | 'warning' | 'sell';
  message: string;
  crypto: string;
  price: number;
  timestamp: string;
  active: boolean;
}

@Component({
  selector: 'app-dashboard-advanced',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    CardContentComponent,
    GlassButtonComponent,
    LabelComponent,
    ToggleComponent,
    IonIcon
  ],
  templateUrl: './dashboard-advanced.component.html'
})
export class DashboardAdvancedComponent implements AfterViewInit, OnDestroy {
  private iconService = inject(IconService);
  private router = inject(Router);

  // Datos de trading activo
  activeTrade = {
    crypto: 'BTC/USDT',
    direction: 'LONG' as 'LONG' | 'SHORT',
    entryPrice: 68500,
    currentPrice: 69250,
    profitLoss: +750,
    profitPercentage: +1.1,
    takeProfit: 71000,
    stopLoss: 67000,
    leverage: 3,
    invested: 1000
  };

  // Métricas del mercado en tiempo real
  marketMetrics: MarketMetric[] = [
    { name: 'RSI', value: 58.3, change: +2.1, icon: 'pulse-outline' },
    { name: 'MACD', value: 125.4, change: -0.8, icon: 'trending-up-outline' },
    { name: 'Volumen 24h', value: 42.5, change: +15.2, icon: 'bar-chart-outline' },
    { name: 'Miedo y Codicia', value: 68, change: +5, icon: 'flash-outline' },
  ];

  // Alertas activas
  activeAlerts: ActiveAlert[] = [
    { id: 1, type: 'preparation', message: 'BTC entrando en zona de compra', crypto: 'BTC/USDT', price: 68500, timestamp: '15:28', active: true },
    { id: 2, type: 'buy', message: '¡COMPRA CONFIRMADA! ETH', crypto: 'ETH/USDT', price: 3850, timestamp: '14:15', active: false },
    { id: 3, type: 'warning', message: 'Prepárate para vender SOL', crypto: 'SOL/USDT', price: 195, timestamp: '13:45', active: true },
  ];

  // Configuración avanzada
  advancedConfig = {
    autoTrading: false,
    trailingStop: true,
    trailingStopPercent: 1.5,
    multipleEntries: false,
    riskRewardRatio: 2.5,
    maxDailyLoss: 5,
    notificationsSound: true,
    emailReports: false
  };

  // Gráficos disponibles
  availableCharts = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT'];
  selectedChart = 'BTC/USDT';
  
  // Timeframes
  timeframes = ['1m', '5m', '15m', '1h', '4h', '1d'];
  selectedTimeframe = '15m';

  // Para mostrar la hora actual
  currentTime = '';

  // Intervalo para simular updates
  private updateInterval: any;

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
    
    // Actualizar hora actual
    this.updateCurrentTime();
    
    // Simular updates en tiempo real
    this.updateInterval = setInterval(() => {
      this.simulateMarketUpdate();
      this.updateCurrentTime();
    }, 5000);
  }

  ngOnDestroy() {
    if (this.updateInterval) {
      clearInterval(this.updateInterval);
    }
  }

  updateCurrentTime() {
    this.currentTime = new Date().toLocaleTimeString('es-AR', { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit'
    });
  }

  simulateMarketUpdate() {
    // Simular cambios de precio
    const change = (Math.random() - 0.5) * 100;
    this.activeTrade.currentPrice += change;
    this.activeTrade.profitLoss = this.activeTrade.currentPrice - this.activeTrade.entryPrice;
    this.activeTrade.profitPercentage = (this.activeTrade.profitLoss / this.activeTrade.entryPrice) * 100;
    
    // Actualizar métricas
    this.marketMetrics.forEach(metric => {
      metric.value += (Math.random() - 0.5) * 2;
      metric.change = (Math.random() - 0.5) * 1;
    });
  }

  onBack() {
    this.router.navigate(['/']);
  }

  onExecuteTrade() {
    console.log('Ejecutar trade avanzado:', this.activeTrade);
    // Lógica para ejecutar trade
  }

  onCloseTrade() {
    console.log('Cerrar trade manualmente');
    // Lógica para cerrar trade
  }

  onAddAlert() {
    const newAlert: ActiveAlert = {
      id: Date.now(),
      type: 'warning',
      message: 'Alerta personalizada',
      crypto: this.selectedChart,
      price: this.activeTrade.currentPrice,
      timestamp: new Date().toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' }),
      active: true
    };
    this.activeAlerts.unshift(newAlert);
  }

  onToggleAlert(alert: ActiveAlert) {
    alert.active = !alert.active;
  }

  onSaveConfig() {
    console.log('Guardando configuración avanzada:', this.advancedConfig);
    // Guardar configuración
  }

  onOpenChart(chart: string) {
    this.selectedChart = chart;
    console.log('Abriendo gráfico:', chart);
  }

  setTimeframe(tf: string) {
    this.selectedTimeframe = tf;
  }

  // Métodos auxiliares
  getAlertColor(type: 'preparation' | 'buy' | 'warning' | 'sell'): string {
    switch(type) {
      case 'preparation': return 'warning';
      case 'buy': return 'success';
      case 'warning': return 'warning';
      case 'sell': return 'danger';
      default: return 'primary';
    }
  }

  getAlertIcon(type: 'preparation' | 'buy' | 'warning' | 'sell'): string {
    switch(type) {
      case 'preparation': return 'warning-outline';
      case 'buy': return 'trending-up-outline';
      case 'warning': return 'notifications-outline';
      case 'sell': return 'trending-down-outline';
      default: return 'alert-circle-outline';
    }
  }

  formatCurrency(value: number): string {
    return `$${Math.abs(value).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  getProfitColor(): string {
    return this.activeTrade.profitLoss >= 0 ? 'text-success' : 'text-danger';
  }
}