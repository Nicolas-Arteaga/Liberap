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
import { TradingStyle } from '../proxy/trading/trading-style.enum';
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
  style: TradingStyle;
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

  TradingStyle = TradingStyle; // For template
  tradingStyles = [
    { label: 'Scalping', icon: 'flash-outline', value: TradingStyle.Scalping, desc: '1m | 5-10x | TP 1-2%' },
    { label: 'Day Trading', icon: 'sunny-outline', value: TradingStyle.DayTrading, desc: '15m | 3-5x | TP 3-5%' },
    { label: 'Swing', icon: 'calendar-outline', value: TradingStyle.SwingTrading, desc: '4h | 2-3x | TP 8-15%' },
    { label: 'Position', icon: 'trending-up-outline', value: TradingStyle.PositionTrading, desc: '1d | 1-2x | TP 20-30%' },
    { label: 'HODL', icon: 'diamond-outline', value: TradingStyle.HODL, desc: '1w | 1x | Spot' },
    { label: 'Grid Trading', icon: 'grid-outline', value: TradingStyle.GridTrading, desc: 'Rango | Múltiples órdenes' },
    { label: 'Arbitraje', icon: 'swap-horizontal-outline', value: TradingStyle.Arbitrage, desc: 'Entre exchanges' },
    { label: 'Algorítmico', icon: 'code-outline', value: TradingStyle.Algorithmic, desc: 'Bots automáticos' }
  ];

  isAutoSelected = false;
  isRecommending = false;
  recommendationReason = '';

  hasActiveHunt = false;
  showBlockingDialog = false;
  isExecuting = false;

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

  request: ExecuteTradeRequest = {
    symbol: 'BTCUSDT',
    direction: 'buy',
    amount: 500,
    leverage: 5,
    takeProfit: 5,
    stopLoss: 2,
    orderType: 'market',
    style: TradingStyle.DayTrading
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

  onStyleSelect(style: TradingStyle) {
    if (this.isAutoSelected && this.isRecommending) return;
    this.request.style = style;
    this.isAutoSelected = false; // Turn off auto if manual selection is made
    this.applyStyleDefaults(style);
  }

  applyStyleDefaults(style: TradingStyle) {
    switch (style) {
      case TradingStyle.Scalping:
        this.request.leverage = 10;
        this.request.takeProfit = 2;
        this.request.stopLoss = 1;
        break;
      case TradingStyle.DayTrading:
        this.request.leverage = 5;
        this.request.takeProfit = 5;
        this.request.stopLoss = 2;
        break;
      case TradingStyle.SwingTrading:
        this.request.leverage = 3;
        this.request.takeProfit = 15;
        this.request.stopLoss = 5;
        break;
      case TradingStyle.PositionTrading:
        this.request.leverage = 2;
        this.request.takeProfit = 30;
        this.request.stopLoss = 10;
        break;
      case TradingStyle.HODL:
        this.request.leverage = 1;
        this.request.takeProfit = 0;
        this.request.stopLoss = 0;
        break;
      case TradingStyle.GridTrading:
        this.request.leverage = 3;
        this.request.takeProfit = 1;
        this.request.stopLoss = 1;
        break;
      case TradingStyle.Arbitrage:
        this.request.leverage = 1;
        this.request.takeProfit = 0.5;
        this.request.stopLoss = 0.3;
        break;
      case TradingStyle.Algorithmic:
        this.request.leverage = 5;
        this.request.takeProfit = 5;
        this.request.stopLoss = 2;
        break;
    }
  }

  recommendStyle() {
    let targetSymbol = this.request.symbol;
    if (targetSymbol === 'AUTO') {
      targetSymbol = 'BTCUSDT'; // Default to BTCUSDT for analysis if symbol is AUTO
    }

    this.isRecommending = true;
    this.recommendationReason = 'Analizando mercado en tiempo real...';

    this.tradingService.recommendTradingStyle(targetSymbol).subscribe({
      next: (res) => {
        this.request.style = res.style;
        this.recommendationReason = res.reason;
        this.applyStyleDefaults(res.style);
        this.isRecommending = false;
        this.isAutoSelected = true;
      },
      error: (err) => {
        console.error('Error recommending style', err);
        this.recommendationReason = 'Error al analizar el mercado. Intente de nuevo.';
        this.isRecommending = false;
      }
    });
  }

  handleBack() {
    this.router.navigate(['/signals']);
  }

  getTimeframeForStyle(style: TradingStyle): string {
    switch (style) {
      case TradingStyle.Scalping: return '1m';
      case TradingStyle.DayTrading: return '15m';
      case TradingStyle.SwingTrading: return '4h';
      case TradingStyle.PositionTrading: return '1d';
      case TradingStyle.HODL: return '1w';
      case TradingStyle.GridTrading: return '15m';
      case TradingStyle.Arbitrage: return '1m';
      case TradingStyle.Algorithmic: return '15m'; // Por defecto
      default: return '15m'; // Default safer timeframe
    }
  }

  executeTrade() {
    if (this.isExecuting) return;

    this.isExecuting = true;
    console.log('🚀 Iniciando Cacería (Navegación Inmediata):', this.request);

    // 1. Crear Estrategia Real
    // Portfolio completo para AUTO: top monedas que el scanner analiza
    const autoPortfolio = [
      'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
      'ADAUSDT', 'DOTUSDT', 'MATICUSDT', 'LINKUSDT', 'AVAXUSDT'
    ];

    this.tradingService.createStrategy({
      name: `Cacería ${this.request.symbol} - ${new Date().toLocaleString()}`,
      directionPreference: this.isAutoSelected ? SignalDirection.Auto : (this.request.direction === 'buy' ? SignalDirection.Long : SignalDirection.Short),
      selectedCryptos: this.isAutoSelected ? autoPortfolio : [this.request.symbol],
      customSymbols: this.isAutoSelected ? [] : [],
      leverage: this.request.leverage,
      capital: this.request.amount,
      riskLevel: RiskTolerance.Medium,
      autoStopLoss: true,
      takeProfitPercentage: this.request.takeProfit,
      stopLossPercentage: this.request.stopLoss,
      notificationsEnabled: true,
      isAutoMode: this.isAutoSelected,
      style: this.request.style,
      styleParametersJson: null
    }).subscribe({
      next: (strategy) => {
        console.log('✅ Estrategia creada:', strategy);

        // 2. Iniciar Sesión (siempre, auto o no)
        const sessionSymbol = this.isAutoSelected ? 'AUTO' : this.request.symbol;
        const timeframe = this.getTimeframeForStyle(this.request.style);

        this.tradingService.startSession({
          symbol: sessionSymbol,
          timeframe: timeframe
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
