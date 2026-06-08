import {
  Component, OnInit, OnDestroy, AfterViewInit,
  inject, signal, computed, ElementRef, ViewChild
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { Nexus5Service } from '../proxy/trading/nexus5/nexus5.service';
import { Nexus5ResultDto, Nexus5FeaturesDto } from '../proxy/trading/nexus5/models';
import { BotService } from '../proxy/trading/bot.service';
import { TradingSignalrService } from '../services/trading-signalr.service';
import { ActivatedRoute } from '@angular/router';
import { BINANCE_FUTURES_PAIRS } from '../shared/models/models-shared';
import {
  createChart, IChartApi, ISeriesApi,
  CandlestickData, CandlestickSeries,
  HistogramSeries, LineSeries, LineData,
  ColorType, CrosshairMode, IPriceLine, LineStyle
} from 'lightweight-charts';

// ── Group meta for NEXUS-5 (6 groups) ───────────────────────────────────
const GROUPS_META = [
  { key: 'g1PriceAction', num: 1,  label: 'Price Action — Ruptura Sniper',    color: '#ff4400', weight: 20 },
  { key: 'g2SmcIct',      num: 2,  label: 'SMC/ICT — Desplazamiento',         color: '#ff00aa', weight: 15 },
  { key: 'g3Wyckoff',     num: 3,  label: 'Wyckoff — Fases de Resorte',       color: '#00ff88', weight: 15 },
  { key: 'g4Fractals',    num: 4,  label: 'Fractales — Micro-Tendencia',      color: '#aa00ff', weight: 10 },
  { key: 'g5Volume',      num: 5,  label: 'Volume — Corazón del Movimiento',  color: '#ff8800', weight: 25 },
  { key: 'g6Ml',          num: 6,  label: 'ML — Anomalías y Momentum',        color: '#ffdd00', weight: 15 },
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
  selector: 'app-nexus5',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './nexus5.component.html',
  styleUrls: ['./nexus5.component.scss'],
})
export class Nexus5Component implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('chartContainer') chartContainerRef!: ElementRef<HTMLDivElement>;

  private nexus5Svc = inject(Nexus5Service);
  private botSvc    = inject(BotService);
  private signalR   = inject(TradingSignalrService);
  private route     = inject(ActivatedRoute);

  // ── State ──────────────────────────────────────────────────────────────────
  selectedSymbol = signal('BTCUSDT');
  isLoading      = signal(false);
  data           = signal<Nexus5ResultDto | null>(null);
  errorMsg       = signal<string | null>(null);
  terminalLines  = signal<string[]>([]);
  livePrice      = signal<number | null>(null);
  livePriceChange = signal<number>(0);
  scanCount      = signal(0);
  topResults     = signal<Nexus5ResultDto[]>([]);
  isTopLoading   = signal(false);

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
  selectedTimeframe = signal('5m');

  onTimeframeChange(tf: string) {
    if (this.selectedTimeframe() === tf) return;
    this.selectedTimeframe.set(tf);
    this.wipeAllState();
    this.loadBinanceCandles(this.selectedSymbol());
  }

  // ── Terminal ───────────────────────────────────────────────────────────────
  private sub?: Subscription;
  private terminalTimer?: any;
  private msgIdx = 0;

  private readonly TERMINAL_MSGS = [
    'NEXUS-5 IGNITION CORE ONLINE...', 'CONNECTING TO REDIS PIPELINE...',
    'LOADING XGB MODEL V1...', 'FEATURE ENGINE READY [18 FEATURES]',
    'PHASE DETECTOR INITIALIZED', 'SMC/ICT DISPLACEMENT MODULE LOADED',
    'COMPRESSION ZONE SCANNER ACTIVE', 'WYCKOFF SOS/JUMPING CREEK ENGINE',
    'FRACTAL MICRO-TREND MAP [OK]', 'ANOMALY DETECTOR CALIBRATED',
    'AWAITING 5M CANDLE CLOSE...', 'SIGNAL ROUTER CONNECTED',
    'BINANCE FEED ACTIVE', 'SEMAPHORE(5,5) SECURED',
    'RSI BYPASS MODULE STANDBY', 'EFFICIENCY CHECK ACTIVE',
    'NEXUS-5 IGNITION PREDICTIVE CORE READY ✓',
  ];

  // ── Chart series ─────────────────────────────────────────────────────────
  private chart!: IChartApi;
  private candleSeries!: ISeriesApi<'Candlestick'>;
  private volumeSeries!: ISeriesApi<'Histogram'>;
  private hmaSeries!: ISeriesApi<'Line'>;
  private ma7Series!: ISeriesApi<'Line'>;
  private ma25Series!: ISeriesApi<'Line'>;
  private ma99Series!: ISeriesApi<'Line'>;
  private midLineSeries!: ISeriesApi<'Line'>;
  private upperBandSeries!: ISeriesApi<'Line'>;
  private lowerBandSeries!: ISeriesApi<'Line'>;
  private chartResizeObserver?: ResizeObserver;
  private entryLine?: IPriceLine;
  private targetLine?: IPriceLine;

  currentHmaValue = signal<number | null>(null);
  currentMa7Value = signal<number | null>(null);
  currentMa25Value = signal<number | null>(null);
  currentMa99Value = signal<number | null>(null);

  lastHmaValue: number | null = null;
  lastMa7Value: number | null = null;
  lastMa25Value: number | null = null;
  lastMa99Value: number | null = null;

  realCandles: CandlestickData[] = [];

  // ── Computed ───────────────────────────────────────────────────────────────
  confidenceColor = computed(() => {
    const c = this.data()?.aiConfidence ?? 0;
    return c >= 75 ? '#00ff88' : c >= 55 ? '#ffdd00' : '#ff4466';
  });

  directionClass = computed(() => {
    const d = this.data()?.direction;
    return d === 'BULLISH' ? 'bullish' : d === 'BEARISH' ? 'bearish' : 'neutral';
  });

  phaseClass = computed(() => {
    const p = this.data()?.phase;
    return p === 'IGNITION' ? 'phase-ignition' :
           p === 'COMPRESSION' ? 'phase-compression' :
           p === 'EXPANSION' ? 'phase-expansion' : 'phase-idle';
  });

  phaseLabel = computed(() => {
    const p = this.data()?.phase;
    if (p === 'IGNITION') return '⚡ IGNITION';
    if (p === 'COMPRESSION') return '🔒 COMPRESSION';
    if (p === 'EXPANSION') return '🚀 EXPANSION';
    return '⏸ IDLE';
  });

  leftGroups = computed(() => this._buildGroups(this.data()).slice(0, 4));
  rightGroups = computed(() => this._buildGroups(this.data()).slice(4, 6));

  directionArrow = computed(() => {
    const d = this.data()?.direction;
    return d === 'BULLISH' ? '▲' : d === 'BEARISH' ? '▼' : '⬡';
  });

  // ── Lifecycle ───────────────────────────────────────────────────────────────
  ngOnInit() {
    this.startTerminal();
    this.loadActivePairs();

    this.route.queryParams.subscribe(params => {
      const sym = params['symbol'];
      if (sym) {
        this.selectedSymbol.set(sym.toUpperCase());
        this.loadBinanceCandles(sym.toUpperCase());
      }
      this.loadLatest();
    });

    this.sub = this.signalR.nexus5$.subscribe(p => {
      if (!p) return;
      if ((p.symbol ?? '').toUpperCase() === this.selectedSymbol().toUpperCase()) {
        this.data.set(p);
        this.scanCount.update(n => n + 1);
        this.pushTerminal(`↳ ${p.symbol} | ${p.phase}(${(p.phaseScore ?? 0).toFixed(0)}) | CONF:${(p.aiConfidence ?? 0).toFixed(1)}% | ${p.direction}`);
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
    if (this.chartResizeObserver) this.chartResizeObserver.disconnect();
  }

  // ── Public actions ─────────────────────────────────────────────────────────
  onSymbolChange(sym: string, existingData?: Nexus5ResultDto) {
    const binanceSym = this.toBinanceSymbol(sym);
    if (binanceSym === this.selectedSymbol()) return;

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

  private wipeAllState() {
    this.errorMsg.set(null);
    this.livePrice.set(null);
    this.realCandles = [];
    this.candleSeries?.setData([]);
    this.volumeSeries?.setData([]);
    this.hmaSeries?.setData([]);
    this.ma7Series?.setData([]);
    this.ma25Series?.setData([]);
    this.ma99Series?.setData([]);
    this.midLineSeries?.setData([]);
    this.upperBandSeries?.setData([]);
    this.lowerBandSeries?.setData([]);
    this.currentHmaValue.set(null);
    this.currentMa7Value.set(null);
    this.currentMa25Value.set(null);
    this.currentMa99Value.set(null);
    this.lastHmaValue = null;
    this.lastMa7Value = null;
    this.lastMa25Value = null;
    this.lastMa99Value = null;
    if (this.entryLine && this.candleSeries) {
      this.candleSeries.removePriceLine(this.entryLine);
      this.entryLine = undefined;
    }
    if (this.targetLine && this.candleSeries) {
      this.candleSeries.removePriceLine(this.targetLine);
      this.targetLine = undefined;
    }
  }

  onSymbolSearch(q: string) { this.symbolSearch.set(q); }

  onSearchEnter() {
    const q = this.symbolSearch().toUpperCase().trim();
    if (!q) return;
    const filtered = this.filteredSymbols();
    if (this.availableSymbols().includes(q)) { this.onSymbolChange(q); return; }
    if (filtered.length === 1) { this.onSymbolChange(filtered[0]); return; }
    if (q.endsWith('USDT') || q.length >= 5) this.onSymbolChange(q);
  }

  runOnDemand() {
    const q = this.symbolSearch().toUpperCase().trim();
    if (q && (q.endsWith('USDT') || q.length >= 5 || this.availableSymbols().includes(q))) {
      this.onSymbolChange(q);
      setTimeout(() => this.executeOnDemand(), 50);
      return;
    }
    this.executeOnDemand();
  }

  private executeOnDemand() {
    this.isLoading.set(true);
    this.errorMsg.set(null);
    this.pushTerminal(`> MANUAL IGNITION SCAN: ${this.selectedSymbol()}`);
    this.nexus5Svc.analyzeOnDemand(this.selectedSymbol()).subscribe({
      next: r => {
        this.isLoading.set(false);
        if (!r) {
          this.errorMsg.set(`AI model sin datos para ${this.selectedSymbol()} — chart activo igual.`);
          this.pushTerminal(`⚠ NEXUS-5: sin modelo para ${this.selectedSymbol()}`);
          return;
        }
        this.data.set(r);
        this.scanCount.update(n => n + 1);
        this.pushTerminal(`✓ Phase:${r.phase}(${(r.phaseScore ?? 0).toFixed(0)}) Conf:${(r.aiConfidence ?? 0).toFixed(1)}% Dir:${r.direction} Entry:${r.entryTimeframe}`);
        this.renderProjection(r);
      },
      error: err => {
        this.isLoading.set(false);
        const msg = err?.error?.error || err?.message || 'check service';
        this.errorMsg.set(`NEXUS-5: sin datos para ${this.selectedSymbol()} (${msg})`);
        this.pushTerminal(`⚠ NEXUS-5 error: ${msg}`);
      }
    });
  }

  runTopScan() {
    this.isTopLoading.set(true);
    this.topResults.set([]);
    this.pushTerminal('> IGNITION SCAN: TOP 5 PHASE 1/2 PAIRS...');
    this.nexus5Svc.analyzeTopAvailable(5).subscribe({
      next: res => {
        const arr = (res as any)?.items || res || [];
        // Sort: highest confidence first
        arr.sort((a: any, b: any) => (b.aiConfidence ?? 0) - (a.aiConfidence ?? 0));
        this.topResults.set(arr);
        this.isTopLoading.set(false);
        this.pushTerminal(`✓ SCAN COMPLETE: ${arr.length} IGNITION/COMPRESSION PAIRS FOUND`);
      },
      error: err => {
        this.isTopLoading.set(false);
        const msg = err?.error?.error?.message || err?.message || 'unknown';
        this.pushTerminal(`⚠ TOP SCAN ERROR: ${msg}`);
      }
    });
  }

  // ── Pairs loading ──────────────────────────────────────────────────────────
  private loadActivePairs() {
    this.botSvc.getActivePairs().subscribe({
      next: pairs => {
        if (pairs && pairs.length > 0) {
          const activePairSymbols = pairs.map(p => (p as any).symbol ?? (p as any).pair ?? '').filter(Boolean).map((s: string) => s.toUpperCase());
          const merged = [...new Set([...activePairSymbols, ...BINANCE_FUTURES_PAIRS])];
          this.availableSymbols.set(merged);
          this.pushTerminal(`✓ PAIRS LOADED: ${activePairSymbols.length} ACTIVE + BINANCE FUTURES`);
        }
      },
      error: () => { this.availableSymbols.set(BINANCE_FUTURES_PAIRS); }
    });
  }

  // ── Chart initialization ──────────────────────────────────────────────────
  private initChart() {
    if (!this.chartContainerRef) return;
    const el = this.chartContainerRef.nativeElement;

    this.chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: 'rgba(255,68,0,0.7)',
        fontFamily: "'Share Tech Mono', monospace",
        fontSize: 13,
      },
      grid: {
        vertLines: { color: 'rgba(255,68,0,0.03)' },
        horzLines: { color: 'rgba(255,68,0,0.03)' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: 'rgba(255,68,0,0.15)',
        scaleMargins: { top: 0.08, bottom: 0.28 }
      },
      timeScale: {
        borderColor: 'rgba(255,68,0,0.15)',
        timeVisible: true,
      },
      width: el.clientWidth,
      height: el.clientHeight || 400,
    });

    this.chartResizeObserver = new ResizeObserver(entries => {
      if (entries.length === 0 || entries[0].target !== el) return;
      const newRect = entries[0].contentRect;
      if (newRect.width > 0 && newRect.height > 0) {
        this.chart.applyOptions({ width: newRect.width, height: newRect.height });
      }
    });
    this.chartResizeObserver.observe(el);

    this.candleSeries = this.chart.addSeries(CandlestickSeries, {
      upColor: '#00ff88', downColor: '#ff4466',
      borderUpColor: '#00ff88', borderDownColor: '#ff4466',
      wickUpColor: '#00ff88', wickDownColor: '#ff4466',
    });

    this.volumeSeries = this.chart.addSeries(HistogramSeries, {
      color: '#ff8800', priceFormat: { type: 'volume' }, priceScaleId: 'volume',
    });
    this.chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    this.hmaSeries = this.chart.addSeries(LineSeries, {
      color: '#00e5ff', lineWidth: 2,
      crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
      autoscaleInfoProvider: () => null,
    });

    this.ma7Series = this.chart.addSeries(LineSeries, {
      color: '#ffcc00', lineWidth: 1, lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
      autoscaleInfoProvider: () => null,
    });

    this.ma25Series = this.chart.addSeries(LineSeries, {
      color: '#ba55d3', lineWidth: 1,
      crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
      autoscaleInfoProvider: () => null,
    });

    this.ma99Series = this.chart.addSeries(LineSeries, {
      color: '#722ed1', lineWidth: 1,
      crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
      autoscaleInfoProvider: () => null,
    });

    this.upperBandSeries = this.chart.addSeries(LineSeries, {
      color: 'rgba(255,136,0,0.15)', lineWidth: 1, lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
      autoscaleInfoProvider: () => null,
    });

    this.lowerBandSeries = this.chart.addSeries(LineSeries, {
      color: 'rgba(255,136,0,0.15)', lineWidth: 1, lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
      autoscaleInfoProvider: () => null,
    });

    this.midLineSeries = this.chart.addSeries(LineSeries, {
      color: '#ff8800', lineWidth: 2, lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: true, lastValueVisible: true, priceLineVisible: false,
      autoscaleInfoProvider: () => null,
    });

    // Crosshair move tracker for overlay HUD
    this.chart.subscribeCrosshairMove((param) => {
      if (param && param.time) {
        const hmaData = param.seriesData.get(this.hmaSeries!) as any;
        const ma7Data = param.seriesData.get(this.ma7Series!) as any;
        const ma25Data = param.seriesData.get(this.ma25Series!) as any;
        const ma99Data = param.seriesData.get(this.ma99Series!) as any;

        this.currentHmaValue.set(hmaData ? hmaData.value : null);
        this.currentMa7Value.set(ma7Data ? ma7Data.value : null);
        this.currentMa25Value.set(ma25Data ? ma25Data.value : null);
        this.currentMa99Value.set(ma99Data ? ma99Data.value : null);
      } else {
        this.currentHmaValue.set(this.lastHmaValue);
        this.currentMa7Value.set(this.lastMa7Value);
        this.currentMa25Value.set(this.lastMa25Value);
        this.currentMa99Value.set(this.lastMa99Value);
      }
    });

    this.loadBinanceCandles(this.selectedSymbol());
  }

  private toBinanceSymbol(sym: string): string {
    const withoutSettle = sym.includes(':') ? sym.split(':')[0] : sym;
    return withoutSettle.replace(/[/\-]/g, '').toUpperCase().trim();
  }

  private loadBinanceCandles(symbol: string, interval = this.selectedTimeframe(), limit = 1000) {
    const binanceSym = this.toBinanceSymbol(symbol);
    this.pushTerminal(`> BINANCE KLINES: ${binanceSym} [${interval}] x${limit}...`);

    const parseKlines = (raw: any[]) => {
      const candles: CandlestickData[] = [];
      const volumes: any[] = [];
      for (const k of raw) {
        const t = Math.floor(k[0] / 1000) as any;
        const o = parseFloat(k[1]), h = parseFloat(k[2]);
        const l = parseFloat(k[3]), c = parseFloat(k[4]);
        const vol = parseFloat(k[5]);
        candles.push({ time: t, open: o, high: h, low: l, close: c });
        volumes.push({ time: t, value: vol,
          color: c >= o ? 'rgba(0,255,136,0.45)' : 'rgba(255,68,102,0.45)' });
      }
      return { candles, volumes };
    };

    const apply = (candles: CandlestickData[], volumes: any[]) => {
      if (this.selectedSymbol() !== binanceSym) return;
      this.realCandles = candles;

      let prec = 2, minMove = 0.01;
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
      this.ma7Series?.applyOptions({ priceFormat: format });
      this.ma25Series?.applyOptions({ priceFormat: format });
      this.ma99Series?.applyOptions({ priceFormat: format });
      this.midLineSeries?.applyOptions({ priceFormat: format });
      this.upperBandSeries?.applyOptions({ priceFormat: format });
      this.lowerBandSeries?.applyOptions({ priceFormat: format });

      this.candleSeries?.setData(candles);
      this.volumeSeries?.setData(volumes);
      
      this.updateHMA(candles);
      this.updateMA(candles, 7, this.ma7Series);
      this.updateMA(candles, 25, this.ma25Series);
      this.updateMA(candles, 99, this.ma99Series);
      this.chart?.timeScale().fitContent();

      const currentData = this.data();
      if (currentData && this.toBinanceSymbol(currentData.symbol ?? '') === binanceSym) {
        this.renderProjection(currentData);
      }

      if (candles.length >= 2) {
        const last = candles[candles.length - 1];
        const prev = candles[candles.length - 2];
        this.livePrice.set(last.close);
        const pct = ((last.close - prev.close) / prev.close) * 100;
        this.livePriceChange.set(Math.round(pct * 100) / 100);
      }
      this.pushTerminal(`✓ ${candles.length} CANDLES [${binanceSym}] @ ${this.livePrice()?.toFixed(4) ?? '?'}`);
    };

    // Futures first, then Spot, then Bybit
    const futuresUrl = `https://fapi.binance.com/fapi/v1/klines?symbol=${binanceSym}&interval=${interval}&limit=${limit}`;
    fetch(futuresUrl)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((raw: any[]) => {
        if (!Array.isArray(raw) || raw.length === 0) throw new Error('no data');
        const { candles, volumes } = parseKlines(raw);
        apply(candles, volumes);
      })
      .catch(() => {
        const spotUrl = `https://api.binance.com/api/v3/klines?symbol=${binanceSym}&interval=${interval}&limit=${limit}`;
        this.pushTerminal(`  → Futures n/d, probando SPOT...`);
        fetch(spotUrl)
          .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
          .then((raw: any[]) => {
            if (!Array.isArray(raw) || raw.length === 0) throw new Error('no data');
            const { candles, volumes } = parseKlines(raw);
            apply(candles, volumes);
          })
          .catch(() => {
            this.pushTerminal(`  → Bybit fallback...`);
            const bybitIntervals: any = { '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30', '1h': '60', '2h': '120', '4h': '240', '1d': 'D', '1w': 'W', '1M': 'M' };
            const bbInterval = bybitIntervals[interval] || '5';
            const bybitUrl = `https://api.bybit.com/v5/market/kline?category=linear&symbol=${binanceSym}&interval=${bbInterval}&limit=${limit}`;
            fetch(bybitUrl)
              .then(r => { if (!r.ok) throw new Error(`Bybit HTTP ${r.status}`); return r.json(); })
              .then(bbData => {
                if (bbData.retCode !== 0 || !bbData.result?.list?.length) throw new Error('Bybit no data');
                const rawList = bbData.result.list.reverse();
                const candles2: CandlestickData[] = [];
                const volumes2: any[] = [];
                for (const k of rawList) {
                  const t = Math.floor(parseInt(k[0], 10) / 1000) as any;
                  const o = parseFloat(k[1]), h = parseFloat(k[2]);
                  const l = parseFloat(k[3]), c = parseFloat(k[4]);
                  const vol = parseFloat(k[5]);
                  candles2.push({ time: t, open: o, high: h, low: l, close: c });
                  volumes2.push({ time: t, value: vol, color: c >= o ? 'rgba(0,255,136,0.45)' : 'rgba(255,68,102,0.45)' });
                }
                apply(candles2, volumes2);
              })
              .catch(() => {
                this.errorMsg.set(`${binanceSym} no disponible en exchanges públicos.`);
                this.loadFallbackDemo();
              });
          });
      });
  }

  private loadFallbackDemo(basePrice = 1.0) {
    const now = Math.floor(Date.now() / 1000);
    const interval = 5 * 60;
    const candles: CandlestickData[] = [];
    const volumes: any[] = [];
    let price = basePrice;
    for (let i = 200; i >= 0; i--) {
      const t = (now - i * interval - (now % interval)) as any;
      const o = price;
      const pct = (Math.random() - 0.48) * 0.018;
      const c = o * (1 + pct);
      const h = Math.max(o, c) * (1 + Math.random() * 0.005);
      const l = Math.min(o, c) * (1 - Math.random() * 0.005);
      candles.push({ time: t, open: o, high: h, low: l, close: c });
      volumes.push({ time: t, value: Math.random() * 500000 + 100000,
        color: c > o ? 'rgba(0,255,136,0.4)' : 'rgba(255,68,102,0.4)' });
      price = c;
    }
    this.realCandles = candles;
    this.candleSeries?.setData(candles);
    this.volumeSeries?.setData(volumes);
    this.updateHMA(candles);
    this.updateMA(candles, 7, this.ma7Series);
    this.updateMA(candles, 25, this.ma25Series);
    this.updateMA(candles, 99, this.ma99Series);
    this.chart?.timeScale().fitContent();
  }

  updateHMA(candles: CandlestickData[]) {
    if (candles.length >= 50) {
      const hmaData = this.calculateHMA(candles, 50);
      this.hmaSeries?.setData(hmaData);
      this.lastHmaValue = hmaData.length > 0 ? hmaData[hmaData.length - 1].value : null;
    } else {
      this.hmaSeries?.setData([]);
      this.lastHmaValue = null;
    }
    if (this.currentHmaValue() === null) {
      this.currentHmaValue.set(this.lastHmaValue);
    }
  }

  updateMA(candles: CandlestickData[], period: number, series: ISeriesApi<'Line'> | null) {
    if (!series || candles.length < period) {
      if (series) series.setData([]);
      if (period === 7) { this.lastMa7Value = null; this.currentMa7Value.set(null); }
      else if (period === 25) { this.lastMa25Value = null; this.currentMa25Value.set(null); }
      else if (period === 99) { this.lastMa99Value = null; this.currentMa99Value.set(null); }
      return;
    }

    const maData = this.calculateSMA(candles, period);
    series.setData(maData);

    const lastVal = maData.length > 0 ? maData[maData.length - 1].value : null;
    if (period === 7) {
      this.lastMa7Value = lastVal;
      if (this.currentMa7Value() === null) this.currentMa7Value.set(lastVal);
    } else if (period === 25) {
      this.lastMa25Value = lastVal;
      if (this.currentMa25Value() === null) this.currentMa25Value.set(lastVal);
    } else if (period === 99) {
      this.lastMa99Value = lastVal;
      if (this.currentMa99Value() === null) this.currentMa99Value.set(lastVal);
    }
  }

  private calculateSMA(candles: CandlestickData[], period: number): LineData[] {
    if (candles.length < period) return [];
    const smaLines: LineData[] = [];
    let sum = 0;
    for (let i = 0; i < period; i++) sum += candles[i].close;
    smaLines.push({ time: candles[period - 1].time, value: sum / period });

    for (let i = period; i < candles.length; i++) {
      sum = sum - candles[i - period].close + candles[i].close;
      smaLines.push({ time: candles[i].time, value: sum / period });
    }
    return smaLines;
  }

  private renderProjection(d: Nexus5ResultDto) {
    if (!this.candleSeries || !this.midLineSeries || !this.upperBandSeries || !this.lowerBandSeries) return;
    const targetSym = this.toBinanceSymbol(d.symbol ?? '');
    if (targetSym !== this.selectedSymbol()) return;
    if (this.realCandles.length === 0) { setTimeout(() => this.renderProjection(d), 200); return; }

    const interval = 5 * 60; // 5 min in seconds
    const bullish = (d.direction ?? '') === 'BULLISH';
    const neutral = (d.direction ?? '') === 'NEUTRAL';
    const prob5 = d.next5CandlesProb ?? 0.5;
    const rangePct = (d.estimatedRangePercent ?? 1.8) / 100;
    const dirMul = bullish ? 1 : neutral ? 0 : -1;
    const candleCount = 10; // fewer candles projected for 5m

    const lastCandle = this.realCandles[this.realCandles.length - 1];
    const anchorTime = lastCandle.time as number;
    const anchorPrice = lastCandle.close;

    const midColor  = neutral ? '#ff8800' : bullish ? '#00ff88' : '#ff4466';
    const bandColor = neutral ? 'rgba(255,136,0,0.12)' : bullish ? 'rgba(0,255,136,0.12)' : 'rgba(255,68,102,0.12)';

    this.midLineSeries.applyOptions({ color: midColor, lineWidth: 2, lineStyle: LineStyle.Dashed });
    this.upperBandSeries.applyOptions({ color: bandColor, lineWidth: 1, lineStyle: LineStyle.Dotted });
    this.lowerBandSeries.applyOptions({ color: bandColor, lineWidth: 1, lineStyle: LineStyle.Dotted });

    const midData: LineData[] = [{ time: anchorTime as any, value: anchorPrice }];
    const upperData: LineData[] = [{ time: anchorTime as any, value: anchorPrice }];
    const lowerData: LineData[] = [{ time: anchorTime as any, value: anchorPrice }];

    for (let i = 1; i <= candleCount; i++) {
      const t = (anchorTime + i * interval) as any;
      const progress = i / candleCount;
      const mid = anchorPrice * (1 + dirMul * rangePct * progress);
      const spread = anchorPrice * rangePct * 1.5 * progress * (1 + (1 - prob5) * 0.6);
      midData.push({ time: t, value: mid });
      upperData.push({ time: t, value: mid + spread });
      lowerData.push({ time: t, value: mid - spread });
    }

    this.midLineSeries.setData(midData);
    this.upperBandSeries.setData(upperData);
    this.lowerBandSeries.setData(lowerData);

    if (this.entryLine) { this.candleSeries.removePriceLine(this.entryLine); this.entryLine = undefined; }
    if (this.targetLine) { this.candleSeries.removePriceLine(this.targetLine); this.targetLine = undefined; }

    if (!neutral) {
      const finalTarget = anchorPrice * (1 + dirMul * rangePct);
      const tColor = bullish ? '#00ff88' : '#ff4466';
      this.entryLine = this.candleSeries.createPriceLine({
        price: anchorPrice, color: 'rgba(255,136,0,0.5)', lineWidth: 1,
        lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'ENTRY',
      });
      this.targetLine = this.candleSeries.createPriceLine({
        price: finalTarget, color: tColor, lineWidth: 2,
        lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: 'TARGET',
      });
    }

    const histVols = this.realCandles.map(c => ({
      time: c.time, value: Math.random() * 900 + 200,
      color: c.close > c.open ? 'rgba(0,255,136,0.45)' : 'rgba(255,68,102,0.45)',
    }));
    const futureVols = midData.slice(1).map(pt => ({
      time: pt.time, value: 200 + Math.random() * 300,
      color: bullish ? 'rgba(255,136,0,0.35)' : 'rgba(255,0,170,0.35)',
    }));
    this.volumeSeries?.setData([...histVols, ...futureVols]);
    this.chart?.timeScale().fitContent();
  }

  // ── Private helpers ────────────────────────────────────────────────────────
  private loadLatest() {
    this.isLoading.set(true);
    this.nexus5Svc.getLatest(this.selectedSymbol()).subscribe({
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

  private calculateHMA(candles: CandlestickData[], period: number): LineData[] {
    const closes = candles.map(c => c.close);
    const wma = (data: number[], p: number) => {
      const res: number[] = new Array(data.length).fill(NaN);
      const wSum = (p * (p + 1)) / 2;
      for (let i = p - 1; i < data.length; i++) {
        let sum = 0;
        for (let j = 0; j < p; j++) sum += data[i - j] * (p - j);
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
      if (!isNaN(halfWma[i]) && !isNaN(fullWma[i])) rawDiff[i] = (2 * halfWma[i]) - fullWma[i];
      else if (!isNaN(halfWma[i])) rawDiff[i] = halfWma[i];
    }
    const wSumSqrt = (sqrtPeriod * (sqrtPeriod + 1)) / 2;
    const hmaRaw: number[] = new Array(closes.length).fill(NaN);
    for (let i = sqrtPeriod - 1; i < rawDiff.length; i++) {
      let sum = 0, valid = true;
      for (let j = 0; j < sqrtPeriod; j++) {
        if (isNaN(rawDiff[i - j])) { valid = false; break; }
        sum += rawDiff[i - j] * (sqrtPeriod - j);
      }
      if (valid) hmaRaw[i] = sum / wSumSqrt;
    }
    const hmaLine: LineData[] = [];
    for (let i = 0; i < candles.length; i++) {
      if (!isNaN(hmaRaw[i])) hmaLine.push({ time: candles[i].time, value: hmaRaw[i] });
    }
    return hmaLine;
  }

  private pushTerminal(line: string) {
    const ts = new Date().toISOString().slice(11, 19);
    this.terminalLines.update(ls => [...ls.slice(-22), `[${ts}] ${line}`]);
  }

  private _buildGroups(d: Nexus5ResultDto | null): GroupCard[] {
    const gs = d?.groupScores as any;
    const det = d?.detectivity ?? {};
    const f = d?.features;
    return GROUPS_META.map(meta => ({
      ...meta,
      score: gs ? (gs[meta.key] ?? 0) : 0,
      detectivity: det[meta.key] ?? '',
      checks: this._buildChecks(meta.key, f),
    }));
  }

  private _buildChecks(key: string, f?: Nexus5FeaturesDto | null): CheckItem[] {
    if (!f) return [
      { label: 'Awaiting data', value: '--', status: 'neutral' },
      { label: 'Awaiting data', value: '--', status: 'neutral' },
      { label: 'Awaiting data', value: '--', status: 'neutral' },
    ];

    switch (key) {
      case 'g1PriceAction': return [
        { label: 'Compression', value: `${(f.compressionRange * 100).toFixed(1)}%`, status: f.compressionRange < 0.04 ? 'ok' : 'neutral' },
        { label: 'Ignition',    value: f.ignitionCandle ? '✓' : '✗',               status: f.ignitionCandle ? 'ok' : 'neutral' },
        { label: 'Efficiency',  value: `${(f.efficiencyCheck * 100).toFixed(0)}%`,   status: f.efficiencyCheck > 0.5 ? 'ok' : 'neutral' },
      ];
      case 'g2SmcIct': return [
        { label: 'Displacement FVG', value: f.displacementFvg ? '✓' : '✗',    status: f.displacementFvg ? 'ok' : 'neutral' },
        { label: 'Micro CHoCH',      value: f.microChoch ? '✓' : '✗',         status: f.microChoch ? 'ok' : 'neutral' },
        { label: 'Order Block',      value: f.instantOrderBlock ? '✓' : '✗',  status: f.instantOrderBlock ? 'ok' : 'neutral' },
      ];
      case 'g3Wyckoff': return [
        { label: 'Compression Zone', value: f.compressionZone ? '✓' : '✗',  status: f.compressionZone ? 'ok' : 'neutral' },
        { label: 'SOS Detected',     value: f.sosDetected ? '✓' : '✗',      status: f.sosDetected ? 'ok' : 'neutral' },
        { label: 'Jumping Creek',    value: f.jumpingCreek ? '✓' : '✗',     status: f.jumpingCreek ? 'ok' : 'neutral' },
      ];
      case 'g4Fractals': return [
        { label: 'Fractal Break', value: f.fractalHighBreak ? '✓' : '✗',           status: f.fractalHighBreak ? 'ok' : 'neutral' },
        { label: 'EMA7 Angle',   value: `${(f.ema7Angle * 100).toFixed(1)}`,       status: Math.abs(f.ema7Angle) > 0.3 ? 'ok' : 'neutral' },
        { label: 'HH/HL Seq',    value: f.hhHlSequence ? '✓' : '✗',               status: f.hhHlSequence ? 'ok' : 'neutral' },
      ];
      case 'g5Volume': return [
        { label: 'Vol Multiplier', value: `${f.relativeVolMultiplier?.toFixed(2)}×`,     status: f.relativeVolMultiplier > 2 ? 'ok' : 'neutral' },
        { label: 'Vol Intensity',  value: `${f.volIntensity?.toFixed(2)}`,               status: f.volIntensity > 1 ? 'ok' : 'neutral' },
        { label: 'Buy Imbalance',  value: `${(f.buyingImbalance * 100).toFixed(0)}%`,     status: f.buyingImbalance > 0.6 ? 'ok' : f.buyingImbalance < 0.4 ? 'warn' : 'neutral' },
      ];
      case 'g6Ml': return [
        { label: 'ATR Expansion', value: `${f.atrExpansion?.toFixed(2)}×`,   status: f.atrExpansion > 1.5 ? 'ok' : 'neutral' },
        { label: 'Z-Score',       value: `${f.zScore?.toFixed(2)}`,          status: Math.abs(f.zScore) > 1.5 ? 'ok' : 'neutral' },
        { label: 'RSI Velocity',  value: `${(f.rsiVelocity * 100).toFixed(0)}`, status: Math.abs(f.rsiVelocity) > 0.3 ? 'ok' : 'neutral' },
      ];
      default: return [];
    }
  }
}
