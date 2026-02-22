import { Component, inject, OnInit, LOCALE_ID, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
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
import { DialogComponent } from 'src/shared/components/dialog/dialog.component';
import { TradingSignalrService } from '../services/trading-signalr.service';
import { Subject, takeUntil } from 'rxjs';

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
    IonIcon,
    DialogComponent
  ],
  templateUrl: './execute-trade.component.html'
})
export class ExecuteTradeComponent implements OnInit {
  constructor(@Inject(LOCALE_ID) public locale: string) { }

  private iconService = inject(IconService);
  private router = inject(Router);
  private marketDataService = inject(MarketDataService);
  private tradingService = inject(TradingService);
  private route = inject(ActivatedRoute);
  private signalrService = inject(TradingSignalrService);
  private destroy$ = new Subject<void>();

  symbols: { label: string, value: string }[] = [];
  isAutoSelected = false;
  hasActiveHunt = false;
  showBlockingDialog = false;
  isExecuting = false;

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
    this.route.queryParams.subscribe(params => {
      if (params['symbol']) {
        this.request.symbol = params['symbol'];
      }
      if (params['direction']) {
        this.request.direction = params['direction'] === 'SHORT' ? 'sell' : 'buy';
      }
    });
    this.checkActiveHunt();
  }


  checkActiveHunt() {
    this.tradingService.getCurrentSession().subscribe({
      next: (session) => {
        this.hasActiveHunt = !!session;
        if (this.hasActiveHunt) {
          this.showBlockingDialog = true;
        }
      }
    });
  }

  closeBlockingDialog() {
    this.showBlockingDialog = false;
    this.router.navigate(['/dashboard']);
  }

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  loadSymbols() {
    // Sincronizado con DashboardComponent
    this.symbols = [
      { label: '🤖 Automático (Todas)', value: 'AUTO' },
      { label: 'BTC/USDT', value: 'BTCUSDT' },
      { label: 'ETH/USDT', value: 'ETHUSDT' },
      { label: 'SOLUSDT', value: 'SOLUSDT' },
      { label: 'BNBUSDT', value: 'BNBUSDT' },
      { label: 'XRPUSDT', value: 'XRPUSDT' },
    ];
  }

  onSymbolChange() {
    this.isAutoSelected = this.request.symbol === 'AUTO';
  }

  handleBack() {
    this.router.navigate(['/signals']);
  }

  executeTrade() {
    if (this.isExecuting) return;

    this.isExecuting = true;
    console.log('🚀 Iniciando Cacería (Navegación Inmediata):', this.request);

    // 1. Crear Estrategia Real
    this.tradingService.createStrategy({
      name: `Cacería ${this.request.symbol} - ${new Date().toLocaleString()}`,
      directionPreference: this.isAutoSelected ? SignalDirection.Auto : (this.request.direction === 'buy' ? SignalDirection.Long : SignalDirection.Short),
      selectedCryptos: this.isAutoSelected ? [] : [this.request.symbol],
      customSymbols: this.isAutoSelected ? [] : [],
      leverage: this.request.leverage,
      capital: this.request.amount,
      riskLevel: RiskTolerance.Medium,
      autoStopLoss: true,
      takeProfitPercentage: this.request.takeProfit,
      stopLossPercentage: this.request.stopLoss,
      notificationsEnabled: true,
      isAutoMode: this.isAutoSelected
    }).subscribe({
      next: (strategy) => {
        console.log('✅ Estrategia creada:', strategy);

        // 2. Iniciar Sesión (siempre, auto o no)
        const sessionSymbol = this.isAutoSelected ? 'AUTO' : this.request.symbol;
        this.tradingService.startSession({
          symbol: sessionSymbol,
          timeframe: '1m'
        }).subscribe({
          next: () => {
            console.log('✅ Sesión iniciada. Navegando al dashboard...');
            this.router.navigate(['/dashboard']);
          },
          error: (err) => {
            console.error('❌ Error al iniciar sesión', err);
            this.isExecuting = false;
          }
        });
      },
      error: (err) => {
        console.error('❌ Error al crear estrategia', err);
        this.isExecuting = false;
      }
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
