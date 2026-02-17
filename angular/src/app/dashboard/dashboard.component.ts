import { Component, AfterViewInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { IonIcon } from '@ionic/angular/standalone';
import { IconService } from 'src/shared/services/icon.service';
import { createChart, IChartApi, ISeriesApi, CandlestickData, CandlestickSeries } from 'lightweight-charts';
import { MarketDataService } from '../proxy/trading/market-data.service';
import { TradingService } from '../proxy/trading/trading.service';
import { TradingSessionDto, AnalysisLogDto, MarketAnalysisDto, OpportunityDto } from '../proxy/trading/models';
import { CardContentComponent } from "src/shared/components/card-content/card-content.component";

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
    IonIcon
  ],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss']
})
export class DashboardComponent implements AfterViewInit, OnDestroy {
  private iconService = inject(IconService);
  private router = inject(Router);
  private marketDataService = inject(MarketDataService);
  private tradingService = inject(TradingService);

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

  Object = Object; // Make Object available in template
  private analysisInterval: any;
  private refreshInterval: any;

  // Lightweight Charts
  private chart: IChartApi | null = null;
  private candlestickSeries: ISeriesApi<'Candlestick'> | null = null;

  // Configuración
  selectedSymbol = 'BTCUSDT';
  selectedTimeframe = '15';

  symbols = [
    { value: 'BTCUSDT', label: 'BTC/USDT' },
    { value: 'ETHUSDT', label: 'ETH/USDT' },
    { value: 'SOLUSDT', label: 'SOL/USDT' },
    { value: 'BNBUSDT', label: 'BNB/USDT' },
    { value: 'XRPUSDT', label: 'XRP/USDT' }
  ];

  timeframes = [
    { value: '1', label: '1 minuto' },
    { value: '5', label: '5 minutos' },
    { value: '15', label: '15 minutos' },
    { value: '60', label: '1 hora' },
    { value: '240', label: '4 horas' },
    { value: '1D', label: '1 día' }
  ];

  // Señales activas (mock)
  activeSignals: TradingSignal[] = [
    {
      id: 1,
      type: 'warning',
      price: 68500,
      confidence: 85,
      timestamp: '15:30',
      message: 'BTC entrando en zona de interés',
      symbol: 'BTCUSDT'
    },
    {
      id: 2,
      type: 'buy',
      price: 3850,
      confidence: 92,
      timestamp: '14:15',
      message: '¡COMPRA CONFIRMADA! ETH',
      symbol: 'ETHUSDT'
    },
    {
      id: 3,
      type: 'warning',
      price: 195,
      confidence: 78,
      timestamp: '13:45',
      message: 'Prepárate para vender SOL',
      symbol: 'SOLUSDT'
    }
  ];

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

  // Precios simulados para cálculo de posición
  private chartPrices = {
    min: 67000,
    max: 70000,
    current: 68500
  };

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
    this.initChart();
    this.loadData();
    this.checkActiveSession();
    this.startRefreshTimer();
  }

  ngOnDestroy() {
    if (this.analysisInterval) {
      clearInterval(this.analysisInterval);
    }
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
    if (this.chart) {
      this.chart.remove();
    }
  }

  initChart() {
    const chartContainer = document.getElementById('tradingview-chart');
    if (!chartContainer) return;

    this.chart = createChart(chartContainer, {
      width: chartContainer.clientWidth,
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

    window.addEventListener('resize', () => {
      this.chart?.applyOptions({ width: chartContainer.clientWidth });
    });
  }

  loadData() {
    this.marketDataService.getCandles({
      symbol: this.selectedSymbol,
      interval: `${this.selectedTimeframe}m`,
      limit: 100
    }).subscribe({
      next: (data) => {
        if (this.candlestickSeries) {
          // Sort data for lightweight-charts
          const sortedData = [...data].sort((a, b) => a.time - b.time);
          this.candlestickSeries.setData(sortedData as CandlestickData[]);

          if (sortedData.length > 0) {
            const lastCandle = sortedData[sortedData.length - 1];
            this.chartPrices.current = Number(lastCandle.close);
          }
        }
      },
      error: (err) => console.error('Error fetching market data', err)
    });
  }

  startRefreshTimer() {
    // Carga inicial rápida
    this.loadAnalysisLogs();

    this.refreshInterval = setInterval(() => {
      this.loadData();
      this.checkActiveSession();
      this.loadAnalysisLogs();
    }, 10000); // 10 segundos para ver logs en tiempo real
  }

  loadAnalysisLogs() {
    // SIEMPRE traer logs globales (usando Guid vacío)
    const sessionId = '00000000-0000-0000-0000-000000000000';

    this.tradingService.getAnalysisLogs(sessionId).subscribe({
      next: (logs) => {
        // Solo actualizamos si hay cambios o si es la primera carga
        if (logs.length !== this.analysisLogs.length) {
          this.analysisLogs = logs;
          this.processScannerLogs(logs);
        }
      },
      error: (err) => console.error('Error fetching analysis logs', err)
    });
  }

  processScannerLogs(logs: AnalysisLogDto[]) {
    this.marketAnalyses = [];
    logs.forEach(log => {
      // Detectar logs de scanner normales
      if (log.message?.startsWith('Scanner:') && log.dataJson) {
        const data = this.parseJson(log.dataJson) as MarketAnalysisDto;
        if (data && !this.marketAnalyses.some(a => a.symbol === data.symbol)) {
          this.marketAnalyses.push(data);

          if (data.confidence >= 80 && !this.currentOpportunity) {
            this.currentOpportunity = {
              symbol: data.symbol,
              confidence: data.confidence,
              signal: data.signal,
              reason: data.description
            };
          }
        }
      }

      // Detectar logs de OPORTUNIDAD (para el modal)
      if (log.message?.includes('� OPORTUNIDAD DETECTADA') && log.dataJson) {
        const data = this.parseJson(log.dataJson) as OpportunityDto;
        if (data && !this.currentOpportunity) {
          this.currentOpportunity = data;
        }
      }

      if (log.level === 'success' || log.level === 'warning') {
        if (!log.message?.startsWith('Scanner:')) {
          this.lastMotorSignal = log.message;
        } else if (this.marketAnalyses.length > 0) {
          // Si es del scanner, formateamos como la imagen
          const m = this.marketAnalyses[0];
          this.lastMotorSignal = `RSI en ${m.symbol} recuperándose desde zona de sobreventa (${m.rsi - 9} → ${m.rsi}). Volumen +18%. Posible reversión alcista en formación.`;
        }
      }
    });
  }

  generateMarketDescription(data: MarketAnalysisDto): string {
    const rsi = data.rsi;
    if (rsi < 30) return 'sobreventa extrema | divergencia alcista';
    if (rsi < 45) return 'posible reversión alcista';
    if (rsi > 70) return 'sobrecompra | riesgo de corrección';
    if (rsi > 55) return 'fuerza alcista confirmada';
    return `${data.trend} | volumen normal`;
  }

  dismissOpportunity() {
    this.currentOpportunity = null;
  }

  goToTrade() {
    if (this.currentOpportunity) {
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
    this.tradingService.getCurrentSession().subscribe({
      next: (session) => {
        if (session) {
          this.currentSession = session;
          this.currentStage = session.currentStage || 1;
          this.isHunting = true;
          this.isAnalyzing = true;
          this.startAnalysisTimer();
          this.loadAnalysisLogs(); // Load initially
        } else {
          this.isHunting = false;
          this.isAnalyzing = false;
          this.currentSession = null;
          this.analysisLogs = [];
          clearInterval(this.analysisInterval);
          this.analysisTime = '00:00:00';
        }
      },
      error: (err) => console.error('Error checking active session', err)
    });
  }

  // startHunt() removed - now handled in ExecuteTradeComponent

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
          console.log('Etapa avanzada:', session);
          this.checkActiveSession(); // Actualizar UI
        },
        error: (err) => console.error('Error advancing stage', err)
      });
    } else {
      // Si por alguna razón no hay sesión, redirigir a configuración
      this.onQuickTrade();
    }
  }

  // Métodos auxiliares
  getCurrentStage(): StageInfo {
    return this.stages[this.currentStage - 1] || this.stages[0];
  }

  getSignalColor(type: 'buy' | 'sell' | 'warning'): string {
    switch (type) {
      case 'buy': return 'success';
      case 'sell': return 'danger';
      case 'warning': return 'warning';
      default: return 'primary';
    }
  }

  getSignalIcon(type: 'buy' | 'sell' | 'warning'): string {
    switch (type) {
      case 'buy': return 'trending-up-outline';
      case 'sell': return 'trending-down-outline';
      case 'warning': return 'warning-outline';
      default: return 'alert-circle-outline';
    }
  }

  getDynamicCTA() {
    return {
      text: this.getCurrentStage().ctaText,
      variant: this.getCurrentStage().ctaVariant
    };
  }

  // Nuevo método para obtener la descripción según el stage
  getCurrentDescription(): string {
    switch (this.currentStage) {
      case 1: return 'Buscando patrón ideal en el mercado...';
      case 2: return 'Oportunidad detectada - Evaluando entrada...';
      case 3: return 'Trade activo - Monitoreando posición...';
      case 4: return 'Preparando salida - Objetivo cercano...';
      default: return '';
    }
  }

  // Método para obtener el progreso en porcentaje
  getProgressPercentage(): number {
    return (this.currentStage / 4) * 100;
  }

  // Método para verificar si un stage está activo
  isStageActive(stageIndex: number): boolean {
    return this.currentStage > stageIndex;
  }

  // Método para verificar si es el stage actual
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
}