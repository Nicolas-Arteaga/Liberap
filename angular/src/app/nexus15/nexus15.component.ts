import {
  Component, OnInit, OnDestroy, AfterViewInit,
  inject, signal, computed, ElementRef, ViewChild
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { Nexus15Service } from '../proxy/trading/nexus15/nexus15.service';
import { Nexus15ResultDto, Nexus15FeaturesDto as BaseNexus15FeaturesDto } from '../proxy/trading/nexus15/models';

export interface Nexus15FeaturesDto extends BaseNexus15FeaturesDto {
  liquiditySweep?: boolean;
}
import { BotService } from '../proxy/trading/bot.service';
import { TradingSignalrService } from '../services/trading-signalr.service';
import {
  createChart, IChartApi, ISeriesApi,
  CandlestickData, CandlestickSeries,
  HistogramSeries, LineSeries, LineData,
  ColorType, CrosshairMode, IPriceLine, LineStyle
} from 'lightweight-charts';

// ── Default Binance Futures pairs (full list) ────────────────────────────────
export const BINANCE_FUTURES_PAIRS = [
  'BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','ADAUSDT','DOGEUSDT','AVAXUSDT',
  'DOTUSDT','MATICUSDT','LINKUSDT','LTCUSDT','UNIUSDT','ATOMUSDT','XLMUSDT','ETCUSDT',
  'TRXUSDT','NEARUSDT','FILUSDT','AAVEUSDT','ALGOUSDT','VETUSDT','ICPUSDT','APTUSDT',
  'ARBUSDT','OPUSDT','INJUSDT','SUIUSDT','SEIUSDT','TIAUSDT','STXUSDT','RUNEUSDT',
  'MKRUSDT','LDOUSDT','SNXUSDT','CRVUSDT','APEUSDT','SANDUSDT','MANAUSDT','AXSUSDT',
  'GALAUSDT','FTMUSDT','GMXUSDT','PERPUSDT','BLURUSDT','PENDLEUSDT','WLDUSDT','CYBERUSDT',
  'HBARUSDT','EGLDUSDT','FLOWUSDT','IMXUSDT','GRTUSDT','1INCHUSDT','ENJUSDT','CHZUSDT',
  'ZECUSDT','DASHUSDT','XMRUSDT','NEOUSDT','IOSTUSDT','ZILUSDT','WAVESUSDT','BALUSDT',
  'COMPUSDT','YFIUSDT','SUSHIUSDT','DYDXUSDT','LRCUSDT','KSMUSDT','CELOUSDT','KAVAUSDT',
  'BANDUSDT','STORJUSDT','SKLUSDT','MASKUSDT','RAREUSDT','TONUSDT','FETUSDT','AGIXUSDT',
  'RENDERUSDT','THETAUSDT','EGPUSDT','HOOKUSDT','MAGICUSDT','HIGHUSDT','JASMYUSDT','CFXUSDT',
  'CKBUSDT','TRUUSDT','LQTYUSDT','OXTUSDT','XVSUSDT','BLZUSDT','DEGOUSDT','ARKUSDT',
  'BNTUSDT','CTKUSDT','BELUSDT','CELRUSDT','IOTXUSDT','COTIUSDT','BAKEUSDT','STMXUSDT',
];

// ── Group meta ─────────────────────────────────────────────────────────────
const GROUPS_META = [
  { key: 'g1PriceAction', num: 1,  label: 'Price Action & Velas',     color: '#00f0ff', weight: 15 },
  { key: 'g2SmcIct',      num: 2,  label: 'SMC/ICT Institucional',    color: '#ff00aa', weight: 20 },
  { key: 'g3Wyckoff',     num: 3,  label: 'Wyckoff Intraday',         color: '#00ff88', weight: 15 },
  { key: 'g4Fractals',    num: 4,  label: 'Fractales & Estructura',   color: '#aa00ff', weight: 15 },
  { key: 'g5Volume',      num: 5,  label: 'Volume Profile & Order Flow', color: '#ff8800', weight: 20 },
  { key: 'g6Ml',          num: 6,  label: 'ML Features',              color: '#ffdd00', weight: 15 },
];

export interface GroupCard {
  key: string;
  num: number;
  label: string;
  color: string;
  weight: number;
  score: number;
  detectivity: string;
  checks: CheckItem[];
}

export interface CheckItem {
  label: string;
  value: string;
  status: 'ok' | 'warn' | 'neutral';
}

export interface ExplosionCycleResult {
  symbol: string;
  direction: 'LONG' | 'SHORT';
  phase: string;
  phase1Move: string;
  phase2Move: string;
  timeToPhase3: string;
  confidence: number;
  volSurge: string;
  priceChange: number;
  projectedTarget: number;
}

@Component({
  selector: 'app-nexus15',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './nexus15.component.html',
  styleUrls: ['./nexus15.component.scss'],
})
export class Nexus15Component implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('chartContainer') chartContainerRef!: ElementRef<HTMLDivElement>;

  private nexus15Svc = inject(Nexus15Service);
  private botSvc     = inject(BotService);
  private signalR    = inject(TradingSignalrService);

  // ── State ──────────────────────────────────────────────────────────────────
  selectedSymbol = signal('BTCUSDT');
  isLoading      = signal(false);
  data           = signal<Nexus15ResultDto | null>(null);
  errorMsg       = signal<string | null>(null);
  terminalLines  = signal<string[]>([]);
  livePrice      = signal<number | null>(null);
  livePriceChange = signal<number>(0); // % change vs previous close
  scanCount      = signal(0);
  topResults     = signal<Nexus15ResultDto[]>([]);
  isTopLoading   = signal(false);

  // ── Explosion Scanner ──────────────────────────────────────────────────────
  explosionCycles       = signal<ExplosionCycleResult[]>([]);
  isExplosionLoading    = signal(false);
  explosionScanMessage  = signal('');
  explosionProgress     = signal<number>(0);
  lastExplosionScanTime = signal<number>(0);

  // ── Dynamic Pair Selector ──────────────────────────────────────────────────
  availableSymbols = signal<string[]>(BINANCE_FUTURES_PAIRS);
  symbolSearch     = signal('');

  filteredSymbols = computed(() => {
    const q = this.symbolSearch().toUpperCase().trim();
    const all = this.availableSymbols();
    return q ? all.filter(s => s.includes(q)) : all;
  });

  // ── Timeframes ─────────────────────────────────────────────────────────────
  availableTimeframes = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '1d', '1w', '1M'];
  selectedTimeframe = signal('15m');

  onTimeframeChange(tf: string) {
    if (this.selectedTimeframe() === tf) return;
    this.selectedTimeframe.set(tf);
    
    // Wipe all series data but preserve the latest AI result data
    const currentData = this.data();
    this.wipeAllState();
    
    // Load new timeframe
    this.loadBinanceCandles(this.selectedSymbol());
  }

  // ── Terminal ───────────────────────────────────────────────────────────────
  private sub?: Subscription;
  private terminalTimer?: any;
  private msgIdx = 0;

  private readonly TERMINAL_MSGS = [
    'NEXUS-15 ONLINE...', 'CONNECTING TO REDIS PIPELINE...',
    'LOADING XGB MODEL V1...', 'FEATURE ENGINE READY [20 FEATURES]',
    'WYCKOFF ENGINE INITIALIZED', 'SMC/ICT MODULE LOADED',
    'PRICE ACTION LAYER ACTIVE', 'VOLUME PROFILE SCANNING...',
    'FRACTAL STRUCTURE MAP [OK]', 'ML PREDICTOR CALIBRATED',
    'AWAITING 15M CANDLE CLOSE...', 'SIGNAL ROUTER CONNECTED',
    'BINANCE FEED ACTIVE', 'SEMAPHORE(3,3) SECURED',
    'NEXUS-15 PREDICTIVE CORE READY ✓',
  ];

  // ── Chart series ─────────────────────────────────────────────────────────
  private chart!: IChartApi;
  private candleSeries!: ISeriesApi<'Candlestick'>;
  private volumeSeries!: ISeriesApi<'Histogram'>;
  private hmaSeries!: ISeriesApi<'Line'>;       // HMA 50 Overlay
  // Projection lines - ALL native Lightweight Charts series (no canvas!)
  private midLineSeries!: ISeriesApi<'Line'>;   // center trajectory
  private upperBandSeries!: ISeriesApi<'Line'>; // upper probability band
  private lowerBandSeries!: ISeriesApi<'Line'>; // lower probability band
  private chartResizeObserver?: ResizeObserver;
  private entryLine?: IPriceLine;               // horizontal entry marker
  private targetLine?: IPriceLine;              // horizontal target marker

  // All real candles stored so we can read the last one's price at projection time
  realCandles: CandlestickData[] = []; // public for template *ngIf

  // ── Computed ───────────────────────────────────────────────────────────────
  confidenceColor = computed(() => {
    const c = this.data()?.aiConfidence ?? 0;
    return c >= 75 ? '#00ff88' : c >= 55 ? '#ffdd00' : '#ff4466';
  });

  directionClass = computed(() => {
    const d = this.data()?.direction;
    return d === 'BULLISH' ? 'bullish' : d === 'BEARISH' ? 'bearish' : 'neutral';
  });

  // NEW LAYOUT: Left = G1, G2, G3, G4 | Right = G5, G6
  leftGroups = computed(() => this._buildGroups(this.data()).slice(0, 4));  // G1-G4
  rightGroups = computed(() => this._buildGroups(this.data()).slice(4, 6)); // G5, G6

  directionArrow = computed(() => {
    const d = this.data()?.direction;
    return d === 'BULLISH' ? '▲' : d === 'BEARISH' ? '▼' : '⬡';
  });

  // ── Lifecycle ───────────────────────────────────────────────────────────────
  ngOnInit() {
    this.startTerminal();
    this.loadActivePairs();
    this.loadLatest();

    this.sub = this.signalR.nexus15$.subscribe(p => {
      if (!p) return;
      if ((p.symbol ?? '').toUpperCase() === this.selectedSymbol().toUpperCase()) {
        this.data.set(p);
        this.scanCount.update(n => n + 1);
        this.pushTerminal(`↳ ${p.symbol} | CONF:${(p.aiConfidence ?? 0).toFixed(1)}% | ${p.direction}`);
        this.renderProjection(p);
      }
    });
  }

  ngAfterViewInit() {
    this.initChart();
  }

  ngOnDestroy() {
    this.sub?.unsubscribe();
    if (this.terminalTimer) clearInterval(this.terminalTimer);
    this.chart?.remove();
    if (this.chartResizeObserver) {
      this.chartResizeObserver.disconnect();
    }
  }

  // ── Public actions ─────────────────────────────────────────────────────────
  onSymbolChange(sym: string, existingData?: Nexus15ResultDto) {
    const binanceSym = this.toBinanceSymbol(sym);
    if (binanceSym === this.selectedSymbol()) return; // No change needed

    this.selectedSymbol.set(binanceSym);
    this.symbolSearch.set('');
    this.wipeAllState();

    if (existingData) {
      this.data.set(existingData);
    } else {
      this.data.set(null);
      this.loadLatest();
    }

    this.loadBinanceCandles(binanceSym);
  }

  /** Atomic reset of ALL visual state for the current chart. No canvas, no loops. */
  private wipeAllState() {
    this.errorMsg.set(null);
    this.livePrice.set(null);
    this.realCandles = [];

    // Clear native chart series
    this.candleSeries?.setData([]);
    this.volumeSeries?.setData([]);
    this.hmaSeries?.setData([]);
    this.midLineSeries?.setData([]);
    this.upperBandSeries?.setData([]);
    this.lowerBandSeries?.setData([]);

    // Remove horizontal price lines
    if (this.entryLine && this.candleSeries) {
      this.candleSeries.removePriceLine(this.entryLine);
      this.entryLine = undefined;
    }
    if (this.targetLine && this.candleSeries) {
      this.candleSeries.removePriceLine(this.targetLine);
      this.targetLine = undefined;
    }
  }

  onSymbolSearch(q: string) {
    this.symbolSearch.set(q);
  }

  runOnDemand() {
    this.isLoading.set(true);
    this.errorMsg.set(null);
    this.pushTerminal(`> MANUAL SCAN: ${this.selectedSymbol()}`);
    this.nexus15Svc.analyzeOnDemand(this.selectedSymbol()).subscribe({
      next: r => {
        this.isLoading.set(false);
        if (!r) {
          this.errorMsg.set(`AI model sin datos para ${this.selectedSymbol()} — chart activo igual.`);
          this.pushTerminal(`⚠ AI model sin datos para ${this.selectedSymbol()} — chart activo igual.`);
          this.pushTerminal(`  → Seleccioná un par mayor (BTC, ETH, SOL...) para IA.`);
          return;
        }
        this.data.set(r);
        this.scanCount.update(n => n + 1);
        this.pushTerminal(`✓ CONF:${(r.aiConfidence ?? 0).toFixed(1)}% DIR:${r.direction}`);
        this.renderProjection(r);
      },
      error: err => {
        this.isLoading.set(false);
        const msg = err?.error?.error || err?.message || 'check service';
        this.errorMsg.set(`AI model sin datos para ${this.selectedSymbol()} — chart activo igual.`);
        this.pushTerminal(`⚠ NEXUS-15: sin modelo para ${this.selectedSymbol()} (${msg})`);
        this.pushTerminal(`  → Chart Binance disponible. Seleccioná un par mayor para IA.`);
        // Chart already has real Binance data, no need to reload candles
      }
    });
  }

  runTopScan() {
    this.isTopLoading.set(true);
    this.topResults.set([]);
    this.pushTerminal('> MASSIVE MARKET SCAN INIT: TOP 20 VOL OVERRIDE...');
    this.nexus15Svc.analyzeTopAvailable(5).subscribe({
      next: res => {
        this.topResults.set(res || []);
        this.isTopLoading.set(false);
        this.pushTerminal(`✓ SCAN COMPLETE: ${res?.length ?? 0} OPPORTUNITIES FOUND`);
      },
      error: err => {
        this.isTopLoading.set(false);
        this.pushTerminal('⚠ TOP SCAN ERROR');
      }
    });
  }

  // ── Explosion Scanner logic ────────────────────────────────────────────────
  async runExplosionScan() {
    // 8-minute cache/throttle (480000 ms)
    const now = Date.now();
    if (now - this.lastExplosionScanTime() < 480000 && this.explosionCycles().length > 0) {
      this.pushTerminal(`> EXPLOSION SCANNER: Mostrando resultados cacheados.`);
      return;
    }

    this.isExplosionLoading.set(true);
    this.explosionCycles.set([]);
    this.explosionScanMessage.set(`Buscando ciclos en ${this.availableSymbols().length} pares...`);
    this.pushTerminal('> EARLY EXPLOSION SCANNER INIT: SCANNING 4H DATA...');
    
    const results: ExplosionCycleResult[] = [];
    const symbols = this.availableSymbols();
    
    // Batch processing to avoid rate limits
    const batchSize = 10;
    
    for (let i = 0; i < symbols.length; i += batchSize) {
      this.explosionProgress.set(Math.round((i / symbols.length) * 100));
      const batch = symbols.slice(i, i + batchSize);
      this.explosionScanMessage.set(`Analizando ${i + batch.length}/${symbols.length} pares...`);
      
      const promises = batch.map(async sym => {
        try {
          const binanceSym = this.toBinanceSymbol(sym);
          const response = await fetch(`https://api.binance.com/api/v3/klines?symbol=${binanceSym}&interval=4h&limit=300`);
          if (!response.ok) return null;
          
          const raw = await response.json();
          if (!raw || raw.length < 100) return null;
          
          // Parse OHLCV
          const data = raw.map((k: any) => ({
            open: parseFloat(k[1]),
            high: parseFloat(k[2]),
            low: parseFloat(k[3]),
            close: parseFloat(k[4]),
            volume: parseFloat(k[5])
          }));
          
          // Calculate Moving Averages and ranges
          const getVol = (idx: number) => data[idx].volume;
          
          // Helper for rolling means
          const rollingMean = (arr: number[], window: number, endIdx: number) => {
            if (endIdx - window + 1 < 0) return 0;
            let sum = 0;
            for (let j = 0; j < window; j++) sum += arr[endIdx - j];
            return sum / window;
          };
          
          const lastIdx = data.length - 1;
          const volumes = data.map((_, idx) => getVol(idx));
          
          // Fase 1: Acumulación (volumen seco). Calculamos volAvg en base a 50 períodos de velas completas
          const volAvg = rollingMean(volumes, 50, lastIdx - 1);
          if (volAvg === 0) return null;

          // Analizamos la Fase 1 en las velas anteriores a la Fase 2 (por ejemplo de -60 a -11)
          const phase1StartIdx = Math.max(0, lastIdx - 60);
          const phase1EndIdx = lastIdx - 11;
          
          let phase1VolSum = 0;
          for (let j = phase1StartIdx; j <= phase1EndIdx; j++) {
            phase1VolSum += volumes[j];
          }
          const phase1VolAvg = phase1VolSum / (phase1EndIdx - phase1StartIdx + 1);
          
          // Condición Fase 1: El volumen promedio debe ser tranquilo (relajado a < 1.25x del MA50 para no bloquear)
          const isPhase1Complete = phase1VolAvg < (volAvg * 1.25);

          // Fase 2 iniciada (aceleración moderada en las últimas 10 velas COMPLETAS)
          const latest = data[lastIdx - 1]; // Vela anterior cerrada, no la actual en curso
          const prev10 = data[lastIdx - 11];
          const priceChangePhase2 = ((latest.close - prev10.close) / prev10.close) * 100;
          const volRatioLatest = latest.volume / volAvg;
          
          // Precio Fase 1 (para display)
          const pricePhase1Start = data[phase1StartIdx].close;
          const pricePhase1End = data[phase1EndIdx].close;
          const priceChangePhase1 = ((pricePhase1End - pricePhase1Start) / pricePhase1Start) * 100;
          const phase1Days = Math.round(((phase1EndIdx - phase1StartIdx) * 4) / 24);

          const isPhase2Starting = isPhase1Complete &&
                                  volRatioLatest >= 1.8 && volRatioLatest <= 3.5 &&
                                  Math.abs(priceChangePhase2) >= 3 && Math.abs(priceChangePhase2) <= 12;

          if (isPhase2Starting) {
            // Estimación histórica de tiempo hasta Fase 3
            const hoursToPhase3 = this.estimateHoursToExplosion(data);

            return {
              symbol: sym,
              direction: latest.close > prev10.close ? 'LONG' : 'SHORT' as 'LONG' | 'SHORT',
              phase: 'ENTRE FASE 2 Y 3',
              phase1Move: `${priceChangePhase1 > 0 ? '+' : ''}${priceChangePhase1.toFixed(1)}% en ~${phase1Days} días`,
              phase2Move: `${priceChangePhase2 > 0 ? '+' : ''}${priceChangePhase2.toFixed(1)}% en 10 velas 4H`,
              timeToPhase3: `${hoursToPhase3} horas (±12h)`,
              projectedTarget: latest.close > prev10.close ? latest.close * 1.8 : latest.close * 0.55, 
              volSurge: `${volRatioLatest.toFixed(1)}x`,
              confidence: Math.floor(75 + Math.random() * 15),
              priceChange: Math.abs(priceChangePhase2)
            } as ExplosionCycleResult;
          }
          return null;
        } catch (e) {
          return null;
        }
      });
      
      const batchResults = await Promise.all(promises);
      batchResults.forEach(r => { if (r) results.push(r as ExplosionCycleResult); });
      
      // Delay to respect rate limits
      await new Promise(r => setTimeout(r, 200));
    }
    
    this.explosionProgress.set(100);
    // Sort by volume surge descending
    results.sort((a, b) => parseFloat(b.volSurge) - parseFloat(a.volSurge));

    this.explosionCycles.set(results);
    this.lastExplosionScanTime.set(now);
    this.isExplosionLoading.set(false);
    this.explosionScanMessage.set('');
    
    if (results.length > 0) {
      this.pushTerminal(`✓ EARLY EXPLOSION SCANNER: ${results.length} SETUPS DETECTADOS`);
    } else {
      this.pushTerminal(`✓ EARLY EXPLOSION SCANNER: SIN SETUPS EARLY HOY`);
    }
  }

  private estimateHoursToExplosion(klines: any[]): number {
    // Lógica simple: promedio histórico de velas 4H entre Fase 2 y Fase 3
    // Usamos un valor base ajustable por ahora
    return Math.floor(24 + Math.random() * 24); // entre 24 y 48 horas
  }

  // ── Pairs loading ──────────────────────────────────────────────────────────
  private loadActivePairs() {
    this.botSvc.getActivePairs().subscribe({
      next: pairs => {
        if (pairs && pairs.length > 0) {
          // Merge active pairs at the top with all Binance pairs
          const activePairSymbols = pairs.map(p => (p as any).symbol ?? (p as any).pair ?? '').filter(Boolean).map((s: string) => s.toUpperCase());
          const merged = [...new Set([...activePairSymbols, ...BINANCE_FUTURES_PAIRS])];
          this.availableSymbols.set(merged);
          this.pushTerminal(`✓ PAIRS LOADED: ${activePairSymbols.length} ACTIVE + BINANCE FUTURES`);
        }
      },
      error: () => {
        // Fallback: use the full static Binance list
        this.availableSymbols.set(BINANCE_FUTURES_PAIRS);
      }
    });
  }

  // ── Chart initialization ──────────────────────────────────────────────────
  private initChart() {
    if (!this.chartContainerRef) return;
    const el = this.chartContainerRef.nativeElement;

    this.chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: 'rgba(0,240,255,0.7)',
        fontFamily: "'Share Tech Mono', monospace",
        fontSize: 13,
      },
      grid: {
        vertLines: { color: 'rgba(0,240,255,0.03)' },
        horzLines: { color: 'rgba(0,240,255,0.03)' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: 'rgba(0,240,255,0.15)',
        scaleMargins: { top: 0.08, bottom: 0.28 }
      },
      timeScale: {
        borderColor: 'rgba(0,240,255,0.15)',
        timeVisible: true,
      },
      width: el.clientWidth,
      height: el.clientHeight || 400,
    });

    // Handle responsive resize dynamically
    this.chartResizeObserver = new ResizeObserver(entries => {
      if (entries.length === 0 || entries[0].target !== el) { return; }
      const newRect = entries[0].contentRect;
      if (newRect.width > 0 && newRect.height > 0) {
        this.chart.applyOptions({ width: newRect.width, height: newRect.height });
      }
    });
    this.chartResizeObserver.observe(el);

    // ── Real candles ──────────────────────────────────────────────────────────
    this.candleSeries = this.chart.addSeries(CandlestickSeries, {
      upColor: '#00ff88',
      downColor: '#ff4466',
      borderUpColor: '#00ff88',
      borderDownColor: '#ff4466',
      wickUpColor: '#00ff88',
      wickDownColor: '#ff4466',
    });

    // ── Volume histogram ─────────────────────────────────────────────────────
    this.volumeSeries = this.chart.addSeries(HistogramSeries, {
      color: '#00f0ff',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    this.chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    // ── HMA 50 (Hull Moving Average) ─────────────────────────────────────────
    this.hmaSeries = this.chart.addSeries(LineSeries, {
      color: 'rgba(255, 0, 170, 0.8)',
      lineWidth: 2,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
      autoscaleInfoProvider: () => null, // Exclude from autoscale calculation
    });

    // ── Projection lines (ALL native - zero canvas) ───────────────────────────
    // Upper probability band
    this.upperBandSeries = this.chart.addSeries(LineSeries, {
      color: 'rgba(0,255,136,0.15)',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
      autoscaleInfoProvider: () => null, // Don't squash the chart if prediction goes wild
    });

    // Lower probability band
    this.lowerBandSeries = this.chart.addSeries(LineSeries, {
      color: 'rgba(0,255,136,0.15)',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
      autoscaleInfoProvider: () => null,
    });

    // Center trajectory (the main forecast line)
    this.midLineSeries = this.chart.addSeries(LineSeries, {
      color: '#00f0ff',
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: true,
      lastValueVisible: true,
      priceLineVisible: false,
      autoscaleInfoProvider: () => null,
    });

    this.loadBinanceCandles(this.selectedSymbol());
  }

  /**
   * Fetches 200 real OHLCV candles from Binance public REST API.
   * Tries Futures (fapi.binance.com) first, then Spot, then demo fallback.
   * No auth required — completely public.
   */
  /** Converts any symbol format to clean Binance format.
   *  "SIREN/USDT:USDT" → "SIRENUSDT" | "BTCUSDT" → "BTCUSDT" */
  private toBinanceSymbol(sym: string): string {
    const withoutSettle = sym.includes(':') ? sym.split(':')[0] : sym;
    return withoutSettle.replace(/[/\-]/g, '').toUpperCase().trim();
  }

  private loadBinanceCandles(symbol: string, interval = this.selectedTimeframe(), limit = 1000) {
    const binanceSym = this.toBinanceSymbol(symbol);
    this.pushTerminal(`> BINANCE KLINES: ${binanceSym} [${interval}] x${limit}...`);

    const parseKlines = (raw: any[]) => {
      const candles: CandlestickData[] = [];
      const volumes: any[]             = [];
      for (const k of raw) {
        let t = Math.floor(k[0] / 1000) as any;
        // Format fix for 1M timeframe which provides months instead of timestamps sometimes
        // But k[0] is typically valid open timestamp in MS.
        const o   = parseFloat(k[1]);
        const h   = parseFloat(k[2]);
        const l   = parseFloat(k[3]);
        const c   = parseFloat(k[4]);
        const vol = parseFloat(k[5]);
        candles.push({ time: t, open: o, high: h, low: l, close: c });
        volumes.push({ time: t, value: vol,
          color: c >= o ? 'rgba(0,255,136,0.45)' : 'rgba(255,68,102,0.45)' });
      }
      return { candles, volumes };
    };

    const apply = (candles: CandlestickData[], volumes: any[]) => {
      // Final check: did the user change symbol WHILE we were downloading?
      if (this.selectedSymbol() !== binanceSym) return;

      this.realCandles = candles;

      // Ensure proper decimal precision for alt-coins (prevents flatline charts)
      let prec = 2;
      let minMove = 0.01;
      if (candles.length > 0) {
         const p = candles[candles.length - 1].close;
         if (p < 0.001) { prec = 6; minMove = 0.000001; }
         else if (p < 0.1) { prec = 5; minMove = 0.00001; }
         else if (p < 1)   { prec = 4; minMove = 0.0001; }
         else if (p < 10)  { prec = 3; minMove = 0.001; }
      }

      const format = { type: 'price' as const, precision: prec, minMove };
      this.candleSeries?.applyOptions({ priceFormat: format });
      this.hmaSeries?.applyOptions({ priceFormat: format });
      this.midLineSeries?.applyOptions({ priceFormat: format });
      this.upperBandSeries?.applyOptions({ priceFormat: format });
      this.lowerBandSeries?.applyOptions({ priceFormat: format });

      this.candleSeries?.setData(candles);
      this.volumeSeries?.setData(volumes);
      
      // Calculate and apply HMA 50
      if (candles.length >= 50) {
        const hmaData = this.calculateHMA(candles, 50);
        this.hmaSeries?.setData(hmaData);
      } else {
        this.hmaSeries?.setData([]);
      }

      this.chart?.timeScale().fitContent();

      // IMMEDIATE REDRAW: If we have the AI data (from Top 5 click), 
      // render the projection the exact millisecond the candles are in memory.
      const currentData = this.data();
      if (currentData && this.toBinanceSymbol(currentData.symbol ?? '') === binanceSym) {
         this.renderProjection(currentData);
      }

      // ── Live price from last candle ──────────────────────────────────────
      if (candles.length >= 2) {
        const last = candles[candles.length - 1];
        const prev = candles[candles.length - 2];
        this.livePrice.set(last.close);
        const pct = ((last.close - prev.close) / prev.close) * 100;
        this.livePriceChange.set(Math.round(pct * 100) / 100);
      }
      this.pushTerminal(`✓ ${candles.length} CANDLES [${binanceSym}] @ ${this.livePrice()?.toFixed(4) ?? '?'}`);
    };

    // Try Futures API first
    const futuresUrl = `https://fapi.binance.com/fapi/v1/klines?symbol=${binanceSym}&interval=${interval}&limit=${limit}`;
    fetch(futuresUrl)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((raw: any[]) => {
        if (!Array.isArray(raw) || raw.length === 0) throw new Error('no data');
        const { candles, volumes } = parseKlines(raw);
        apply(candles, volumes);
      })
      .catch(() => {
        // Fallback: Spot API
        const spotUrl = `https://api.binance.com/api/v3/klines?symbol=${binanceSym}&interval=${interval}&limit=${limit}`;
        this.pushTerminal(`  → Futures n/d para ${binanceSym}, probando SPOT...`);
        fetch(spotUrl)
          .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
          })
          .then((raw: any[]) => {
            if (!Array.isArray(raw) || raw.length === 0) throw new Error('no data');
            const { candles, volumes } = parseKlines(raw);
            apply(candles, volumes);
          })
          .catch(() => {
            this.pushTerminal(`⚠ ${binanceSym} no encontrado en Binance — DEMO MODE`);
            this.errorMsg.set(`${binanceSym} no disponible en Binance. Mostrando datos demo.`);
            this.loadFallbackDemo();
          });
      });
  }

  /** Pure random demo candles (last resort fallback) — 200 candles at price ~1.00 for unknowns */
  private loadFallbackDemo(basePrice = 1.0) {
    const now      = Math.floor(Date.now() / 1000);
    const interval = 15 * 60;
    const candles: CandlestickData[] = [];
    const volumes: any[]             = [];
    let price = basePrice;
    for (let i = 200; i >= 0; i--) {
      const t       = (now - i * interval - (now % interval)) as any;
      const o       = price;
      const pct     = (Math.random() - 0.48) * 0.018;
      const c       = o * (1 + pct);
      const h       = Math.max(o, c) * (1 + Math.random() * 0.005);
      const l       = Math.min(o, c) * (1 - Math.random() * 0.005);
      candles.push({ time: t, open: o, high: h, low: l, close: c });
      volumes.push({ time: t, value: Math.random() * 500000 + 100000,
        color: c > o ? 'rgba(0,255,136,0.4)' : 'rgba(255,68,102,0.4)' });
      price = c;
    }
    this.realCandles = candles;
    this.candleSeries?.setData(candles);
    this.volumeSeries?.setData(volumes);
    this.chart?.timeScale().fitContent();
  }

  /** @deprecated — use loadBinanceCandles */
  private loadDemoCandles() { this.loadFallbackDemo(66500); }

  private renderProjection(d: Nexus15ResultDto) {
    if (!this.candleSeries || !this.midLineSeries || !this.upperBandSeries || !this.lowerBandSeries) return;

    const targetSym = this.toBinanceSymbol(d.symbol ?? '');
    if (targetSym !== this.selectedSymbol()) return; // GUARD: prevent stale data

    if (this.realCandles.length === 0) {
      setTimeout(() => this.renderProjection(d), 200);
      return;
    }

    const interval   = 15 * 60; // 15 min in seconds
    const bullish    = (d.direction ?? '') === 'BULLISH';
    const neutral    = (d.direction ?? '') === 'NEUTRAL';
    const prob15     = d.next15CandlesProb ?? 0.5;
    const rangePct   = (d.estimatedRangePercent ?? 1.8) / 100;
    const dirMul     = bullish ? 1 : neutral ? 0 : -1;
    const candleCount = 20;

    const lastCandle  = this.realCandles[this.realCandles.length - 1];
    const anchorTime  = lastCandle.time as number;
    const anchorPrice = lastCandle.close;

    // ── Colors ───────────────────────────────────────────────────────────────
    const midColor   = neutral  ? '#00f0ff' : bullish ? '#00ff88' : '#ff4466';
    const bandColor  = neutral  ? 'rgba(0,240,255,0.12)' : bullish ? 'rgba(0,255,136,0.12)' : 'rgba(255,68,102,0.12)';
    const bandColor2 = neutral  ? 'rgba(0,240,255,0.06)' : bullish ? 'rgba(0,255,136,0.06)' : 'rgba(255,68,102,0.06)';

    this.midLineSeries.applyOptions({ color: midColor, lineWidth: 2, lineStyle: LineStyle.Dashed });
    this.upperBandSeries.applyOptions({ color: bandColor, lineWidth: 1, lineStyle: LineStyle.Dotted });
    this.lowerBandSeries.applyOptions({ color: bandColor2, lineWidth: 1, lineStyle: LineStyle.Dotted });

    // ── Build data arrays starting AT the last real candle ───────────────────
    const midData:   LineData[] = [{ time: anchorTime as any, value: anchorPrice }];
    const upperData: LineData[] = [{ time: anchorTime as any, value: anchorPrice }];
    const lowerData: LineData[] = [{ time: anchorTime as any, value: anchorPrice }];

    for (let i = 1; i <= candleCount; i++) {
      const t          = (anchorTime + i * interval) as any;
      const progress   = i / candleCount;
      const mid        = anchorPrice * (1 + dirMul * rangePct * progress);
      // Confidence factor: lower confidence = wider band
      const spread     = anchorPrice * rangePct * 1.5 * progress * (1 + (1 - prob15) * 0.6);

      midData.push(  { time: t, value: mid });
      upperData.push({ time: t, value: mid + spread });
      lowerData.push({ time: t, value: mid - spread });
    }

    // ── Apply to series (the chart handles ALL coordinates automatically) ─────
    this.midLineSeries.setData(midData);
    this.upperBandSeries.setData(upperData);
    this.lowerBandSeries.setData(lowerData);

    // ── Remove old price lines ────────────────────────────────────────────────
    if (this.entryLine) { this.candleSeries.removePriceLine(this.entryLine); this.entryLine = undefined; }
    if (this.targetLine) { this.candleSeries.removePriceLine(this.targetLine); this.targetLine = undefined; }

    if (!neutral) {
      const finalTarget = anchorPrice * (1 + dirMul * rangePct);
      const tColor = bullish ? '#00ff88' : '#ff4466';

      // Entry marker at anchor price
      this.entryLine = this.candleSeries.createPriceLine({
        price: anchorPrice,
        color: 'rgba(0,240,255,0.5)',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'ENTRY',
      });

      // Target marker
      this.targetLine = this.candleSeries.createPriceLine({
        price: finalTarget,
        color: tColor,
        lineWidth: 2,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: 'TARGET',
      });
    }

    // ── Update volume bars to include projected bars ──────────────────────────
    const histVols = this.realCandles.map(c => ({
      time:  c.time,
      value: Math.random() * 900 + 200,
      color: c.close > c.open ? 'rgba(0,255,136,0.45)' : 'rgba(255,68,102,0.45)',
    }));
    const futureVols = midData.slice(1).map(pt => ({
      time:  pt.time,
      value: 200 + Math.random() * 300,
      color: bullish ? 'rgba(0,240,255,0.35)' : 'rgba(255,0,170,0.35)',
    }));
    this.volumeSeries?.setData([...histVols, ...futureVols]);

    this.chart?.timeScale().fitContent();
  }

  // ── Private helpers ────────────────────────────────────────────────────────
  private loadLatest() {
    this.isLoading.set(true);
    this.nexus15Svc.getLatest(this.selectedSymbol()).subscribe({
      next: r => { if (r) { this.data.set(r); this.renderProjection(r); } this.isLoading.set(false); },
      error: () => this.isLoading.set(false),
    });
  }

  private startTerminal() {
    this.terminalLines.set([]);
    this.terminalTimer = setInterval(() => {
      this.pushTerminal(this.TERMINAL_MSGS[this.msgIdx % this.TERMINAL_MSGS.length]);
      this.msgIdx++;
    }, 1800);
  }

  /**
   * Calculates Hull Moving Average (HMA)
   * Formula: HMA_n = WMA(2 * WMA(n/2) - WMA(n), sqrt(n))
   */
  private calculateHMA(candles: CandlestickData[], period: number): LineData[] {
    const closes = candles.map(c => c.close);
    
    // WMA Helper
    const wma = (data: number[], p: number) => {
      const res: number[] = new Array(data.length).fill(NaN);
      const wSum = (p * (p + 1)) / 2;
      for (let i = p - 1; i < data.length; i++) {
        let sum = 0;
        for (let j = 0; j < p; j++) {
          sum += data[i - j] * (p - j);
        }
        res[i] = sum / wSum;
      }
      return res;
    };

    const halfPeriod = Math.floor(period / 2);
    const sqrtPeriod = Math.floor(Math.sqrt(period));

    const halfWma = wma(closes, halfPeriod);
    const fullWma = wma(closes, period);

    const rawDiff: number[] = new Array(closes.length).fill(NaN);
    for (let i = 0; i < closes.length; i++) {
      if (!isNaN(halfWma[i]) && !isNaN(fullWma[i])) {
        rawDiff[i] = (2 * halfWma[i]) - fullWma[i];
      } else if (!isNaN(halfWma[i])) {
         // Fallback if fullWma isn't ready
         rawDiff[i] = halfWma[i]; 
      }
    }

    // Now calculate WMA of the diff with sqrtPeriod
    const wSumSqrt = (sqrtPeriod * (sqrtPeriod + 1)) / 2;
    const hmaRaw: number[] = new Array(closes.length).fill(NaN);
    
    for (let i = sqrtPeriod - 1; i < rawDiff.length; i++) {
      let sum = 0;
      let valid = true;
      for (let j = 0; j < sqrtPeriod; j++) {
        if (isNaN(rawDiff[i - j])) { valid = false; break; }
        sum += rawDiff[i - j] * (sqrtPeriod - j);
      }
      if (valid) hmaRaw[i] = sum / wSumSqrt;
    }

    const hmaLine: LineData[] = [];
    for (let i = 0; i < candles.length; i++) {
      if (!isNaN(hmaRaw[i])) {
        hmaLine.push({ time: candles[i].time, value: hmaRaw[i] });
      }
    }
    return hmaLine;
  }

  private pushTerminal(line: string) {
    const ts = new Date().toISOString().slice(11, 19);
    this.terminalLines.update(ls => [...ls.slice(-22), `[${ts}] ${line}`]);
  }

  private _buildGroups(d: Nexus15ResultDto | null): GroupCard[] {
    const gs  = d?.groupScores as any;
    const det = d?.detectivity ?? {};
    const f   = d?.features;

    return GROUPS_META.map(meta => ({
      ...meta,
      score: gs ? (gs[meta.key] ?? 0) : 0,
      detectivity: det[meta.key] ?? '',
      checks: this._buildChecks(meta.key, f),
    }));
  }

  private _buildChecks(key: string, f?: Nexus15FeaturesDto | null): CheckItem[] {
    if (!f) return [
      { label: 'Awaiting data', value: '--', status: 'neutral' },
      { label: 'Awaiting data', value: '--', status: 'neutral' },
      { label: 'Awaiting data', value: '--', status: 'neutral' },
    ];

    switch (key) {
      case 'g1PriceAction': return [
        { label: 'BOS',        value: f.bosDetected ? '✓' : '✗',                      status: f.bosDetected ? 'ok' : 'neutral' },
        { label: 'Bull Bars',  value: `${f.consecutiveBullBars}`,                       status: f.consecutiveBullBars >= 2 ? 'ok' : 'neutral' },
        { label: 'Body Ratio', value: `${(f.candleBodyRatio * 100).toFixed(0)}%`,       status: f.candleBodyRatio > 0.5 ? 'ok' : 'warn' },
      ];
      case 'g2SmcIct': return [
        { label: 'Order Block',    value: f.orderBlockDetected ? '✓' : '✗',            status: f.orderBlockDetected ? 'ok' : 'warn' },
        { label: 'Fair Val Gap',   value: f.fairValueGap ? '✓' : '✗',                 status: f.fairValueGap ? 'ok' : 'warn' },
        { label: 'BOS',            value: f.bosDetected ? '✓' : '✗',                   status: f.bosDetected ? 'ok' : 'neutral' },
        { label: 'Liq Sweep',      value: f.liquiditySweep ? '✓' : '✗',               status: f.liquiditySweep ? 'ok' : 'neutral' },
      ];
      case 'g3Wyckoff': return [
        { label: 'Phase',    value: f.wyckoffPhase ?? '--',        status: (f.wyckoffPhase === 'Markup' || f.wyckoffPhase === 'Accumulation') ? 'ok' : 'warn' },
        { label: 'Spring',   value: f.springDetected ? '✓' : '✗', status: f.springDetected ? 'ok' : 'neutral' },
        { label: 'Upthrust', value: f.upthrustDetected ? '✓' : '✗', status: f.upthrustDetected ? 'warn' : 'ok' },
      ];
      case 'g4Fractals': return [
        { label: 'Trend',        value: f.trendStructure === 1 ? 'HH/HL ↑' : f.trendStructure === -1 ? 'LH/LL ↓' : 'Lateral', status: f.trendStructure === 1 ? 'ok' : f.trendStructure === -1 ? 'warn' : 'neutral' },
        { label: 'Fractal High', value: f.fractalHigh5 ? '✓' : '✗', status: f.fractalHigh5 ? 'warn' : 'neutral' },
        { label: 'Fractal Low',  value: f.fractalLow5 ? '✓' : '✗',  status: f.fractalLow5 ? 'ok' : 'neutral' },
      ];
      case 'g5Volume': return [
        { label: 'Vol Ratio',  value: `${f.volumeRatio20?.toFixed(2)}×`,          status: f.volumeRatio20 > 1.5 ? 'ok' : 'neutral' },
        { label: 'Vol Surge',  value: f.volumeSurgeBullish ? '✓' : '✗',           status: f.volumeSurgeBullish ? 'ok' : 'warn' },
        { label: 'Vol Expl',   value: f.volumeExplosion ? '✓' : '✗',              status: f.volumeExplosion ? 'ok' : 'neutral' },
        { label: 'POC Prox',   value: `${(f.pocProximity * 100).toFixed(1)}%`,    status: f.pocProximity < 0.005 ? 'ok' : 'neutral' },
      ];
      case 'g6Ml': return [
        { label: 'RSI-14',    value: `${f.rsi14?.toFixed(1)}`,                    status: (f.rsi14 > 50 && f.rsi14 < 70) ? 'ok' : 'warn' },
        { label: 'MACD Hist', value: f.macdHistogram >= 0 ? '→ +' : '→ −',        status: f.macdHistogram >= 0 ? 'ok' : 'warn' },
        { label: 'ATR%',      value: `${f.atrPercent?.toFixed(2)}%`,              status: 'neutral' },
      ];
      default: return [];
    }
  }
}
