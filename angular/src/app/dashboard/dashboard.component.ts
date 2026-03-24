import { Component, AfterViewInit, OnDestroy, inject, OnInit, ViewChild, ElementRef } from '@angular/core';
import { Subject, takeUntil, timeout, filter } from 'rxjs';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { IonIcon } from '@ionic/angular/standalone';
import { IconService } from 'src/shared/services/icon.service';
import { createChart, IChartApi, ISeriesApi, CandlestickData, CandlestickSeries, LineSeries } from 'lightweight-charts';
import { MarketDataService } from '../proxy/trading/market-data.service';
import { TradingService } from '../proxy/trading/trading.service';
import { TradingSessionDto, AnalysisLogDto, MarketAnalysisDto, OpportunityDto, SymbolTickerDto } from '../proxy/trading/models';
import { SimulatedTradeDto } from '../proxy/trading/dtos/models';
import { SimulatedTradeService } from '../proxy/trading/simulated-trade.service';
import { SignalStatsDto } from '../proxy/trading/dtos/models';
import { AnalysisLogType } from '../proxy/trading/analysis-log-type.enum';
import { DialogComponent } from 'src/shared/components/dialog/dialog.component';
import { CardContentComponent } from "src/shared/components/card-content/card-content.component";
import { TradingSignalrService } from '../services/trading-signalr.service';
import { AUTH_TOKEN_KEY } from '../core/auth.service';
import { AlertsComponent } from '../shared/components/alerts/alerts.component';
import { AlertService } from '../services/alert.service';
import { TradingPanelComponent } from 'src/shared/components/trading-panel/trading-panel.component';

interface TradingSignal {
  id: number;
  type: 'buy' | 'sell' | 'warning';
  price: number;
  confidence: number;
  timestamp: string;
  message: string;
  symbol?: string;
}

interface StageInfo {
  label: string;
  icon: string;
  color: string;
  description: string;
  ctaText: string;
  ctaVariant: 'primary' | 'warning' | 'success' | 'danger';
  lineColor: string;
  price: number;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    GlassButtonComponent,
    IonIcon,
    DialogComponent,
    AlertsComponent,
    TradingPanelComponent
  ],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss']
})
export class DashboardComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('chartContainer') set chartContainer(content: ElementRef) {
    if (content) {
      // Si ya hay un chart, destruirlo antes de crear uno nuevo
      if (this.chart) {
        this.chart.remove();
        this.chart = null;
      }
      // Si el contenedor aparece (por el *ngIf), inicializamos el gráfico
      this.initChart(content.nativeElement);
      this.loadData();
    }
  }

  private iconService = inject(IconService);
  private router = inject(Router);
  private marketDataService = inject(MarketDataService);
  private tradingService = inject(TradingService);
  private signalrService = inject(TradingSignalrService);
  public alertService = inject(AlertService);
  private destroy$ = new Subject<void>();

  // Estado del dashboard
  isAnalyzing = false;
  isHunting = false;
  currentSession: TradingSessionDto | null = null;
  analysisTime = '00:00:00';
  analysisLogs: AnalysisLogDto[] = [];
  marketAnalyses: MarketAnalysisDto[] = [];
  lastMotorSignal: string = '';
  lastNewsTitle: string = '';
  currentOpportunity: OpportunityDto | null = null;
  topOpportunities: any[] = [];
  showConfirmationDialog = false;
  sessionChecked = false;
  AnalysisLogType = AnalysisLogType; // Expose enum to template

  // Tabs & Categorized Data (Institutional Overhaul)
  activeTab: 'events' | 'whales' | 'liquidations' | 'scanner' | 'performance' = 'events';
  whaleLogs: any[] = [];
  liquidationLogs: any[] = [];
  scannerData: Map<string, any> = new Map(); // Real-time grid data

  // Header Institutional Metrics
  headerWhales: any[] = [];
  headerSqueezes: any[] = [];
  headerHeatmapCoins: any[] = [];
  performanceStats: SignalStatsDto | null = null;
  orderBook: any = { bids: [], asks: [] };
  recentTrades: any[] = [];
  orderBookViewMode: 'mixed' | 'bids' | 'asks' = 'mixed';

  // Toast de notificación de stage
  stageNotification: { message: string; icon: string; color: string; visible: boolean } | null = null;
  private toastTimeout: any;

  Object = Object; // Make Object available in template
  private analysisInterval: any;
  private refreshInterval: any;

  // Lightweight Charts
  private chart: IChartApi | null = null;
  private candlestickSeries: ISeriesApi<'Candlestick'> | null = null;
  private hmaSeries: ISeriesApi<'Line'> | null = null;
  private chartContainerElement: HTMLElement | null = null;

  // Configuración
  selectedSymbol = 'BTCUSDT';
  selectedTimeframe = '15';
  hmaPeriod = 50;

  symbols = [
    { value: 'BTCUSDT', label: 'BTC/USDT' },
    { value: 'ETHUSDT', label: 'ETH/USDT' },
    { value: 'SOLUSDT', label: 'SOL/USDT' },
    { value: 'BNBUSDT', label: 'BNB/USDT' },
    { value: 'XRPUSDT', label: 'XRP/USDT' },
    { value: 'ADAUSDT', label: 'ADA/USDT' },
    { value: 'DOGEUSDT', label: 'DOGE/USDT' },
    { value: 'MATICUSDT', label: 'MATIC/USDT' },
    { value: 'DOTUSDT', label: 'DOT/USDT' },
    { value: 'LTCUSDT', label: 'LTC/USDT' },
    { value: 'AVAXUSDT', label: 'AVAX/USDT' },
    { value: 'LINKUSDT', label: 'LINK/USDT' }
  ];

  timeframes = [
    { value: '1m', label: '1m' },
    { value: '5m', label: '5m' },
    { value: '15m', label: '15m' },
    { value: '30m', label: '30m' },
    { value: '1h', label: '1h' },
    { value: '2h', label: '2h' },
    { value: '4h', label: '4h' },
    { value: '1d', label: '1d' },
    { value: '1w', label: '1w' },
    { value: '1M', label: '1M' }
  ];

  // Tickers para el buscador
  tickers: SymbolTickerDto[] = [];
  filteredTickers: SymbolTickerDto[] = [];
  selectedTicker?: SymbolTickerDto;
  searchTerm: string = '';
  showSymbolSelector: boolean = false;

  // Simulation Simulation
  activeTrades: SimulatedTradeDto[] = [];
  tradeHistory: SimulatedTradeDto[] = [];
  consoleTab: 'positions' | 'orders' | 'history' = 'positions';
  private simulatedTradeService = inject(SimulatedTradeService);

  // Señales activas (reemplazado por logs reales)
  activeSignals: TradingSignal[] = [];

  // Sistema de alertas 1-2-3-4
  currentStage = 1;

  // Stages con líneas de gráfico
  stages: StageInfo[] = [
    {
      label: 'EVALUANDO',
      icon: 'search-outline',
      color: 'warning',
      lineColor: '#fbbf24', // Amarillo
      description: 'Buscando patrón ideal en el mercado...',
      ctaText: '🔍 Seguir cazando',
      ctaVariant: 'primary',
      price: 68000
    },
    {
      label: 'PREPARADO',
      icon: 'warning-outline',
      color: 'warning',
      lineColor: '#f97316', // Naranja
      description: '⚠️ OPORTUNIDAD INMINENTE - Zona de interés. Prepárate.',
      ctaText: '🎯 Preparar entrada',
      ctaVariant: 'warning',
      price: 68500
    },
    {
      label: 'COMPRA',
      icon: 'trending-up-outline',
      color: 'success',
      lineColor: '#22c55e', // Verde
      description: '🚀 ¡COMPRA AHORA! Objetivo: +4% | Apalancamiento: 3x',
      ctaText: '📊 Monitorear trade',
      ctaVariant: 'success',
      price: 68800
    },
    {
      label: 'VENTA',
      icon: 'trending-down-outline',
      color: 'danger',
      lineColor: '#ef4444', // Rojo
      description: '💰 ¡VENDE YA! Objetivo alcanzado. ¿Nuevo trade?',
      ctaText: '💰 Cerrar ciclo',
      ctaVariant: 'danger',
      price: 69500
    }
  ];

  // Precios para cálculo de posición y visualización
  chartPrices = {
    min: 0,
    max: 0,
    current: 0,
    last: 0,
    change: 0,
    changePercent: 0
  };

  ngOnInit() {
    console.log('[Dashboard] 🚀 ngOnInit ejecutado');
    this.checkActiveSession();
    this.loadTickers();
    this.loadActiveTrades();
    this.loadTradeHistory();

    // Verificar si hay sesión cacheada en SignalR (para el caso donde el evento ya llegó)
    const cachedSession = this.signalrService.getLastSession();
    if (cachedSession && !this.currentSession) {
      console.log('[Dashboard] 📦 Usando sesión cacheada de SignalR:', cachedSession.id);
      this.handleSessionUpdate(cachedSession);
    }

    this.subscribeToNotifications();

    // Polling de datos
    setInterval(() => {
      this.loadData();
      this.loadOrderBook();
      this.loadRecentTrades();
      this.loadTickers();
    }, 5000);
  }

  private subscribeToNotifications() {
    this.signalrService.sessionStarted$.pipe(
      takeUntil(this.destroy$),
      filter(session => session !== null)
    ).subscribe(session => {
      console.log('[Dashboard] Recibido SessionStarted vía SignalR');
      this.handleSessionUpdate(session);
    });

    this.signalrService.sessionEnded$.pipe(takeUntil(this.destroy$)).subscribe(() => {
      console.log('[Dashboard] Recibido SessionEnded vía SignalR');
      this.cleanupDashboard();
    });

    this.signalrService.stageAdvanced$.pipe(takeUntil(this.destroy$)).subscribe(session => {
      console.log('[Dashboard] Recibido StageAdvanced vía SignalR');
      const prevStage = this.currentStage;
      this.currentStage = session.currentStage || 1;
      this.currentSession = session;
      this.updateStagePrices(session);
      if (this.currentStage !== prevStage) {
        this.showStageToast(this.currentStage);
      }
    });

    // --- Simulated Trading Subscriptions ---
    this.signalrService.tradeOpened$.pipe(takeUntil(this.destroy$)).subscribe(trade => {
      this.activeTrades = [trade, ...this.activeTrades];
    });

    this.signalrService.tradeClosed$.pipe(takeUntil(this.destroy$)).subscribe(trade => {
      this.activeTrades = this.activeTrades.filter(t => t.id !== trade.id);
    });

    this.signalrService.tradeUpdate$.pipe(takeUntil(this.destroy$)).subscribe(update => {
      const index = this.activeTrades.findIndex(t => t.id === update.id);
      if (index !== -1) {
        this.activeTrades[index] = { ...this.activeTrades[index], ...update };
        // Trigger CD by reassigning the array (immutable pattern)
        this.activeTrades = [...this.activeTrades];
      }
    });

    // Real-time UI updates from alerts — ALL symbols populate the scanner tabs
    this.alertService.alerts$.pipe(takeUntil(this.destroy$)).subscribe(alerts => {
      if (!alerts || alerts.length === 0) return;

      const latestAlert = alerts[0]; // Alerts are sorted desc by timestamp in service

      // Update last motor signal for any alert
      if (latestAlert.message) {
        this.lastMotorSignal = latestAlert.message;
      }

      // Sync stage if it changed and we have an active session
      if (this.currentSession && latestAlert.stage && latestAlert.stage !== this.currentStage) {
        this.currentStage = latestAlert.stage;
      }

      // All alerts feed the institutional scanner — no symbol filter here
      this.processInstitutionalAlert(latestAlert);
    });
  }

  private processInstitutionalAlert(alert: any) {
    // Note: no session guard here — scanner tabs populate from all alerts regardless of session state
    // Normalize signal/direction names
    let symbol = alert.crypto || alert.Crypto || alert.symbol || alert.Symbol;

    // FALLBACK: If no symbol is provided, it's likely a global/macro event. 
    // We assign a generic symbol to avoid returning early and losing the data for Whales/Liqs.
    if (!symbol) {
      if (alert.message?.toLowerCase().includes('ballena')) symbol = '🐋 WHALE';
      else if (alert.message?.toLowerCase().includes('liquidación')) symbol = '💥 LIQ';
      else symbol = 'VERGE';
    }

    const winProb = alert.winProbability !== undefined ? alert.winProbability : (alert.WinProbability !== undefined ? alert.WinProbability : 0.5);
    const score = alert.score !== undefined ? alert.score : (alert.Score !== undefined ? alert.Score : 0);
    const confidence = alert.confidence !== undefined ? alert.confidence : (alert.Confidence !== undefined ? alert.Confidence : 0);

    // Tactical Price Mapping (Institutional 1% Standards)
    const entryPrice = alert.entryPrice || alert.EntryPrice || alert.price || alert.Price;
    const stopLoss = alert.stopLoss || alert.StopLoss;
    const takeProfit = alert.takeProfit || alert.TakeProfit;
    const patternName = alert.patternSignal || alert.patternName || alert.PatternSignal || alert.PatternName || 'Institutional Analysis';

    // Normalize direction with fallback
    let direction = alert.direction !== undefined ? alert.direction : alert.Direction;

    // FALLBACK: If direction is missing but score is decent, try to infer intention
    if (direction === undefined || direction === null) {
      if (winProb > 0.55) direction = 0; // Bias LONG
      else if (winProb < 0.45 && winProb > 0) direction = 1; // Bias SHORT
    }

    const regime = alert.structure || alert.regime || alert.Regime || 'N/A';
    let isSqueeze = alert.title?.toLowerCase().includes('squeeze') || alert.isSqueeze || alert.IsSqueeze || false;
    let whaleScore = alert.whaleInfluenceScore || alert.whaleInfluence || alert.WhaleInfluence || 0;
    const factorBreakdown = alert.patternSignal || alert.PatternSignal || '';
    const timeWindow = alert.timeWindow || alert.TimeWindow || '2-4h';
    const historicProb = winProb != null ? winProb * 100 : 0;

    // Keyword matching for generic logs without structured data
    if (alert.message) {
      const msg = alert.message.toLowerCase();
      if (msg.includes('ballena') || msg.includes('whale') || msg.includes('acumulación')) {
        if (whaleScore === 0) whaleScore = 65; // Default score if keyword matched
      }
      if (msg.includes('squeeze') || msg.includes('liquidación') || msg.includes('cluster')) {
        isSqueeze = true;
      }
    }

    // 1. Update Scanner (Grid Data)
    this.scannerData.set(symbol, {
      symbol: symbol,
      score: score,
      confidence: confidence,
      direction: direction,
      winProb: winProb,
      whaleInfluence: whaleScore,
      regime: regime,
      isSqueeze: isSqueeze,
      factorBreakdown: factorBreakdown,
      timeWindow: timeWindow,
      historicProb: historicProb,
      rrRatio: alert.riskRewardRatio || 0,
      sampleSize: alert.historicSampleSize || 0,
      // Tactical
      entryPrice: entryPrice,
      stopLoss: stopLoss,
      takeProfit: takeProfit,
      patternName: patternName
    });

    // 2. Whale Tab
    if (whaleScore > 0) {
      this.whaleLogs.unshift({
        symbol: symbol,
        influence: whaleScore,
        sentiment: alert.whaleSentiment || 'Neutral',
        message: alert.message,
        timestamp: alert.timestamp ? new Date(alert.timestamp) : new Date()
      });
      this.whaleLogs = this.uniqueBy(this.whaleLogs, (w: any) => w.symbol + w.timestamp.getTime()).slice(0, 50);

      // Update Header Whales (Top 3)
      this.headerWhales = this.whaleLogs
        .filter(w => w.influence > 40)
        .slice(0, 3);
    }

    // 3. Liquidations Tab
    if (isSqueeze || alert.message?.toLowerCase().includes('liquidación')) {
      this.liquidationLogs.unshift({
        symbol: symbol,
        message: alert.message,
        confidence: confidence || 80,
        timestamp: alert.timestamp ? new Date(alert.timestamp) : new Date()
      });
      this.liquidationLogs = this.uniqueBy(this.liquidationLogs, (l: any) => l.symbol + l.timestamp.getTime()).slice(0, 50);

      // Update Header Squeezes
      this.headerSqueezes = this.liquidationLogs.slice(0, 2);
    }

    // 4. Update Header Heatmap
    if (score > 0) {
      const existing = this.headerHeatmapCoins.find(c => c.symbol === symbol);
      if (existing) {
        existing.score = score;
      } else {
        this.headerHeatmapCoins.push({ symbol: symbol, score: score });
      }
      this.headerHeatmapCoins.sort((a, b: any) => b.score - a.score);
      this.headerHeatmapCoins = this.headerHeatmapCoins.slice(0, 3);
    }

    // 5. Check for Stagnation and Automatic Rotation
    this.checkStagnationAndRotate(symbol, score);
  }

  private uniqueBy(arr: any[], keyFn: (item: any) => string) {
    const seen = new Set();
    return arr.filter(item => {
      const key = keyFn(item);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  private checkStagnationAndRotate(symbol: string, score: number) {
    if (!this.currentSession || !this.isHunting) return;

    // Only rotate if the current symbol is weak and we find a much better one
    if (symbol === this.selectedSymbol && score < 60) {
      const bestAlternative = this.getScannerList().find(c => c.score > 75);
      if (bestAlternative && bestAlternative.symbol !== this.selectedSymbol) {
        console.log(`🔄 Rotando automáticamente a ${bestAlternative.symbol} (Score: ${bestAlternative.score})`);
        this.selectedSymbol = bestAlternative.symbol;
        this.onSymbolChange();
        this.showStageToast(1); // Reset toast message for the new target

        // Notify user about auto-rotation
        this.lastMotorSignal = `🔄 Rotando a ${bestAlternative.symbol} (score ${bestAlternative.score}) - Mejor oportunidad detectada.`;
      }
    }
  }

  setTab(tab: 'events' | 'whales' | 'liquidations' | 'scanner' | 'performance') {
    this.activeTab = tab;
  }

  getScannerList() {
    return Array.from(this.scannerData.values()).sort((a, b) => b.score - a.score);
  }

  private handleSessionUpdate(session: any) {
    this.currentSession = session;
    this.currentStage = session.currentStage || 1;
    this.isHunting = true;
    this.isAnalyzing = true;
    this.updateStagePrices(session);
    this.startAnalysisTimer();
    this.loadAnalysisLogs();
  }

  private updateStagePrices(session: TradingSessionDto) {
    // Stage 1: Evaluando → precio de entrada si existe, o dejar en blanco
    if (session.entryPrice) {
      this.stages[0].price = session.entryPrice;
    }
    // Stage 2: Preparado → precio de entrada real
    if (session.entryPrice) {
      this.stages[1].price = session.entryPrice;
      this.stages[1].description = `⚠️ OPORTUNIDAD INMINENTE - Entrada estimada: $${session.entryPrice.toLocaleString()}`;
    }
    // Stage 3: Compra → precio de entrada + TP + SL
    if (session.entryPrice && session.takeProfitPrice && session.stopLossPrice) {
      this.stages[2].price = session.entryPrice;
      this.stages[2].description = `🚀 ¡COMPRA! Entrada: $${session.entryPrice.toLocaleString()} | TP: $${session.takeProfitPrice.toLocaleString()} | SL: $${session.stopLossPrice.toLocaleString()}`;
    }
    // Stage 4: Venta → precio de TP
    if (session.takeProfitPrice) {
      this.stages[3].price = session.takeProfitPrice;
      this.stages[3].description = `💰 ¡VENDE! Objetivo: $${session.takeProfitPrice.toLocaleString()} alcanzado`;
    }
  }

  private showStageToast(stage: number) {
    if (this.toastTimeout) clearTimeout(this.toastTimeout);
    const stageMap: Record<number, { message: string; icon: string; color: string }> = {
      1: { message: '🔍 Evaluando mercado...', icon: 'search-outline', color: 'warning' },
      2: { message: '⚠️ OPORTUNIDAD DETECTADA — Prepara tu entrada', icon: 'warning-outline', color: 'warning' },
      3: { message: '🚀 ¡COMPRA AHORA! El motor confirmó la señal', icon: 'trending-up-outline', color: 'success' },
      4: { message: '💰 ¡OBJETIVO ALCANZADO! Considerá cerrar la posición', icon: 'checkmark-circle-outline', color: 'danger' },
    };
    this.stageNotification = { ...(stageMap[stage] ?? stageMap[1]), visible: true };
    this.toastTimeout = setTimeout(() => {
      if (this.stageNotification) this.stageNotification.visible = false;
    }, 6000);
  }

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
    this.startRefreshTimer();
  }

  ngOnDestroy() {
    window.removeEventListener('resize', this.onResize);
    if (this.analysisInterval) {
      clearInterval(this.analysisInterval);
    }
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
    if (this.chart) {
      this.chart.remove();
      this.chart = null;
    }
    this.destroy$.next();
    this.destroy$.complete();
  }

  initChart(container: HTMLElement) {
    this.chartContainerElement = container;
    if (this.chart) {
      this.chart.remove();
      this.chart = null;
    }

    this.chart = createChart(container, {
      width: container.clientWidth,
      height: 500,
      layout: {
        background: { color: '#0d1117' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: 'rgba(42, 46, 57, 0.5)' },
        horzLines: { color: 'rgba(42, 46, 57, 0.5)' },
      },
      rightPriceScale: {
        borderColor: 'rgba(197, 203, 206, 0.8)',
      },
      timeScale: {
        borderColor: 'rgba(197, 203, 206, 0.8)',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    this.candlestickSeries = this.chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    });

    this.hmaSeries = this.chart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 2,
      title: 'HMA 50',
    });

    window.addEventListener('resize', this.onResize);
  }

  private onResize = () => {
    if (this.chart && this.chartContainerElement) {
      this.chart.applyOptions({ width: this.chartContainerElement.clientWidth });
    }
  };

  loadData() {
    if (!this.chart || !this.candlestickSeries) return;

    this.marketDataService.getCandles({
      symbol: this.selectedSymbol,
      interval: this.selectedTimeframe,
      limit: 1000
    }).subscribe({
      next: (data) => {
        if (this.candlestickSeries) {
          // Sort data for lightweight-charts
          const sortedData = [...data].sort((a, b) => a.time - b.time);
          this.candlestickSeries.setData(sortedData as CandlestickData[]);

          this.updateHMA(sortedData);

          if (sortedData.length > 0) {
            const lastCandle = sortedData[sortedData.length - 1];
            this.chartPrices.current = Number(lastCandle.close);
          }
        }
      },
      error: (err) => console.error('Error fetching market data', err)
    });
  }

  loadOrderBook() {
    this.marketDataService.getOrderBook({
      symbol: this.selectedSymbol,
      limit: 20
    }).subscribe({
      next: (data) => {
        // Calculate totals for Bids (high to low)
        let bidTotal = 0;
        const bids = (data.bids || []).map(b => {
          bidTotal += b.amount;
          return { ...b, total: bidTotal };
        });

        // Calculate totals for Asks (low to high)
        let askTotal = 0;
        const asks = (data.asks || []).map(a => {
          askTotal += a.amount;
          return { ...a, total: askTotal };
        });

        this.orderBook = { bids, asks };
      },
      error: (err) => console.error('Error fetching order book', err)
    });
  }

  loadRecentTrades() {
    this.marketDataService.getRecentTrades({
      symbol: this.selectedSymbol,
      limit: 20
    }).subscribe({
      next: (data) => {
        this.recentTrades = data;
      },
      error: (err) => console.error('Error fetching recent trades', err)
    });
  }

  startRefreshTimer() {
    // Carga inicial rápida
    this.loadAnalysisLogs();
    this.loadLivePerformance();

    this.refreshInterval = setInterval(() => {
      // Ya NO llamamos a checkActiveSession() incondicionalmente cada 10s
      // porque SignalR nos avisa de los cambios de estado.
      // Solo refrescamos los logs y datos si estamos en cacería.
      if (this.isHunting) {
        this.loadData();
        this.loadAnalysisLogs();
        this.loadLivePerformance();
        this.loadOrderBook();
        this.loadRecentTrades();
      }
    }, 10000);
  }

  loadLivePerformance() {
    this.tradingService.getSignalStats(this.selectedSymbol === 'AUTO' ? undefined : this.selectedSymbol).subscribe({
      next: (stats) => {
        this.performanceStats = stats;
        console.log('[Dashboard] 📈 Live Performance loaded:', stats);
      },
      error: (err) => console.error('[Dashboard] Error loading signal stats', err)
    });
  }

  loadActiveTrades() {
    this.simulatedTradeService.getActiveTrades().subscribe({
      next: (trades) => this.activeTrades = trades,
      error: (err) => console.error('Error loading active trades', err)
    });
  }

  loadTradeHistory() {
    this.simulatedTradeService.getTradeHistory().subscribe({
      next: (history) => this.tradeHistory = history,
      error: (err) => console.error('Error loading trade history', err)
    });
  }

  setConsoleTab(tab: 'positions' | 'orders' | 'history') {
    this.consoleTab = tab;
    if (tab === 'history') {
      this.loadTradeHistory();
    } else if (tab === 'positions') {
      this.loadActiveTrades();
    }
  }

  closePosition(tradeId: string) {
    this.simulatedTradeService.closeTrade(tradeId).subscribe({
      next: () => {
        // SignalR will handle the list update, but we can proactively filter
        this.activeTrades = this.activeTrades.filter(t => t.id !== tradeId);
      },
      error: (err) => console.error('Error closing trade', err)
    });
  }

  loadAnalysisLogs() {
    // Evitar consultar logs si no hay sesión activa (GUID vacío causa 500)
    if (!this.currentSession ||
      !this.currentSession.id ||
      this.currentSession.id === '00000000-0000-0000-0000-000000000000' ||
      this.currentSession.id === '00000000-0000-0000-0000-000000000001') {
      console.warn('[Dashboard] ⛔ No hay sessionId válido. Ignorando consulta de logs.');
      return;
    }

    const sessionId = this.currentSession.id;
    console.log('[Dashboard] 📊 Cargando logs para sesión:', sessionId);

    this.tradingService.getAnalysisLogs(sessionId).subscribe({
      next: (logs) => {
        this.analysisLogs = logs;
        this.processScannerLogs(logs);
      },
      error: (err) => console.error('[Dashboard] Error fetching analysis logs', err)
    });
  }

  processScannerLogs(logs: AnalysisLogDto[]) {
    this.marketAnalyses = [];
    if (!logs || logs.length === 0) return;

    // Deduplicate logs to reduce UI noise
    const cleanLogs = this.deduplicateLogs(logs);

    // Process most recent logs first
    const sortedLogs = [...cleanLogs].sort((a, b) =>
      new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );

    // 1. First Pass: Enrich and Process ALL logs for Institutional state
    for (const log of sortedLogs) {
      if (!log.message) continue;

      const data = this.parseJson(log.dataJson);

      // Handle Opportunity Ranking (Phase 3/20) - Support both legacy 'top' and new 'rankings' keys
      if (log.logType === AnalysisLogType.OpportunityRanking) {
        const rankings = data?.rankings || data?.top || data?.Rankings || data?.Top;
        if (rankings && Array.isArray(rankings)) {
          this.topOpportunities = rankings;

          // Enrich the log message with the actual coins (Top 3)
          const top3 = rankings.slice(0, 3).map((r: any) => `${r.symbol || r.Symbol}(${r.score || r.Score})`).join(', ');
          log.message = `📈 TOP 3: ${top3}`;

          // Populate Scanner with each ranked coin
          rankings.forEach((rank: any) => {
            this.processInstitutionalAlert({
              ...rank,
              symbol: rank.symbol || rank.Symbol,
              timestamp: log.timestamp,
              message: `Oportunidad detectada (#${rank.symbol || rank.Symbol})`
            });
          });
        }
      }

      // Process any log with structured data for institutional tabs
      if (data) {
        this.processInstitutionalAlert({
          ...data,
          symbol: log.symbol,
          message: log.message,
          timestamp: log.timestamp
        });
      }

      // Populate lastMotorSignal
      if (log.level === 'warning' || log.level === 'success' ||
        log.logType === AnalysisLogType.AlertEntry ||
        log.logType === AnalysisLogType.AlertPrepare) {
        this.lastMotorSignal = log.message;
      }

      // --- Populate lastNewsTitle from sentiment in dataJson ---
      if (data?.fng && !this.lastNewsTitle) {
        this.lastNewsTitle = `Miedo & Codicia: ${data.fng}/100`;
      }

      // --- Build marketAnalyses from dataJson RSI and symbol ---
      if (data?.rsi != null && log.symbol) {
        const symbol = log.symbol;
        const rsi = Number(data.rsi);
        const existing = this.marketAnalyses.find(a => a.symbol === symbol);
        if (existing) {
          existing.rsi = rsi;
          existing.description = this.getRsiDescription(rsi);
          existing.signal = rsi > 55 ? 'LONG' : (rsi < 45 ? 'SHORT' : 'NEUTRAL');
          if (data.score != null) existing.confidence = Number(data.score);
        } else {
          this.marketAnalyses.push({
            symbol,
            rsi,
            description: this.generateMarketDescription({ rsi, symbol, trend: rsi > 50 ? 'alcista' : 'bajista', confidence: data.score, bosDetected: data.bosDetected } as any),
            signal: rsi > 55 ? 'LONG' : (rsi < 45 ? 'SHORT' : 'NEUTRAL'),
            confidence: data.score != null ? Number(data.score) : 0,
            trend: rsi > 50 ? 'alcista' : 'bajista',
            bosDetected: data.bosDetected || false,
            // Institutional Sprint 5
            whaleSentiment: data.whaleSentiment,
            whaleInfluence: data.whaleInfluence,
            isSqueeze: data.isSqueeze,
            macroQuiet: data.macroQuiet,
            macroReason: data.macroReason
          } as any);
        }
      }

      // --- Institutional Processing (Seed historical data) ---
      if (data) {
        this.processInstitutionalAlert({
          ...data,
          symbol: log.symbol,
          message: log.message,
          timestamp: log.timestamp
        });
      }

      // --- Detect opportunity (score >= 70 or Entry/Prepare decision) ---
      if (!this.currentOpportunity && data) {
        const isEntry = data.decision === 'Entry' || log.logType === AnalysisLogType.AlertEntry || Number(data.score) >= 70;
        const isPrepare = data.decision === 'Prepare' || log.logType === AnalysisLogType.AlertPrepare || (Number(data.score) >= 50 && Number(data.score) < 70);

        if (isEntry || isPrepare) {
          this.currentOpportunity = {
            symbol: log.symbol || 'AUTO',
            confidence: Number(data.score) || (isEntry ? 70 : 50),
            signal: isEntry ? 'LONG' : 'NEUTRAL',
            reason: log.message,
            entryMin: data.entryMin,
            entryMax: data.entryMax
          };
        }
      }
    }

    // 2. Second Pass: Filter for the "EVENTOS" UI tab to avoid noise
    this.analysisLogs = sortedLogs.filter(log => {
      if (!log.message) return false;
      const msg = log.message.toLowerCase();

      // Keep significant events
      if (log.level === 'success' || log.level === 'warning' ||
        log.logType === AnalysisLogType.AlertEntry ||
        log.logType === AnalysisLogType.AlertPrepare ||
        msg.includes('top 3') ||
        msg.includes('cacería') ||
        msg.includes('squeeze') ||
        msg.includes('ballena')) return true;

      // Filter context logs: only show high scores (>70) or every 10th
      if (msg.includes('[context]')) {
        const data = this.parseJson(log.dataJson);
        const score = data?.score || data?.Score || 0;
        return (score >= 70) || (sortedLogs.indexOf(log) % 10 === 0);
      }

      return true;
    });

    console.log(`[Dashboard] 📊 Log processing complete. Scanner symbols: ${Array.from(this.scannerData.keys()).join(', ')}`);
  }

  getRsiDescription(rsi: number): string {
    if (rsi < 30) return 'sobreventa extrema | posible reversión alcista';
    if (rsi < 45) return 'acercándose a sobreventa | monitoreando';
    if (rsi > 70) return 'sobrecompra | posible corrección';
    if (rsi > 55) return 'fuerza alcista confirmada';
    return 'zona neutral | sin señal clara';
  }

  generateMarketDescription(data: any): string {
    const rsi = data.rsi;
    let desc = '';
    if (rsi < 30) desc = 'sobreventa extrema';
    else if (rsi < 45) desc = 'posible reversión alcista';
    else if (rsi > 70) desc = 'sobrecompra';
    else if (rsi > 55) desc = 'fuerza alcista';
    else desc = `${data.trend} | volumen normal`;

    if (data.isSqueeze) desc += ' | 🔥 SQUEEZE DETECTADO';
    if (data.whaleInfluence > 60) desc += ' | 🐋 ACTIVIDAD BALLENA ALTA';
    return desc;
  }

  dismissOpportunity() {
    this.currentOpportunity = null;
  }

  goToTrade(alertId?: string) {
    if (alertId) {
      this.router.navigate(['/execute-trade']);
      this.alertService.markAsRead(alertId);
    } else if (this.currentOpportunity) {
      this.router.navigate(['/execute-trade'], {
        queryParams: {
          symbol: this.currentOpportunity.symbol,
          direction: this.currentOpportunity.signal
        }
      });
      this.currentOpportunity = null;
    }
  }


  startAnalysisTimer() {
    if (this.analysisInterval) clearInterval(this.analysisInterval);

    let seconds = 0;
    // Si ya hay una sesión activa, calculamos el tiempo desde que inició
    if (this.currentSession?.startTime) {
      const startTime = new Date(this.currentSession.startTime).getTime();
      seconds = Math.floor((Date.now() - startTime) / 1000);
    }

    this.analysisInterval = setInterval(() => {
      seconds++;
      const hours = Math.floor(seconds / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      const secs = seconds % 60;

      this.analysisTime =
        `${hours.toString().padStart(2, '0')}:` +
        `${minutes.toString().padStart(2, '0')}:` +
        `${secs.toString().padStart(2, '0')}`;
    }, 1000);
  }

  checkActiveSession() {
    console.log('[Dashboard] 🔍 Verificando sesión activa...');

    this.tradingService.getCurrentSession()
      .pipe(
        timeout(10000)
      )
      .subscribe({
        next: (session: TradingSessionDto) => {
          if (session && session.id && session.id !== '00000000-0000-0000-0000-000000000000' && session.id !== '00000000-0000-0000-0000-000000000001') {
            console.log('[Dashboard] ✅ Sesión encontrada:', session.id);
            this.sessionChecked = true;
            this.currentSession = session;
            this.currentStage = session.currentStage || 1;
            this.isHunting = true;
            this.isAnalyzing = true;
            this.startAnalysisTimer();
            this.loadAnalysisLogs(); // Load initially
          } else {
            console.log('[Dashboard] ℹ️ No hay sesión activa válida');
            this.sessionChecked = true;
            this.cleanupDashboard();
          }
        },
        error: (error) => {
          console.error('[Dashboard] ❌ Error verificando sesión:', {
            status: error.status,
            message: error.message
          });
          this.sessionChecked = true; // Set to true to stop spinners
        }
      });
  }

  // startHunt() removed - now handled in ExecuteTradeComponent

  loadTickers() {
    this.marketDataService.getTickers().subscribe({
      next: (data) => {
        this.tickers = data;
        this.filterTickers();
        
        // Actualizar el ticker seleccionado para mostrar precio en el header
        this.selectedTicker = this.tickers.find(t => t.symbol === this.selectedSymbol);
      },
      error: (err) => console.error('Error al cargar tickers:', err)
    });
  }

  filterTickers() {
    if (!this.searchTerm) {
      this.filteredTickers = this.tickers.slice(0, 50); // Mostrar top 50 por defecto
    } else {
      const term = this.searchTerm.toUpperCase();
      this.filteredTickers = this.tickers.filter(t => t.symbol.includes(term));
    }
  }

  selectSymbol(symbol: string) {
    this.selectedSymbol = symbol;
    this.showSymbolSelector = false;
    this.onSymbolChange();
  }

  onSymbolChange() {
    console.log('Cambiando a símbolo:', this.selectedSymbol);
    
    // Resetear datos previos
    this.chartPrices = { min: 0, max: 0, current: 0, last: 0, change: 0, changePercent: 0 };
    this.orderBook = { bids: [], asks: [] };
    this.recentTrades = [];
    
    // Actualizar ticker seleccionado
    this.selectedTicker = this.tickers.find(t => t.symbol === this.selectedSymbol);

    this.loadData();
    this.loadOrderBook();
    this.loadRecentTrades();
  }

  // Métodos de control
  toggleAnalysis() {
    this.isAnalyzing = !this.isAnalyzing;
    if (this.isAnalyzing) {
      this.startAnalysisTimer();
    } else {
      clearInterval(this.analysisInterval);
    }
  }

  changeSymbol(symbol: string) {
    this.selectedSymbol = symbol;
    this.loadData();
    this.loadOrderBook();
    this.loadRecentTrades();
  }

  changeTimeframe(timeframe: string) {
    this.selectedTimeframe = timeframe;
    this.loadData();
  }

  onBack() {
    this.router.navigate(['/']);
  }

  onOpenAdvanced() {
    this.router.navigate(['/dashboard-advanced']);
  }

  onQuickTrade() {
    this.router.navigate(['/execute-trade']);
  }

  onExecuteTrade() {
    console.log('Ejecutar trade rápido - Estado:', this.getCurrentStage().label);

    if (this.currentSession) {
      this.tradingService.advanceStage(this.currentSession.id).subscribe({
        next: (session) => {
          console.log('✅ Etapa avanzada en backend. Actualizando UI localmente...');
          this.currentStage = session.currentStage || 1;
          this.currentSession = session;
          // SignalR también enviará el evento, pero ya lo actualizamos aquí
        },
        error: (err) => console.error('❌ Error advancing stage', err)
      });
    } else {
      // Si por alguna razón no hay sesión, redirigir a configuración
      this.onQuickTrade();
    }
  }

  finalizeHunt() {
    if (!this.currentSession) return;
    this.showConfirmationDialog = true;
  }

  confirmEndHunt() {
    if (!this.currentSession) return;

    this.tradingService.finalizeHunt(this.currentSession.id).subscribe({
      next: () => {
        console.log('✅ Cacería finalizada en backend. Limpiando UI inmediatamente...');
        this.showConfirmationDialog = false;
        this.cleanupDashboard(); // Limpieza inmediata local
      },
      error: (err) => {
        console.error('❌ Error finalizing hunt', err);
        this.showConfirmationDialog = false;
      }
    });
  }

  private cleanupDashboard() {
    this.isHunting = false;
    this.isAnalyzing = false;
    this.currentSession = null;
    this.analysisLogs = [];
    this.marketAnalyses = [];
    this.currentOpportunity = null;
    this.lastMotorSignal = '';
    this.lastNewsTitle = '';
    this.analysisTime = '00:00:00';
    if (this.analysisInterval) {
      clearInterval(this.analysisInterval);
    }
    // Volver al estado inicial de stages
    this.currentStage = 1;
  }

  // Métodos auxiliares
  getCurrentStage(): StageInfo {
    return this.stages[this.currentStage - 1] || this.stages[0];
  }

  getSignalIcon(log: AnalysisLogDto): string {
    if (log.logType === AnalysisLogType.AlertEntry) return 'rocket-outline';
    if (log.logType === AnalysisLogType.AlertPrepare) return 'timer-outline';
    if (log.logType === AnalysisLogType.AlertInvalidated) return 'close-circle-outline';
    if (log.logType === AnalysisLogType.AlertExit) return 'exit-outline';

    switch (log.level) {
      case 'success': return 'trending-up-outline';
      case 'danger': return 'trending-down-outline';
      case 'warning': return 'warning-outline';
      default: return 'alert-circle-outline';
    }
  }

  getLogColor(log: AnalysisLogDto): string {
    if (log.logType === AnalysisLogType.AlertEntry) return '#10b981'; // Emerald
    if (log.logType === AnalysisLogType.AlertPrepare) return '#f59e0b'; // Amber
    if (log.logType === AnalysisLogType.AlertInvalidated) return '#94a3b8'; // Slate
    if (log.logType === AnalysisLogType.AlertExit) return '#ef4444'; // Red

    switch (log.level) {
      case 'success': return '#10b981';
      case 'danger': return '#ef4444';
      case 'warning': return '#f59e0b';
      case 'info': return '#3b82f6';
      default: return '#94a3b8';
    }
  }

  getDynamicCTA() {
    return {
      text: this.getCurrentStage().ctaText,
      variant: this.getCurrentStage().ctaVariant
    };
  }

  getCurrentDescription(): string {
    switch (this.currentStage) {
      case 1: return 'Buscando patrón ideal en el mercado...';
      case 2: return 'Oportunidad detectada - Evaluando entrada...';
      case 3: return 'Trade activo - Monitoreando posición...';
      case 4: return 'Preparando salida - Objetivo cercano...';
      default: return '';
    }
  }

  getProgressPercentage(): number {
    return (this.currentStage / 4) * 100;
  }

  isStageActive(stageIndex: number): boolean {
    return this.currentStage > stageIndex;
  }

  isStageCurrent(stageIndex: number): boolean {
    return this.currentStage === stageIndex + 1;
  }

  parseJson(json: string): any {
    if (!json) return null;
    try {
      return JSON.parse(json);
    } catch (e) {
      return null;
    }
  }

  // --- Indicator Calculations ---

  updateHMA(data: any[]) {
    if (!this.hmaSeries || data.length < this.hmaPeriod) {
      if (this.hmaSeries) this.hmaSeries.setData([]);
      return;
    }

    const prices = data.map(d => Number(d.close));
    const hmaValues = this.calculateHMA(prices, this.hmaPeriod);

    const hmaData = hmaValues.map((val, i) => ({
      time: data[i + (data.length - hmaValues.length)].time,
      value: val
    }));

    this.hmaSeries.setData(hmaData);
    this.hmaSeries.applyOptions({ title: `HMA ${this.hmaPeriod}` });
  }

  private calculateHMA(data: number[], period: number): number[] {
    const halfPeriod = Math.floor(period / 2);
    const sqrtPeriod = Math.floor(Math.sqrt(period));

    const wmaHalf = this.calculateWMA(data, halfPeriod);
    const wmaFull = this.calculateWMA(data, period);

    if (wmaFull.length === 0) return [];

    const diff = [];
    const offset = period - halfPeriod;
    for (let i = 0; i < wmaFull.length; i++) {
      diff.push(2 * wmaHalf[i + offset] - wmaFull[i]);
    }

    return this.calculateWMA(diff, sqrtPeriod);
  }

  private calculateWMA(data: number[], period: number): number[] {
    const wma = [];
    if (data.length < period) return [];

    const weightSum = (period * (period + 1)) / 2;

    for (let i = period - 1; i < data.length; i++) {
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += data[i - j] * (period - j);
      }
      wma.push(sum / weightSum);
    }
    return wma;
  }

  // --- UI Handlers ---


  onTimeframeChange(tf: string) {
    this.selectedTimeframe = tf;
    this.loadData();
  }

  onHmaChange() {
    // Force recalculation if we have data
    if (this.candlestickSeries) {
      const currentData = (this.candlestickSeries as any)._data?._items || [];
      // Handle private access if necessary, or just reload
      this.loadData();
    }
  }

  clearAlerts() {
    this.alertService.clearAllAlerts();
  }

  private deduplicateLogs(logs: AnalysisLogDto[]): AnalysisLogDto[] {
    const seen = new Set();
    return logs.filter(log => {
      // Create a key based on symbol, message, and minute-precision timestamp
      // This allows seeing the SAME message if it happens in different minutes,
      // providing a sense of "activity" without spamming the EXACT same thing in a second.
      const date = new Date(log.timestamp);
      const minuteKey = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}-${date.getHours()}-${date.getMinutes()}`;

      let msg = log.message || '';
      if (msg.includes('CACERÍA ESTANCADA')) {
        msg = msg.split('señales claras en')[0]; // Strip the time part
      }
      const messageKey = msg.split('|')[0].trim();

      // Key: Symbol + MessagePrefix + LogType + Minute
      const key = `${log.symbol}-${messageKey}-${log.logType}-${minuteKey}`;

      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }
}
