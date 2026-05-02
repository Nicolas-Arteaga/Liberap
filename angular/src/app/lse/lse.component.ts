import {
  Component, OnInit, OnDestroy, AfterViewInit,
  inject, signal, computed, ElementRef, ViewChild
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  createChart, IChartApi, ISeriesApi,
  CandlestickData, CandlestickSeries,
  HistogramSeries, LineSeries, LineData,
  ColorType, CrosshairMode, IPriceLine, LineStyle
} from 'lightweight-charts';
import { BINANCE_FUTURES_PAIRS } from '../shared/models/models-shared';
import { environment } from '../../environments/environment';

// ── Interfaces ──────────────────────────────────────────────────────────────

export interface LseSubScores {
  compression: number;
  sweep: number;
  reclaim: number;
  volume: number;
  htf_context: number;
}

export interface LseSignal {
  symbol: string;
  timeframe: string;
  state: string;
  /** conservative | aggressive — modo de detección del backend */
  detection_mode?: string;
  score: number;
  sub_scores: LseSubScores;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit_1: number | null;
  take_profit_2: number | null;
  sweep_low: number | null;
  reclaim_close: number | null;
  ma7: number | null;
  ma25: number | null;
  ma99: number | null;
  atr: number | null;
  volume_ratio: number | null;
  compression_pct: number | null;
  reasoning: string[];
  entry_mode: string;
  detected_at: string | null;
  alert_message: string | null;
}

export interface LseHistoryEntry {
  symbol: string;
  time: string;
  score: number;
  result: 'Activa' | 'TP1' | 'TP2' | 'SL';
}

export interface LsePatternStep {
  id: number;
  key: string;
  label: string;
  sublabel: string;
  state: 'confirmed' | 'active' | 'pending' | 'waiting';
  time?: string;
}

const LSE_PYTHON_URL = (environment as { pythonAiUrl?: string }).pythonAiUrl ?? 'http://localhost:8005';

@Component({
  selector: 'app-lse',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './lse.component.html',
  styleUrls: ['./lse.component.scss'],
})
export class LseComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('chartContainer') chartContainerRef!: ElementRef<HTMLDivElement>;

  // ── State signals ─────────────────────────────────────────────────────────
  selectedSymbol  = signal('ARBUSDT');
  /** Binance interval: debe coincidir con `<option value>` del select (15m | 1h | 4h). */
  selectedTf      = signal('1h');
  selectedMode    = signal<'Agresivo' | 'Conservador'>('Agresivo');
  scoreThreshold  = signal(65);
  isLoading       = signal(false);
  isScanning      = signal(false);
  lseSignal       = signal<LseSignal | null>(null);
  errorMsg        = signal<string | null>(null);
  livePrice       = signal<number | null>(null);
  livePriceChange = signal<number>(0);
  symbolSearch    = signal('');
  showSymbolList  = signal(false);
  scanInterval?: any;
  private chartResizeObserver?: ResizeObserver;

  // ── Top Scan ──────────────────────────────────────────────────────────────
  isTopLoading = signal(false);
  topResults   = signal<LseSignal[]>([]);

  // ── Pattern State Machine ─────────────────────────────────────────────────
  patternSteps = signal<LsePatternStep[]>([
    { id: 1, key: 'compression', label: 'COMPRESIÓN', sublabel: 'Detectada', state: 'pending', time: '--:--' },
    { id: 2, key: 'sweep',       label: 'SWEEP',       sublabel: 'Detectado', state: 'pending', time: '--:--' },
    { id: 3, key: 'reclaim',     label: 'RECLAIM',     sublabel: 'Confirmado', state: 'pending', time: '--:--' },
    { id: 4, key: 'intention',   label: 'INTENCIÓN',   sublabel: 'Pendiente',  state: 'pending', time: '...' },
    { id: 5, key: 'triggered',   label: 'TRIGGERED',   sublabel: 'Esperando confirmación', state: 'waiting', time: '...' },
  ]);

  cooldownMsg = signal('Listo para nueva señal en: --');

  // ── History (static + real) ───────────────────────────────────────────────
  signalHistory = signal<LseHistoryEntry[]>([
    { symbol: 'ARBUSDT',  time: '13/05 17:00', score: 78, result: 'Activa' },
    { symbol: 'OPUSDT',   time: '13/05 11:00', score: 72, result: 'TP1'    },
    { symbol: 'TIAUSDT',  time: '13/05 06:00', score: 69, result: 'TP2'    },
    { symbol: 'SUIUSDT',  time: '12/05 22:00', score: 61, result: 'SL'     },
    { symbol: 'BONKUSDT', time: '12/05 15:00', score: 67, result: 'TP1'    },
  ]);

  // ── Additional filters ────────────────────────────────────────────────────
  filters = signal({
    htf:     { label: 'Contexto HTF (4H)', value: 'Alcista',       ok: true  },
    minor:   { label: 'Estructura 15m',    value: 'Neutral/Alcista', ok: true  },
    atr:     { label: 'ATR Ratio',         value: '1.32',          ok: true  },
    anomaly: { label: 'Velas Anómalas',    value: 'OK',            ok: true  },
  });

  // ── Computed ──────────────────────────────────────────────────────────────
  filteredSymbols = computed(() => {
    const q = this.symbolSearch().toUpperCase().trim();
    return q ? BINANCE_FUTURES_PAIRS.filter(s => s.includes(q)) : BINANCE_FUTURES_PAIRS;
  });

  /** Selector UI: mismo modo para detección + entrada (conservative/conservative vs aggressive/aggressive). */
  scanModeLabel = computed(() =>
    this.selectedMode() === 'Agresivo'
      ? 'Detección aggressive · entrada aggressive'
      : 'Detección conservative · entrada conservative',
  );

  activeModeBadge = computed(() => {
    const dm = this.lseSignal()?.detection_mode;
    if (dm) return dm === 'aggressive' ? 'AGGRESSIVE' : 'CONSERVATIVE';
    return this.selectedMode() === 'Agresivo' ? 'AGGRESSIVE*' : 'CONSERVATIVE*';
  });

  scoreColor = computed(() => {
    const s = this.lseSignal()?.score ?? 0;
    return s >= 75 ? '#00ff88' : s >= 65 ? '#ffdd00' : '#ff4466';
  });

  scoreLabel = computed(() => {
    const s = this.lseSignal()?.score ?? 0;
    return s >= 75 ? 'Fuerte' : s >= 65 ? 'Válido' : 'Débil';
  });

  riskReward = computed(() => {
    const sig = this.lseSignal();
    if (!sig?.entry_price || !sig?.stop_loss || !sig?.take_profit_1) return null;
    const risk   = sig.entry_price - sig.stop_loss;
    const reward = sig.take_profit_1 - sig.entry_price;
    return risk > 0 ? +(reward / risk).toFixed(2) : null;
  });

  riskRewardTp2 = computed(() => {
    const sig = this.lseSignal();
    if (!sig?.entry_price || !sig?.stop_loss || !sig?.take_profit_2) return null;
    const risk   = sig.entry_price - sig.stop_loss;
    const reward = sig.take_profit_2 - sig.entry_price;
    return risk > 0 ? +(reward / risk).toFixed(2) : null;
  });

  riskPct = computed(() => {
    const sig = this.lseSignal();
    if (!sig?.entry_price || !sig?.stop_loss) return null;
    return +((sig.stop_loss - sig.entry_price) / sig.entry_price * 100).toFixed(2);
  });

  tp1Pct = computed(() => {
    const sig = this.lseSignal();
    if (!sig?.entry_price || !sig?.take_profit_1) return null;
    return +((sig.take_profit_1 - sig.entry_price) / sig.entry_price * 100).toFixed(2);
  });

  tp2Pct = computed(() => {
    const sig = this.lseSignal();
    if (!sig?.entry_price || !sig?.take_profit_2) return null;
    return +((sig.take_profit_2 - sig.entry_price) / sig.entry_price * 100).toFixed(2);
  });

  patternDescription = computed(() => {
    const sig = this.lseSignal();
    if (!sig) return 'Sin datos — seleccioná un símbolo y ejecutá el scan LSE.';
    return `Spring detectado después de fase de distribución. Compresión de medias MA25 y MA99, barrido de liquidez bajo mínimo relevante con rechazo fuerte, reclaim del nivel roto con volumen de clímax. Contexto HTF favorable para continuación alcista.`;
  });

  // ── Chart ─────────────────────────────────────────────────────────────────
  private chart!: IChartApi;
  private candleSeries!: ISeriesApi<'Candlestick'>;
  private volumeSeries!: ISeriesApi<'Histogram'>;
  private ma7Series!: ISeriesApi<'Line'>;
  private ma25Series!: ISeriesApi<'Line'>;
  private ma99Series!: ISeriesApi<'Line'>;
  private sweepLine?: IPriceLine;
  private reclaimLine?: IPriceLine;
  private entryLine?: IPriceLine;
  private tp1Line?: IPriceLine;
  private tp2Line?: IPriceLine;
  private slLine?: IPriceLine;
  private realCandles: CandlestickData[] = [];
  /** Etiqueta corta para UI (badge junto al símbolo). */
  tfBadge = computed(() => {
    const v = this.selectedTf().toLowerCase();
    if (v === '15m') return '15M';
    if (v === '4h') return '4H';
    return '1H';
  });

  /** Intervalo Binance API para velas principales + campo `timeframe` del backend. */
  private binanceInterval(): string {
    const v = this.selectedTf().toLowerCase();
    return v === '15m' || v === '4h' ? v : '1h';
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────
  ngOnInit() {
    this.loadCandles(this.selectedSymbol());
    // Auto-scan every 60s
    this.scanInterval = setInterval(() => this.runScan(false), 60_000);
  }

  ngAfterViewInit() {
    this.initChart();
  }

  ngOnDestroy() {
    if (this.scanInterval) clearInterval(this.scanInterval);
    this.chart?.remove();
    this.chartResizeObserver?.disconnect();
  }

  // ── Public Actions ─────────────────────────────────────────────────────────
  selectSymbol(sym: string) {
    this.selectedSymbol.set(sym.toUpperCase());
    this.symbolSearch.set('');
    this.showSymbolList.set(false);
    this.lseSignal.set(null);
    this.errorMsg.set(null);
    this.resetPatternSteps();
    this.clearChartOverlays();
    this.loadCandles(sym.toUpperCase());
  }

  selectTf(tf: string) {
    this.selectedTf.set(tf.toLowerCase());
    this.loadCandles(this.selectedSymbol());
  }

  /** Click en banner Top LSE: mantiene la señal en panel derecho y sincroniza TF si viene en la respuesta. */
  selectTopResult(tr: LseSignal) {
    const tfRaw = (tr.timeframe || this.binanceInterval()).toLowerCase();
    const tfNorm = tfRaw === '15m' || tfRaw === '4h' ? tfRaw : '1h';
    this.selectedTf.set(tfNorm);
    this.selectedSymbol.set(tr.symbol.toUpperCase());
    this.symbolSearch.set('');
    this.showSymbolList.set(false);
    this.errorMsg.set(null);
    this.lseSignal.set(tr);
    this.updatePatternStepsFromSignal(tr);
    this.drawChartOverlays(tr);
    this.loadCandles(tr.symbol.toUpperCase());
  }

  toggleMode() {
    this.selectedMode.set(this.selectedMode() === 'Agresivo' ? 'Conservador' : 'Agresivo');
  }

  runScan(showLoader = true) {
    if (this.isScanning()) return;
    if (showLoader) this.isLoading.set(true);
    this.isScanning.set(true);
    this.errorMsg.set(null);

    this.buildCandlePayload().then(payload => {
      if (!payload) {
        this.isLoading.set(false);
        this.isScanning.set(false);
        this.errorMsg.set('Sin datos de velas para analizar. Asegurate que el símbolo existe en Binance.');
        return;
      }

      const useAggressive = this.selectedMode() === 'Agresivo';
      const entry_mode = useAggressive ? 'aggressive' : 'conservative';
      const detection_mode = useAggressive ? 'aggressive' : 'conservative';
      const tf = this.binanceInterval();
      const body = {
        symbol:     this.selectedSymbol(),
        timeframe:  tf,
        candles_1h: payload.candles1h,
        candles_4h: payload.candles4h,
        entry_mode,
        detection_mode,
        preview_only: true,
      };

      fetch(`${LSE_PYTHON_URL}/lse/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
        .then(r => r.json())
        .then(data => {
          this.isLoading.set(false);
          this.isScanning.set(false);
          if (data.signal_found && data.signal) {
            this.lseSignal.set(data.signal as LseSignal);
            this.updatePatternStepsFromSignal(data.signal as LseSignal);
            this.drawChartOverlays(data.signal as LseSignal);
            this.addToHistory(data.signal as LseSignal);
          } else {
            const diag = Array.isArray(data.diagnostics) && data.diagnostics.length
              ? data.diagnostics.join(' ')
              : '';
            this.errorMsg.set(
              diag ||
                'No se detectó señal LSE en este momento. El sistema sigue monitoreando.'
            );
            this.resetPatternSteps();
          }
        })
        .catch(err => {
          this.isLoading.set(false);
          this.isScanning.set(false);
          this.errorMsg.set('Error de conexión con LSE: ' + (err.message || 'unknown'));
          console.error('[LSE] Scan error:', err);
        });
    });
  }

  runTopScan() {
    this.isTopLoading.set(true);
    this.topResults.set([]);
    this.errorMsg.set(null);
    
    // Fetch top 150 pairs by absolute price change from Binance
    fetch('https://fapi.binance.com/fapi/v1/ticker/24hr')
      .then(r => r.json())
      .then(async (tickers: any[]) => {
         const topPairs = tickers
           .filter(t => t.symbol.endsWith('USDT'))
           .sort((a, b) => Math.abs(b.priceChangePercent) - Math.abs(a.priceChangePercent))
           .slice(0, 150)
           .map(t => t.symbol);
           
         const results: LseSignal[] = [];
         
         // Chunk by 15 to avoid browser connection limits
         for (let i = 0; i < topPairs.length; i += 15) {
            const chunk = topPairs.slice(i, i + 15);
            await Promise.all(chunk.map(async sym => {
               try {
                 const iv = this.binanceInterval();
                 const [rPrimary, r4h] = await Promise.all([
                   fetch(`https://fapi.binance.com/fapi/v1/klines?symbol=${sym}&interval=${iv}&limit=500`).then(r => r.json()),
                   fetch(`https://fapi.binance.com/fapi/v1/klines?symbol=${sym}&interval=4h&limit=200`).then(r => r.json()),
                 ]);
                 const convert = (raw: any[]) => (Array.isArray(raw) ? raw : []).map(k => ({
                   timestamp: String(k[0]), open: +k[1], high: +k[2], low: +k[3], close: +k[4], volume: +k[5],
                 }));
                 const candlesPrimary = convert(rPrimary);
                 // Binance a veces devuelve `{ code, msg }` o pocos datos en listados nuevos — menos de 120 no alcanza para MA99
                 if (candlesPrimary.length < 120) {
                   return;
                 }

                 const useAggressive = this.selectedMode() === 'Agresivo';
                 const body = {
                   symbol: sym,
                   timeframe: iv,
                   candles_1h: candlesPrimary,
                   candles_4h: convert(r4h),
                   entry_mode: useAggressive ? 'aggressive' : 'conservative',
                   detection_mode: useAggressive ? 'aggressive' : 'conservative',
                   preview_only: true,
                 };

                 const resScan = await fetch(`${LSE_PYTHON_URL}/lse/scan`, {
                   method: 'POST',
                   headers: { 'Content-Type': 'application/json' },
                   body: JSON.stringify(body),
                 });
                 let scanRes: Record<string, unknown> = {};
                 try {
                   scanRes = await resScan.json() as Record<string, unknown>;
                 } catch {
                   return;
                 }
                 if (!resScan.ok) {
                   return;
                 }

                 const minScore = this.scoreThreshold();
                 if (scanRes.signal_found && scanRes.signal && (scanRes.signal as LseSignal).score >= minScore) {
                    results.push(scanRes.signal as LseSignal);
                 }
               } catch(e) {
                 // ignore
               }
            }));
         }
         
         const sorted = results.sort((a, b) => b.score - a.score);
         const seen = new Set<string>();
         const top10: LseSignal[] = [];
         for (const s of sorted) {
           if (seen.has(s.symbol)) continue;
           seen.add(s.symbol);
           top10.push(s);
           if (top10.length >= 10) break;
         }
         this.topResults.set(top10);
         this.isTopLoading.set(false);
         if (top10.length === 0) {
            this.errorMsg.set(
              'Ningún par del Top 150 superó el umbral LSE (compresión MA + sweep + reclaim + volumen + 4H). ' +
              'Probá bajar el umbral de score, modo Agresivo, otro timeframe, o escanear un símbolo concreto — el motor es selectivo a propósito.'
            );
         }
      })
      .catch(e => {
         this.isTopLoading.set(false);
         this.errorMsg.set('Error fetching top tickers.');
      });
  }

  // ── Chart init ────────────────────────────────────────────────────────────
  private initChart() {
    if (!this.chartContainerRef) return;
    const el = this.chartContainerRef.nativeElement;

    this.chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: 'rgba(180, 200, 220, 0.85)',
        fontFamily: "'Inter', 'Share Tech Mono', monospace",
        fontSize: 12,
      },
      grid: {
        vertLines: { color: 'rgba(255,255,255,0.03)' },
        horzLines: { color: 'rgba(255,255,255,0.03)' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: 'rgba(255,255,255,0.1)',
        scaleMargins: { top: 0.08, bottom: 0.25 },
      },
      timeScale: {
        borderColor: 'rgba(255,255,255,0.1)',
        timeVisible: true,
      },
      width: el.clientWidth,
      height: el.clientHeight || 320,
    });

    this.chartResizeObserver = new ResizeObserver(entries => {
      if (!entries.length) return;
      const r = entries[0].contentRect;
      if (r.width > 0 && r.height > 0) this.chart.applyOptions({ width: r.width, height: r.height });
    });
    this.chartResizeObserver.observe(el);

    this.candleSeries = this.chart.addSeries(CandlestickSeries, {
      upColor:        '#00ff88',
      downColor:      '#ff4466',
      borderUpColor:  '#00ff88',
      borderDownColor:'#ff4466',
      wickUpColor:    '#00ff88',
      wickDownColor:  '#ff4466',
    });

    this.volumeSeries = this.chart.addSeries(HistogramSeries, {
      color: '#00f0ff',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    this.chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    this.ma7Series = this.chart.addSeries(LineSeries, {
      color: '#ffd700',
      lineWidth: 1,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });
    this.ma25Series = this.chart.addSeries(LineSeries, {
      color: '#cc88ff',
      lineWidth: 1,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });
    this.ma99Series = this.chart.addSeries(LineSeries, {
      color: '#00aaff',
      lineWidth: 2,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    this.loadCandles(this.selectedSymbol(), this.binanceInterval());
  }

  private loadCandles(symbol: string, interval?: string, limit = 500) {
    const iv = interval ?? this.binanceInterval();
    const futuresUrl = `https://fapi.binance.com/fapi/v1/klines?symbol=${symbol}&interval=${iv}&limit=${limit}`;
    fetch(futuresUrl)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then((raw: any[]) => this.applyCandles(symbol, raw))
      .catch(() => {
        const spotUrl = `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=${iv}&limit=${limit}`;
        return fetch(spotUrl).then(r => r.json()).then((raw: any[]) => this.applyCandles(symbol, raw));
      })
      .catch(e => console.error('[LSE] Candle fetch error:', e));
  }

  private applyCandles(symbol: string, raw: any[]) {
    if (!Array.isArray(raw) || raw.length === 0 || symbol !== this.selectedSymbol()) return;
    const candles: CandlestickData[] = [];
    const volumes: any[] = [];
    const ma7Raw: number[] = [], ma25Raw: number[] = [], ma99Raw: number[] = [];
    let closes: number[] = [];

    for (const k of raw) {
      const t = Math.floor(k[0] / 1000) as any;
      const o = +k[1], h = +k[2], l = +k[3], c = +k[4], v = +k[5];
      candles.push({ time: t, open: o, high: h, low: l, close: c });
      volumes.push({ time: t, value: v, color: c >= o ? 'rgba(0,255,136,0.4)' : 'rgba(255,68,102,0.4)' });
      closes.push(c);
    }

    this.realCandles = candles;

    // Precision
    let prec = 4, minMove = 0.0001;
    const lastP = closes[closes.length - 1] || 1;
    if (lastP < 0.001)      { prec = 7; minMove = 0.0000001; }
    else if (lastP < 0.01)  { prec = 6; minMove = 0.000001; }
    else if (lastP < 0.1)   { prec = 5; minMove = 0.00001; }
    else if (lastP < 1)     { prec = 4; minMove = 0.0001; }
    else if (lastP < 10)    { prec = 3; minMove = 0.001; }
    else                    { prec = 2; minMove = 0.01; }
    const fmt = { type: 'price' as const, precision: prec, minMove };

    this.candleSeries?.applyOptions({ priceFormat: fmt });
    this.ma7Series?.applyOptions({ priceFormat: fmt });
    this.ma25Series?.applyOptions({ priceFormat: fmt });
    this.ma99Series?.applyOptions({ priceFormat: fmt });

    this.candleSeries?.setData(candles);
    this.volumeSeries?.setData(volumes);

    // MAs via EMA
    const ema7  = this.calcEma(closes, 7);
    const ema25 = this.calcEma(closes, 25);
    const ema99 = this.calcEma(closes, 99);

    const toLineData = (values: number[]): LineData[] =>
      candles.map((c, i) => ({ time: c.time, value: values[i] })).filter(d => !isNaN(d.value));

    this.ma7Series?.setData(toLineData(ema7));
    this.ma25Series?.setData(toLineData(ema25));
    this.ma99Series?.setData(toLineData(ema99));

    // Live price
    if (candles.length >= 2) {
      const last = candles[candles.length - 1];
      const prev = candles[candles.length - 2];
      this.livePrice.set(last.close);
      this.livePriceChange.set(+((last.close - prev.close) / prev.close * 100).toFixed(2));
    }

    this.chart?.timeScale().fitContent();
  }

  private calcEma(closes: number[], period: number): number[] {
    const alpha = 2 / (period + 1);
    const result = new Array(closes.length).fill(NaN);
    let started = false;
    for (let i = 0; i < closes.length; i++) {
      if (i < period - 1) continue;
      if (!started) { result[i] = closes.slice(0, period).reduce((a, b) => a + b, 0) / period; started = true; }
      else result[i] = closes[i] * alpha + result[i - 1] * (1 - alpha);
    }
    return result;
  }

  private async buildCandlePayload(): Promise<{ candles1h: any[], candles4h: any[] } | null> {
    const sym = this.selectedSymbol();
    const iv = this.binanceInterval();
    try {
      const [rPrimary, r4h] = await Promise.all([
        fetch(`https://fapi.binance.com/fapi/v1/klines?symbol=${sym}&interval=${iv}&limit=500`).then(r => r.json()),
        fetch(`https://fapi.binance.com/fapi/v1/klines?symbol=${sym}&interval=4h&limit=200`).then(r => r.json()),
      ]);
      const convert = (raw: any[]) => (Array.isArray(raw) ? raw : []).map(k => ({
        timestamp: String(k[0]), open: +k[1], high: +k[2], low: +k[3], close: +k[4], volume: +k[5],
      }));
      return { candles1h: convert(rPrimary), candles4h: convert(r4h) };
    } catch {
      return null;
    }
  }

  private drawChartOverlays(sig: LseSignal) {
    this.clearChartOverlays();
    if (!this.candleSeries) return;

    const make = (price: number | null, color: string, title: string, style = LineStyle.Dashed) => {
      if (!price) return undefined;
      return this.candleSeries.createPriceLine({ price, color, lineWidth: 1, lineStyle: style, axisLabelVisible: true, title });
    };

    this.sweepLine   = make(sig.sweep_low,      '#ff4466', 'SWEEP LOW', LineStyle.Dotted);
    this.reclaimLine = make(sig.reclaim_close,  '#ffdd00', 'RECLAIM');
    this.entryLine   = make(sig.entry_price,    '#00aaff', 'ENTRY', LineStyle.Solid);
    this.tp1Line     = make(sig.take_profit_1,  '#00ff88', 'TP1');
    this.tp2Line     = make(sig.take_profit_2,  '#00cc66', 'TP2', LineStyle.Dotted);
    this.slLine      = make(sig.stop_loss,      '#ff4466', 'SL', LineStyle.Solid);
  }

  private clearChartOverlays() {
    const rm = (line?: IPriceLine) => { if (line && this.candleSeries) try { this.candleSeries.removePriceLine(line); } catch {} };
    rm(this.sweepLine); rm(this.reclaimLine); rm(this.entryLine);
    rm(this.tp1Line); rm(this.tp2Line); rm(this.slLine);
    this.sweepLine = this.reclaimLine = this.entryLine = this.tp1Line = this.tp2Line = this.slLine = undefined;
  }

  private updatePatternStepsFromSignal(sig: LseSignal) {
    const stateMap: Record<string, string> = {
      idle:                 'pending',
      compression_detected: 'confirmed',
      sweep_detected:       'confirmed',
      reclaimed:            'confirmed',
      triggered:            'active',
      closed:               'confirmed',
    };

    const stateOrder = ['idle', 'compression_detected', 'sweep_detected', 'reclaimed', 'triggered', 'closed'];
    const stateIdx   = stateOrder.indexOf(sig.state);

    const now = new Date().toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });

    this.patternSteps.update(steps => steps.map((step, i) => {
      let state: LsePatternStep['state'] = 'pending';
      if (i < stateIdx) state = 'confirmed';
      else if (i === stateIdx) state = 'active';
      else if (i === 4) state = 'waiting';
      return { ...step, state, time: state === 'pending' || state === 'waiting' ? '...' : now };
    }));

    this.cooldownMsg.set(sig.state === 'triggered' ? 'Señal activa — trade abierto' : 'Listo para nueva señal');
  }

  private resetPatternSteps() {
    this.patternSteps.update(steps => steps.map((s, i) => ({
      ...s, state: i === 4 ? 'waiting' : 'pending', time: i === 4 ? '...' : '--:--',
    }) as LsePatternStep));
    this.cooldownMsg.set('Listo para nueva señal en: --');
  }

  private addToHistory(sig: LseSignal) {
    const entry: LseHistoryEntry = {
      symbol: sig.symbol,
      time:   new Date().toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).replace(', ', ' '),
      score:  Math.round(sig.score),
      result: 'Activa',
    };
    this.signalHistory.update(h => [entry, ...h.slice(0, 9)]);
  }

  // ── Template helpers ──────────────────────────────────────────────────────
  formatPrice(v: number | null | undefined, decimals = 4): string {
    if (v == null) return '--';
    return v.toFixed(decimals);
  }

  getScoreBarWidth(value: number, max: number): string {
    return `${Math.min(100, (value / max) * 100)}%`;
  }

  getResultClass(result: string): string {
    if (result === 'TP1' || result === 'TP2') return 'win';
    if (result === 'SL') return 'loss';
    return 'active';
  }

  getScoreDasharray(score: number): string {
    const circumference = 2 * Math.PI * 52;
    const filled = (score / 100) * circumference;
    return `${filled} ${circumference - filled}`;
  }
}
