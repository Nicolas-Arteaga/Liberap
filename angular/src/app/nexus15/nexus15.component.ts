import {
  Component, OnInit, OnDestroy, AfterViewInit,
  inject, signal, computed, ElementRef, ViewChild
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { Nexus15Service } from '../proxy/trading/nexus15/nexus15.service';
import { Nexus15ResultDto, Nexus15FeaturesDto } from '../proxy/trading/nexus15/models';
import { TradingSignalrService } from '../services/trading-signalr.service';
import {
  createChart, IChartApi, ISeriesApi,
  CandlestickData, LineSeries, CandlestickSeries,
  ColorType, CrosshairMode, LineStyle,
} from 'lightweight-charts';

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
  status: 'ok' | 'warn' | 'neutral'; // ✅ ⚠ →
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
  private signalR    = inject(TradingSignalrService);

  // ── State ──────────────────────────────────────────────────────────────────
  selectedSymbol = signal('BTCUSDT');
  isLoading      = signal(false);
  data           = signal<Nexus15ResultDto | null>(null);
  errorMsg       = signal<string | null>(null);
  terminalLines  = signal<string[]>([]);
  scanCount      = signal(0);

  private sub?: Subscription;
  private terminalTimer?: any;
  private msgIdx = 0;

  readonly SYMBOLS = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT','AVAXUSDT','ADAUSDT'];

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
  private projSeries?: ISeriesApi<'Line'>;

  // ── Computed ───────────────────────────────────────────────────────────────
  confidenceColor = computed(() => {
    const c = this.data()?.aiConfidence ?? 0;
    return c >= 75 ? '#00ff88' : c >= 55 ? '#ffdd00' : '#ff4466';
  });

  directionClass = computed(() => {
    const d = this.data()?.direction;
    return d === 'BULLISH' ? 'bullish' : d === 'BEARISH' ? 'bearish' : 'neutral';
  });

  leftGroups  = computed(() => this._buildGroups(this.data()).slice(0, 3)); // G1 G2 G4
  rightGroups = computed(() => this._buildGroups(this.data()).slice(3, 6)); // G3 G5 G6

  // Groups at idx 0,1,3 on left | 2,4,5 on right to match mockup
  leftGroupsReorder  = computed(() => {
    const all = this._buildGroups(this.data());
    return [all[0], all[1], all[3]]; // G1, G2, G4
  });
  rightGroupsReorder = computed(() => {
    const all = this._buildGroups(this.data());
    return [all[2], all[4], all[5]]; // G3, G5, G6
  });

  directionArrow = computed(() => {
    const d = this.data()?.direction;
    return d === 'BULLISH' ? '▲' : d === 'BEARISH' ? '▼' : '⬡';
  });

  // ── Lifecycle ───────────────────────────────────────────────────────────────
  ngOnInit() {
    this.startTerminal();
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
  }

  // ── Public actions ─────────────────────────────────────────────────────────
  onSymbolChange(sym: string) {
    this.selectedSymbol.set(sym);
    this.loadLatest();
  }

  runOnDemand() {
    this.isLoading.set(true);
    this.errorMsg.set(null);
    this.pushTerminal(`> MANUAL SCAN: ${this.selectedSymbol()}`);
    this.nexus15Svc.analyzeOnDemand(this.selectedSymbol()).subscribe({
      next: r => {
        this.data.set(r);
        this.isLoading.set(false);
        this.scanCount.update(n => n + 1);
        this.pushTerminal(`✓ CONF:${(r.aiConfidence ?? 0).toFixed(1)}% DIR:${r.direction}`);
        this.renderProjection(r);
      },
      error: err => {
        this.isLoading.set(false);
        this.errorMsg.set('Python Service offline or no cached data.');
        this.pushTerminal(`✗ ERROR: ${err?.error?.error || 'check service'}`);
      }
    });
  }

  // ── Chart ──────────────────────────────────────────────────────────────────
  private initChart() {
    if (!this.chartContainerRef) return;
    const el = this.chartContainerRef.nativeElement;

    this.chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: '#030a10' },
        textColor: 'rgba(0,240,255,0.5)',
        fontFamily: "'Share Tech Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: 'rgba(0,240,255,0.04)' },
        horzLines: { color: 'rgba(0,240,255,0.04)' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: 'rgba(0,240,255,0.15)' },
      timeScale: {
        borderColor: 'rgba(0,240,255,0.15)',
        timeVisible: true,
        secondsVisible: false,
      },
      width: el.clientWidth,
      height: el.clientHeight || 280,
    });

    this.candleSeries = this.chart.addSeries(CandlestickSeries, {
      upColor: '#00ff88',
      downColor: '#ff4466',
      borderUpColor: '#00ff88',
      borderDownColor: '#ff4466',
      wickUpColor: '#00ff88',
      wickDownColor: '#ff4466',
    });

    this.projSeries = this.chart.addSeries(LineSeries, {
      color: '#00f0ff',
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // Load synthetic demo candles for visual while awaiting real data
    this.loadDemoCandles();
  }

  private loadDemoCandles() {
    const now = Math.floor(Date.now() / 1000);
    const interval = 15 * 60;
    const candles: CandlestickData[] = [];
    let price = 65000;
    for (let i = 30; i >= 0; i--) {
      const t = now - i * interval;
      const o = price;
      const change = (Math.random() - 0.48) * 400;
      const c = o + change;
      const h = Math.max(o, c) + Math.random() * 200;
      const l = Math.min(o, c) - Math.random() * 200;
      candles.push({ time: t as any, open: o, high: h, low: l, close: c });
      price = c;
    }
    this.candleSeries?.setData(candles);
    this.chart?.timeScale().fitContent();
  }

  private renderProjection(d: Nexus15ResultDto) {
    if (!this.candleSeries || !this.projSeries) return;
    const now = Math.floor(Date.now() / 1000);
    const interval = 15 * 60;
    const lastClose = 65000; // placeholder; replace with actual last close from real feed
    const bullish = (d.direction ?? '') === 'BULLISH';
    const range = (d.estimatedRangePercent ?? 1.5) / 100;

    const projPoints: any[] = [];
    for (let i = 0; i <= 20; i++) {
      const t = now + i * interval;
      const val = lastClose * (1 + (bullish ? 1 : -1) * range * (i / 20));
      projPoints.push({ time: t, value: val });
    }
    this.projSeries.setData(projPoints);
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

  private pushTerminal(line: string) {
    const ts = new Date().toISOString().slice(11, 19);
    this.terminalLines.update(ls => [...ls.slice(-22), `[${ts}] ${line}`]);
  }

  private _buildGroups(d: Nexus15ResultDto | null): GroupCard[] {
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

  private _buildChecks(key: string, f?: Nexus15FeaturesDto | null): CheckItem[] {
    if (!f) return [
      { label: 'Detectiins',   value: '--', status: 'neutral' },
      { label: 'Altered Sizes', value: '--', status: 'neutral' },
      { label: 'Detectiiny',   value: '--', status: 'neutral' },
    ];

    switch (key) {
      case 'g1PriceAction': return [
        { label: 'BOS',              value: f.bosDetected ? '✓' : '✗', status: f.bosDetected ? 'ok' : 'neutral' },
        { label: 'Bull Bars',        value: `${f.consecutiveBullBars}`, status: f.consecutiveBullBars >= 2 ? 'ok' : 'neutral' },
        { label: 'Body Ratio',       value: `${(f.candleBodyRatio * 100).toFixed(0)}%`, status: f.candleBodyRatio > 0.5 ? 'ok' : 'warn' },
      ];
      case 'g2SmcIct': return [
        { label: 'Order Block',  value: f.orderBlockDetected ? '✓' : '✗', status: f.orderBlockDetected ? 'ok' : 'warn' },
        { label: 'Fair Value Gap', value: f.fairValueGap ? '✓' : '✗', status: f.fairValueGap ? 'ok' : 'warn' },
        { label: 'BOS',          value: f.bosDetected ? '✓' : '✗', status: f.bosDetected ? 'ok' : 'neutral' },
      ];
      case 'g3Wyckoff': return [
        { label: 'Phase',        value: f.wyckoffPhase ?? '--', status: (f.wyckoffPhase === 'Markup' || f.wyckoffPhase === 'Accumulation') ? 'ok' : 'warn' },
        { label: 'Spring',       value: f.springDetected ? '✓' : '✗', status: f.springDetected ? 'ok' : 'neutral' },
        { label: 'Upthrust',     value: f.upthrustDetected ? '✓' : '✗', status: f.upthrustDetected ? 'warn' : 'ok' },
      ];
      case 'g4Fractals': return [
        { label: 'Trend',        value: f.trendStructure === 1 ? 'HH/HL ↑' : f.trendStructure === -1 ? 'LH/LL ↓' : 'Lateral', status: f.trendStructure === 1 ? 'ok' : f.trendStructure === -1 ? 'warn' : 'neutral' },
        { label: 'Fractal High', value: f.fractalHigh5 ? '✓' : '✗', status: f.fractalHigh5 ? 'warn' : 'neutral' },
        { label: 'Fractal Low',  value: f.fractalLow5 ? '✓' : '✗', status: f.fractalLow5 ? 'ok' : 'neutral' },
      ];
      case 'g5Volume': return [
        { label: 'Vol Ratio',    value: `${f.volumeRatio20?.toFixed(2)}×`, status: f.volumeRatio20 > 1.5 ? 'ok' : 'neutral' },
        { label: 'Vol Surge',    value: f.volumeSurgeBullish ? '✓' : '✗', status: f.volumeSurgeBullish ? 'ok' : 'warn' },
        { label: 'POC Prox',     value: `${(f.pocProximity * 100).toFixed(1)}%`, status: f.pocProximity < 0.005 ? 'ok' : 'neutral' },
      ];
      case 'g6Ml': return [
        { label: 'RSI-14',       value: `${f.rsi14?.toFixed(1)}`, status: (f.rsi14 > 50 && f.rsi14 < 70) ? 'ok' : 'warn' },
        { label: 'MACD Hist',    value: f.macdHistogram >= 0 ? '→ +' : '→ −', status: f.macdHistogram >= 0 ? 'ok' : 'warn' },
        { label: 'ATR%',         value: `${f.atrPercent?.toFixed(2)}%`, status: 'neutral' },
      ];
      default: return [];
    }
  }
}
