import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { LabelComponent } from 'src/shared/components/label/label.component';
import { IconService } from 'src/shared/services/icon.service';
import { IonIcon } from '@ionic/angular/standalone';
import { MarketDataService } from '../proxy/trading/market-data.service';
import { TradingService } from '../proxy/trading/trading.service';
import { SignalDirection } from '../proxy/trading/signal-direction.enum';
import { RiskTolerance } from '../proxy/trading/risk-tolerance.enum';

interface TradeDetails {
  symbol: string;
  direction: 'LONG' | 'SHORT';
  entryPrice: number;
  currentPrice: number;
  leverage: number;
  suggestedAmount: number;
  takeProfit?: number;
  stopLoss?: number;
  confidence: number;
}

interface ExecuteTradeRequest {
  symbol: string;
  direction: 'buy' | 'sell';
  amount: number;
  leverage: number;
  takeProfit: number;
  stopLoss: number;
  orderType: 'market' | 'limit';
}

@Component({
  selector: 'app-execute-trade',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    CardContentComponent,
    CardIconComponent,
    GlassButtonComponent,
    LabelComponent,
    IonIcon
  ],
  templateUrl: './execute-trade.component.html'
})
export class ExecuteTradeComponent implements OnInit {
  private iconService = inject(IconService);
  private router = inject(Router);
  private marketDataService = inject(MarketDataService);
  private tradingService = inject(TradingService);

  symbols: { label: string, value: string }[] = [];

  // Mock de detalles de la señal
  tradeDetails: TradeDetails = {
    symbol: 'BTC/USDT',
    direction: 'LONG',
    entryPrice: 68500,
    currentPrice: 68550,
    leverage: 5,
    suggestedAmount: 500,
    takeProfit: 5,
    stopLoss: 2,
    confidence: 85
  };

  // Datos del formulario
  request: ExecuteTradeRequest = {
    symbol: 'BTC/USDT',
    direction: 'buy',
    amount: 500,
    leverage: 5,
    takeProfit: 5,
    stopLoss: 2,
    orderType: 'market'
  };

  ngOnInit() {
    this.loadSymbols();
  }

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  loadSymbols() {
    // Sincronizado con DashboardComponent
    this.symbols = [
      { label: 'BTC/USDT', value: 'BTCUSDT' },
      { label: 'ETH/USDT', value: 'ETHUSDT' },
      { label: 'SOL/USDT', value: 'SOLUSDT' },
      { label: 'BNB/USDT', value: 'BNBUSDT' },
      { label: 'XRP/USDT', value: 'XRPUSDT' },
    ];
  }

  handleBack() {
    this.router.navigate(['/signals']);
  }

  executeTrade() {
    console.log('🚀 Iniciando Cacería:', this.request);

    // 1. Crear Estrategia Real
    this.tradingService.createStrategy({
      name: `Cacería ${this.request.symbol} - ${new Date().toLocaleString()}`,
      directionPreference: this.request.direction === 'buy' ? SignalDirection.Long : SignalDirection.Short,
      selectedCryptos: [this.request.symbol],
      leverage: this.request.leverage,
      capital: this.request.amount,
      riskLevel: RiskTolerance.Medium,
      autoStopLoss: true,
      takeProfitPercentage: this.request.takeProfit,
      stopLossPercentage: this.request.stopLoss,
      notificationsEnabled: true
    }).subscribe({
      next: (strategy) => {
        console.log('Estrategia creada:', strategy);
        // 2. Iniciar Sesión Automatically
        this.tradingService.startSession({
          symbol: this.request.symbol,
          timeframe: '1m' // Por defecto
        }).subscribe({
          next: () => {
            console.log('Cacería iniciada con éxito');
            this.router.navigate(['/dashboard']);
          },
          error: (err) => console.error('Error al iniciar sesión', err)
        });
      },
      error: (err) => console.error('Error al crear estrategia', err)
    });
  }

  cancelTrade() {
    this.router.navigate(['/signals']);
  }

  getStatusColor(): 'success' | 'warning' | 'danger' {
    if (this.tradeDetails.confidence >= 80) return 'success';
    if (this.tradeDetails.confidence >= 50) return 'warning';
    return 'danger';
  }

  getRiskSummary() {
    const margin = this.request.amount / this.request.leverage;
    const potentialProfit = this.request.amount * (this.request.takeProfit / 100);
    const potentialLoss = this.request.amount * (this.request.stopLoss / 100);

    return {
      margin,
      potentialProfit,
      potentialLoss
    };
  }
}
