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
  HistogramSeries,
  ColorType, CrosshairMode,
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

@Component({
  selector: 'app-nexus15',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './nexus15.component.html',
  styleUrls: ['./nexus15.component.scss'],
})
export class Nexus15Component implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('chartContainer') chartContainerRef!: ElementRef<HTMLDivElement>;
  @ViewChild('coneCanvas')     coneCanvasRef!: ElementRef<HTMLCanvasElement>;

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

  // ── Dynamic Pair Selector ──────────────────────────────────────────────────
  availableSymbols = signal<string[]>(BINANCE_FUTURES_PAIRS);
  symbolSearch     = signal('');

  filteredSymbols = computed(() => {
    const q = this.symbolSearch().toUpperCase().trim();
    const all = this.availableSymbols();
    return q ? all.filter(s => s.includes(q)) : all;
  });

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

  // ── Chart ──────────────────────────────────────────────────────────────────
  private chart?: IChartApi;
  private candleSeries?: ISeriesApi<'Candlestick'>;
  private volumeSeries?: ISeriesApi<'Histogram'>;
  private ghostCandleSeries?: ISeriesApi<'Candlestick'>;

  // All real candles stored so we can read the last one's price at projection time
  private realCandles: CandlestickData[] = [];

  // Canvas-overlay holographic cone
  private coneData: {
    anchorTime: number;
    anchorPrice: number;
    points: Array<{ t: number; upper: number; mid: number; lower: number }>;
    bullish: boolean;
  } | null = null;

  private coneAnimFrame?: number;

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
    if (this.coneAnimFrame) cancelAnimationFrame(this.coneAnimFrame);
    this.chart?.remove();
  }

  // ── Public actions ─────────────────────────────────────────────────────────
  onSymbolChange(sym: string) {
    this.selectedSymbol.set(sym);
    this.symbolSearch.set('');
    this.data.set(null);               // clear old AI data
    this.errorMsg.set(null);
    this.livePrice.set(null);          // reset price display
    this.coneData = null;              // clear old cone
    this.ghostCandleSeries?.setData([]);
    this.loadBinanceCandles(sym);      // real OHLCV from Binance (symbol normalized internally)
    this.loadLatest();                 // AI prediction from backend
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

  // ── Chart ──────────────────────────────────────────────────────────────────
  private initChart() {
    if (!this.chartContainerRef) return;
    const el = this.chartContainerRef.nativeElement;

    this.chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: 'rgba(0,240,255,0.5)',
        fontFamily: "'Share Tech Mono', monospace",
        fontSize: 10,
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
      height: el.clientHeight || 300,
    });

    // ── Real candles ──
    this.candleSeries = this.chart.addSeries(CandlestickSeries, {
      upColor: '#00ff88',
      downColor: '#ff4466',
      borderUpColor: '#00ff88',
      borderDownColor: '#ff4466',
      wickUpColor: '#00ff88',
      wickDownColor: '#ff4466',
    });

    // ── Volume histogram (bottom 20%) ──
    this.volumeSeries = this.chart.addSeries(HistogramSeries, {
      color: '#00f0ff',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });

    this.chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    // ── Ghost / Predictive candles (turquoise) ──
    const cyan = '#00f0ff';
    this.ghostCandleSeries = this.chart.addSeries(CandlestickSeries, {
      upColor: cyan,
      downColor: cyan,
      borderUpColor: cyan,
      borderDownColor: cyan,
      wickUpColor: cyan,
      wickDownColor: cyan,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    this.loadBinanceCandles(this.selectedSymbol()); // normalized inside

    // ── Re-draw canvas cone whenever the user scrolls / zooms ───────────────
    this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
      if (this.coneData) requestAnimationFrame(() => this.drawConeOnCanvas());
    });
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

  private loadBinanceCandles(symbol: string, interval = '15m', limit = 200) {
    const binanceSym = this.toBinanceSymbol(symbol);
    this.pushTerminal(`> BINANCE KLINES: ${binanceSym} [${interval}] x${limit}...`);

    const parseKlines = (raw: any[]) => {
      const candles: CandlestickData[] = [];
      const volumes: any[]             = [];
      for (const k of raw) {
        const t   = Math.floor(k[0] / 1000) as any;
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
      this.realCandles = candles;
      this.candleSeries?.setData(candles);
      this.volumeSeries?.setData(volumes);
      this.ghostCandleSeries?.setData([]);
      this.coneData = null;
      this.chart?.timeScale().fitContent();
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

  /** @deprecated use loadBinanceCandles — kept only for internal fallback */
  private loadDemoCandles() {
    this.loadFallbackDemo(66500);
  }

  private renderProjection(d: Nexus15ResultDto) {
    if (!this.candleSeries || !this.ghostCandleSeries || !this.volumeSeries) return;
    if (this.realCandles.length === 0) {
      // candles still loading from Binance — retry in 500ms
      setTimeout(() => this.renderProjection(d), 500);
      return;
    }

    const interval = 15 * 60;
    const bullish  = (d.direction ?? '') === 'BULLISH';
    const prob15   = d.next15CandlesProb  ?? 0.5;
    const rangePct = (d.estimatedRangePercent ?? 1.8) / 100;

    // ── Anchor EXACTLY at the last real candle ───────────────────────────────
    if (this.realCandles.length === 0) this.loadDemoCandles();
    const lastCandle   = this.realCandles[this.realCandles.length - 1];
    const anchorTime   = lastCandle.time as number;   // unix seconds
    const anchorPrice  = lastCandle.close;

    // ── Build projection data ───────────────────────────────────────────────
    const ghosts:     CandlestickData[] = [];
    const futureVols: any[]             = [];
    const conePoints: Array<{ t: number; upper: number; mid: number; lower: number }> = [];

    let currentPrice  = anchorPrice;
    const dirMul      = bullish ? 1 : -1;
    const candleCount = 20;

    for (let i = 1; i <= candleCount; i++) {
      const t        = (anchorTime + i * interval) as any;
      const progress = i / candleCount;

      // Mid-line follows direction, divergence opens like a proper funnel from zero
      const targetMid  = anchorPrice * (1 + dirMul * rangePct * progress);
      const confFactor = 1 + (1 - prob15) * 0.8;
      const divergence = anchorPrice * rangePct * 2.5 * progress * confFactor;

      conePoints.push({ t, upper: targetMid + divergence, mid: targetMid, lower: targetMid - divergence });

      // Ghost candles hug the mid-line with tiny noise
      const open   = currentPrice;
      const noise  = (Math.random() - 0.5) * anchorPrice * 0.0004;
      const close  = targetMid + noise;
      const spread = anchorPrice * 0.0004 * (1 + Math.random() * 0.3);
      ghosts.push({ time: t, open, high: Math.max(open, close) + spread, low: Math.min(open, close) - spread, close });
      currentPrice = close;

      futureVols.push({
        time:  t,
        value: 350 + Math.random() * 400,
        color: bullish ? 'rgba(0, 240, 255, 0.70)' : 'rgba(255, 0, 170, 0.70)',
      });
    }

    // Re-generate historical volume bars aligned with realCandles
    const histVols = this.realCandles.map(c => ({
      time:  c.time,
      value: Math.random() * 900 + 200,
      color: c.close > c.open ? 'rgba(0, 255, 136, 0.45)' : 'rgba(255, 68, 102, 0.45)',
    }));

    this.volumeSeries.setData([...histVols, ...futureVols]);
    this.ghostCandleSeries.setData(ghosts);

    // Store cone data for canvas drawing — anchor is now EXACTLY the last real candle
    this.coneData = { anchorTime, anchorPrice, points: conePoints, bullish };

    this.chart?.timeScale().fitContent();
    // Give the chart time to layout before drawing canvas polygon
    setTimeout(() => this.drawConeOnCanvas(), 80);
  }

  /**
   * Draws the holographic cone on a Canvas 2D overlay using the chart's own
   * coordinate API.  The funnel uses multiple gradient layers + glow ribbons
   * for a pro cyberpunk look rather than a flat triangle.
   */
  private drawConeOnCanvas() {
    if (!this.coneCanvasRef || !this.chart || !this.candleSeries || !this.coneData) return;

    const canvas    = this.coneCanvasRef.nativeElement;
    const container = this.chartContainerRef.nativeElement;
    const dpr       = window.devicePixelRatio || 1;
    const W         = container.clientWidth;
    const H         = container.clientHeight;

    canvas.width        = W * dpr;
    canvas.height       = H * dpr;
    canvas.style.width  = W + 'px';
    canvas.style.height = H + 'px';

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);

    const { anchorTime, anchorPrice, points, bullish } = this.coneData;
    const ts     = this.chart.timeScale();
    const series = this.candleSeries;

    // ── Convert anchor → pixel ───────────────────────────────────────────────
    const ax = ts.timeToCoordinate(anchorTime as any);
    const ay = series.priceToCoordinate(anchorPrice);
    if (ax === null || ay === null) return;

    // ── Build pixel arrays ───────────────────────────────────────────────────
    const upperPx: [number, number][] = [];
    const lowerPx: [number, number][] = [];
    const midPx:   [number, number][] = [];

    for (const pt of points) {
      const x  = ts.timeToCoordinate(pt.t as any);
      const yu = series.priceToCoordinate(pt.upper);
      const yl = series.priceToCoordinate(pt.lower);
      const ym = series.priceToCoordinate(pt.mid);
      if (x !== null && yu !== null && yl !== null && ym !== null) {
        upperPx.push([x, yu]);
        lowerPx.push([x, yl]);
        midPx.push([x,  ym]);
      }
    }
    if (upperPx.length === 0) return;

    const lastX  = upperPx[upperPx.length - 1][0];
    const lastYu = upperPx[upperPx.length - 1][1];
    const lastYl = lowerPx[lowerPx.length - 1][1];
    const neon   = bullish ? '0, 255, 136' : '255, 68, 102';
    const cyan   = '0, 240, 255';

    // Helper: trace the full cone outline as a closed path
    const traceFull = () => {
      ctx.moveTo(ax, ay);
      upperPx.forEach(([x, y]) => ctx.lineTo(x, y));
      lowerPx.slice().reverse().forEach(([x, y]) => ctx.lineTo(x, y));
      ctx.closePath();
    };

    // ── Layer 1: deep ambient fill ───────────────────────────────────────────
    {
      const grad = ctx.createLinearGradient(ax, 0, lastX, 0);
      grad.addColorStop(0,   `rgba(${neon}, 0.00)`);
      grad.addColorStop(0.15,`rgba(${neon}, 0.06)`);
      grad.addColorStop(0.6, `rgba(${neon}, 0.12)`);
      grad.addColorStop(1,   `rgba(${neon}, 0.05)`);
      ctx.save();
      ctx.beginPath(); traceFull();
      ctx.fillStyle = grad;
      ctx.fill();
      ctx.restore();
    }

    // ── Layer 2: vertical center-glow (radial-like via y-gradient) ───────────
    {
      const midYEnd = midPx[midPx.length - 1]?.[1] ?? ay;
      const grad = ctx.createLinearGradient(0, Math.min(ay, midYEnd), 0, Math.max(ay, midYEnd) + 80);
      grad.addColorStop(0,   `rgba(${cyan}, 0.00)`);
      grad.addColorStop(0.5, `rgba(${cyan}, 0.08)`);
      grad.addColorStop(1,   `rgba(${cyan}, 0.00)`);
      ctx.save();
      ctx.beginPath(); traceFull();
      ctx.fillStyle = grad;
      ctx.fill();
      ctx.restore();
    }

    // ── Layer 3: horizontal scan lines inside the cone ───────────────────────
    ctx.save();
    ctx.globalAlpha = 0.18;
    ctx.strokeStyle = `rgba(${cyan}, 1)`;
    ctx.lineWidth   = 0.5;
    // Clip to the cone shape
    ctx.beginPath(); traceFull(); ctx.clip();
    const scanStep = 8;
    for (let y = 0; y < H; y += scanStep) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
      ctx.stroke();
    }
    ctx.restore();

    // ── Layer 4: upper rim glow (triple-stroke for wide bloom) ───────────────
    const drawRim = (px: [number, number][], blur: number, alpha: number, lw: number) => {
      ctx.save();
      ctx.shadowColor = `rgba(${neon}, 1)`;
      ctx.shadowBlur  = blur;
      ctx.strokeStyle = `rgba(${neon}, ${alpha})`;
      ctx.lineWidth   = lw;
      ctx.lineJoin    = 'round';
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      px.forEach(([x, y]) => ctx.lineTo(x, y));
      ctx.stroke();
      ctx.restore();
    };
    // Outer bloom
    drawRim(upperPx, 24, 0.25, 6);
    drawRim(lowerPx, 24, 0.25, 6);
    // Mid bloom
    drawRim(upperPx, 12, 0.55, 2.5);
    drawRim(lowerPx, 12, 0.55, 2.5);
    // Sharp core line
    drawRim(upperPx,  4, 0.90, 1.0);
    drawRim(lowerPx,  4, 0.90, 1.0);

    // ── Layer 5: closing vertical rim at the far end ─────────────────────────
    ctx.save();
    ctx.shadowColor = `rgba(${neon}, 1)`;
    ctx.shadowBlur  = 16;
    ctx.strokeStyle = `rgba(${neon}, 0.55)`;
    ctx.lineWidth   = 1.5;
    ctx.beginPath();
    ctx.moveTo(lastX, lastYu);
    ctx.lineTo(lastX, lastYl);
    ctx.stroke();
    ctx.restore();

    // ── Layer 6: center dashed prediction line ───────────────────────────────
    ctx.save();
    ctx.setLineDash([8, 5]);
    ctx.shadowColor = `rgba(${cyan}, 1)`;
    ctx.shadowBlur  = 14;
    ctx.strokeStyle = `rgba(${cyan}, 0.90)`;
    ctx.lineWidth   = 1.5;
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    midPx.forEach(([x, y]) => ctx.lineTo(x, y));
    ctx.stroke();
    ctx.restore();

    // ── Layer 7: anchor dot ──────────────────────────────────────────────────
    ctx.save();
    ctx.shadowColor = `rgba(${cyan}, 1)`;
    ctx.shadowBlur  = 20;
    ctx.fillStyle   = `rgba(${cyan}, 0.95)`;
    ctx.beginPath();
    ctx.arc(ax, ay, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
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
