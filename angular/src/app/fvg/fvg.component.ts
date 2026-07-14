import {
  Component, OnDestroy, AfterViewInit,
  inject, signal, ElementRef, ViewChild
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  createChart, IChartApi, ISeriesApi,
  CandlestickData, CandlestickSeries,
  HistogramSeries, LineSeries,
  ColorType, CrosshairMode, LineStyle
} from 'lightweight-charts';

import { FvgService } from '../proxy/trading/fvg/fvg.service';
import { FvgCascadeResultDto, FvgScanItemDto, FvgZoneDto, VolumeProfileBinDto } from '../proxy/trading/fvg/models';
import { FvgZonePrimitive, FvgRenderZone } from '../shared/charts/fvg-zone-primitive';
import { VolumeProfileSidebarComponent } from '../shared/charts/volume-profile-sidebar.component';
import { VolatileSymbolsService } from '../shared/services/volatile-symbols.service';

const INTERVALS = ['1m', '5m', '15m'];
const VOLATILE_SCAN_SIZE = 80;

/**
 * Exigir que 15m Y 5m estén confirmados AL MISMO TIEMPO (la cascada
 * completa) para aparecer en el Top-5 es pedirle al mercado una
 * coincidencia rarísima — por eso el Top-5 escanea cada temporalidad por
 * su cuenta (1m, 5m, 15m independientes) en vez de exigir la cascada. La
 * cascada completa se sigue usando al analizar UN símbolo puntual
 * (runAnalyze), donde sí tiene sentido buscar la mejor confluencia.
 */
type TopFvgResult = FvgScanItemDto & { interval: string };

@Component({
  selector: 'app-fvg',
  standalone: true,
  imports: [CommonModule, FormsModule, VolumeProfileSidebarComponent],
  templateUrl: './fvg.component.html',
  styleUrls: ['./fvg.component.scss'],
})
export class FvgComponent implements AfterViewInit, OnDestroy {
  @ViewChild('chartContainer') chartContainerRef!: ElementRef<HTMLDivElement>;
  @ViewChild(VolumeProfileSidebarComponent) volumeProfileSidebar!: VolumeProfileSidebarComponent;

  private fvgSvc = inject(FvgService);
  private volatileSvc = inject(VolatileSymbolsService);

  readonly intervals = INTERVALS;

  selectedSymbol = signal('BTCUSDT');
  selectedInterval = signal('15m');
  isLoading = signal(false);
  isTopLoading = signal(false);
  errorMsg = signal<string | null>(null);
  cascade = signal<FvgCascadeResultDto | null>(null);
  topResults = signal<TopFvgResult[]>([]);
  topScanAgeSec = signal<number | null>(null);
  volumeBins = signal<VolumeProfileBinDto[]>([]);

  private topScanAt: number | null = null;
  private topScanAgeInterval: ReturnType<typeof setInterval> | null = null;

  private chart: IChartApi | null = null;
  private candlestickSeries: ISeriesApi<'Candlestick'> | null = null;
  private volumeSeries: ISeriesApi<'Histogram'> | null = null;
  private ma7Series: ISeriesApi<'Line'> | null = null;
  private ma25Series: ISeriesApi<'Line'> | null = null;
  private ma99Series: ISeriesApi<'Line'> | null = null;
  private fvgPrimitive = new FvgZonePrimitive();
  private chartData: CandlestickData[] = [];

  // Guardas anti-carrera: si el usuario cambia de símbolo/temporalidad
  // rápido, una respuesta vieja puede llegar DESPUÉS que una más nueva y
  // pisarla — cada fetch se marca con un token, y solo se aplica si sigue
  // siendo el más reciente cuando la respuesta llega.
  private chartLoadToken = 0;
  private analyzeToken = 0;

  ngAfterViewInit(): void {
    this.initChart(this.chartContainerRef.nativeElement);
    this.loadChartData();
    this.runAnalyze();
  }

  ngOnDestroy(): void {
    window.removeEventListener('resize', this.onResize);
    if (this.topScanAgeInterval) clearInterval(this.topScanAgeInterval);
    this.chart?.remove();
    this.chart = null;
  }

  // ── Chart setup — mismo look que el dashboard ──────────────────────────
  initChart(container: HTMLElement): void {
    this.chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight || 380,
      layout: {
        background: { type: ColorType.Solid, color: 'rgba(5, 9, 16, 0.4)' },
        textColor: '#00f3ff',
        fontFamily: "'Share Tech Mono', 'Orbitron', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: 'rgba(0, 243, 255, 0.04)', style: LineStyle.Dotted },
        horzLines: { color: 'rgba(0, 243, 255, 0.04)', style: LineStyle.Dotted },
      },
      rightPriceScale: { borderColor: 'rgba(0, 243, 255, 0.15)' },
      leftPriceScale: { visible: false },
      timeScale: {
        borderColor: 'rgba(0, 243, 255, 0.15)',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: 'rgba(0, 243, 255, 0.35)', width: 1, style: LineStyle.Dashed, labelBackgroundColor: 'rgba(5, 9, 16, 0.95)' },
        horzLine: { color: 'rgba(0, 243, 255, 0.35)', width: 1, style: LineStyle.Dashed, labelBackgroundColor: 'rgba(5, 9, 16, 0.95)' },
      },
    });

    this.candlestickSeries = this.chart.addSeries(CandlestickSeries, {
      upColor: '#00ff88',
      downColor: '#ff4466',
      borderUpColor: '#00ff88',
      borderDownColor: '#ff4466',
      wickUpColor: '#00ff88',
      wickDownColor: '#ff4466',
    });

    this.volumeSeries = this.chart.addSeries(HistogramSeries, {
      color: '#00e5ff',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    this.chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    this.ma7Series = this.chart.addSeries(LineSeries, { color: '#ffcc00', lineWidth: 1, lineStyle: LineStyle.Dashed, lastValueVisible: false, title: '' });
    this.ma25Series = this.chart.addSeries(LineSeries, { color: '#ba55d3', lineWidth: 1, lastValueVisible: false, title: '' });
    this.ma99Series = this.chart.addSeries(LineSeries, { color: '#722ed1', lineWidth: 1, lastValueVisible: false, title: '' });

    this.candlestickSeries.attachPrimitive(this.fvgPrimitive);

    window.addEventListener('resize', this.onResize);
    this.chart.subscribeCrosshairMove(() => this.volumeProfileSidebar?.render());
    this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => this.volumeProfileSidebar?.render());
  }

  private onResize = () => {
    if (this.chart && this.chartContainerRef) {
      this.chart.applyOptions({ width: this.chartContainerRef.nativeElement.clientWidth });
      this.volumeProfileSidebar?.render();
    }
  };

  toBinanceSymbol(sym: string): string {
    const withoutSettle = sym.includes(':') ? sym.split(':')[0] : sym;
    return withoutSettle.replace(/[/\-]/g, '').toUpperCase().trim();
  }

  loadChartData(): void {
    if (!this.chart || !this.candlestickSeries) return;
    const binanceSym = this.toBinanceSymbol(this.selectedSymbol());
    const interval = this.selectedInterval();
    const token = ++this.chartLoadToken;

    const parseKlines = (raw: any[]) => {
      const candles: CandlestickData[] = [];
      const volumes: any[] = [];
      for (const k of raw) {
        const t = Math.floor(k[0] / 1000) as any;
        const o = parseFloat(k[1]);
        const h = parseFloat(k[2]);
        const l = parseFloat(k[3]);
        const c = parseFloat(k[4]);
        const vol = parseFloat(k[5]);
        candles.push({ time: t, open: o, high: h, low: l, close: c });
        volumes.push({ time: t, value: vol, color: c >= o ? 'rgba(0, 255, 136, 0.4)' : 'rgba(255, 68, 102, 0.4)' });
      }
      return { candles, volumes };
    };

    const apply = (candles: CandlestickData[], volumes: any[]) => {
      if (token !== this.chartLoadToken) return; // una respuesta más nueva ya llegó/está en camino
      this.chartData = [...candles].sort((a, b) => (a.time as number) - (b.time as number));
      const sortedVolumes = [...volumes].sort((a, b) => (a.time as number) - (b.time as number));

      let prec = 2, minMove = 0.01;
      const lastPrice = this.chartData.length ? Number(this.chartData[this.chartData.length - 1].close) : 0;
      if (lastPrice < 0.001) { prec = 6; minMove = 0.000001; }
      else if (lastPrice < 0.1) { prec = 5; minMove = 0.00001; }
      else if (lastPrice < 1) { prec = 4; minMove = 0.0001; }
      else if (lastPrice < 10) { prec = 3; minMove = 0.001; }
      const format = { type: 'price' as const, precision: prec, minMove };

      this.candlestickSeries?.applyOptions({ priceFormat: format });
      this.ma7Series?.applyOptions({ priceFormat: format });
      this.ma25Series?.applyOptions({ priceFormat: format });
      this.ma99Series?.applyOptions({ priceFormat: format });

      this.candlestickSeries?.setData(this.chartData);
      this.volumeSeries?.setData(sortedVolumes);

      this.updateMA(this.chartData, 7, this.ma7Series);
      this.updateMA(this.chartData, 25, this.ma25Series);
      this.updateMA(this.chartData, 99, this.ma99Series);

      this.chart?.timeScale().scrollToRealTime();
      // Re-afirma el cuadrado de entrada/TP/SL después de cada carga de
      // velas — antes se perdía al cambiar de temporalidad porque nada
      // volvía a pedirle a la primitive que se dibuje.
      this.renderEntryZone(this.cascade());
      this.volumeProfileSidebar?.render();
    };

    const futuresUrl = `https://fapi.binance.com/fapi/v1/klines?symbol=${binanceSym}&interval=${interval}&limit=200`;
    fetch(futuresUrl)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((raw: any[]) => {
        if (!Array.isArray(raw) || raw.length === 0) throw new Error('no data');
        const { candles, volumes } = parseKlines(raw);
        apply(candles, volumes);
      })
      .catch((e) => {
        console.error('[FVG] Binance Futures error, fallback a spot:', e);
        const spotUrl = `https://api.binance.com/api/v3/klines?symbol=${binanceSym}&interval=${interval}&limit=200`;
        fetch(spotUrl)
          .then(r => r.json())
          .then((raw: any[]) => {
            const { candles, volumes } = parseKlines(raw);
            apply(candles, volumes);
          })
          .catch(e2 => {
            console.error('[FVG] Binance Spot error:', e2);
            if (token === this.chartLoadToken) {
              this.errorMsg.set('No se pudo cargar el gráfico para este símbolo/temporalidad.');
            }
          });
      });
  }

  private updateMA(data: CandlestickData[], period: number, series: ISeriesApi<'Line'> | null): void {
    if (!series || data.length < period) {
      series?.setData([]);
      return;
    }
    const prices = data.map(d => Number(d.close));
    const maValues = this.calculateSMA(prices, period);
    const maData = maValues.map((val, i) => ({ time: data[i + (data.length - maValues.length)].time, value: val }));
    series.setData(maData);
  }

  private calculateSMA(data: number[], period: number): number[] {
    const sma: number[] = [];
    if (data.length < period) return [];
    let sum = 0;
    for (let i = 0; i < period; i++) sum += data[i];
    sma.push(sum / period);
    for (let i = period; i < data.length; i++) {
      sum = sum - data[i - period] + data[i];
      sma.push(sum / period);
    }
    return sma;
  }

  priceToCoordinate = (price: number): number | null => {
    return this.candlestickSeries?.priceToCoordinate(price) ?? null;
  };

  // ── Acciones ─────────────────────────────────────────────────────────────
  onIntervalChange(interval: string): void {
    this.selectedInterval.set(interval);
    this.loadChartData();
    this.loadVolumeProfile();
    this.clearTopResults(); // la lista anterior quedó escaneada en otra temporalidad, ya no es comparable
  }

  onSymbolChange(symbol: string): void {
    this.selectedSymbol.set(symbol);
    this.loadChartData();
    this.runAnalyze();
  }

  /**
   * El Top-10 mezcla resultados de 1m/5m/15m — cada chip trae SU PROPIA
   * temporalidad (tr.interval), que no necesariamente es la que está
   * elegida en el dropdown. Si solo cambiáramos el símbolo (onSymbolChange)
   * y dejáramos el dropdown como estaba, "Analizar" preguntaría por la
   * temporalidad equivocada — el resultado real (el que armó este chip)
   * puede no existir ahí, y no se dibuja nada aunque el chip diga que SÍ
   * hay un FVG. Por eso acá también se sincroniza el dropdown al hacer clic.
   */
  selectTopResult(tr: TopFvgResult): void {
    if (!tr.symbol) return;
    this.selectedSymbol.set(tr.symbol);
    this.selectedInterval.set(tr.interval);
    this.loadChartData();
    this.loadVolumeProfile();
    this.runAnalyze();
  }

  /**
   * La cascada corre siempre en 15m/5m/1m en paralelo, independiente de qué
   * temporalidad esté mirando el usuario en el gráfico. El volume profile
   * de la izquierda sí depende de la temporalidad elegida (para alinear
   * visualmente con las velas que se están mostrando), así que se pide
   * aparte con el endpoint de un solo timeframe.
   */
  private loadVolumeProfile(): void {
    this.fvgSvc.analyzeOnDemand(this.selectedSymbol(), this.selectedInterval()).subscribe({
      next: (res) => {
        this.volumeBins.set(res.volumeProfile ?? []);
        this.volumeProfileSidebar?.render();
      },
      error: (err) => console.error('[FVG] volume profile error:', err),
    });
  }

  runAnalyze(): void {
    this.isLoading.set(true);
    this.errorMsg.set(null);
    this.loadVolumeProfile();
    const symbolAtRequest = this.selectedSymbol();
    const token = ++this.analyzeToken;
    this.fvgSvc.cascade(symbolAtRequest, this.selectedInterval()).subscribe({
      next: (res) => {
        if (token !== this.analyzeToken) return; // ya se pidió otro símbolo mientras tanto
        this.cascade.set(res);
        this.renderEntryZone(res);
        this.isLoading.set(false);
        this.reconcileTopResult(symbolAtRequest, res);
      },
      error: (err) => {
        if (token !== this.analyzeToken) return;
        console.error('[FVG] cascade error:', err);
        this.errorMsg.set('No se pudo analizar el símbolo.');
        this.isLoading.set(false);
      },
    });
  }

  private startTopScanAgeTracker(): void {
    this.topScanAt = Date.now();
    this.topScanAgeSec.set(0);
    if (this.topScanAgeInterval) clearInterval(this.topScanAgeInterval);
    this.topScanAgeInterval = setInterval(() => {
      if (this.topScanAt) {
        this.topScanAgeSec.set(Math.floor((Date.now() - this.topScanAt) / 1000));
      }
    }, 1000);
  }

  clearTopResults(): void {
    this.topResults.set([]);
    this.topScanAgeSec.set(null);
    this.topScanAt = null;
    if (this.topScanAgeInterval) {
      clearInterval(this.topScanAgeInterval);
      this.topScanAgeInterval = null;
    }
  }

  /**
   * El Top-5 es un snapshot de un momento dado — el precio se mueve rápido
   * y en 1-2 minutos un símbolo puede dejar de ser accionable (ya tocó el
   * TP, o el precio se alejó). Al volver a analizar un símbolo (ej. click
   * en un chip del Top-5) usando la cascada completa, si esa cascada dice
   * que ya no hay nada accionable se sacan TODAS sus entradas (de
   * cualquier temporalidad) de la lista, en vez de dejarlas con un score
   * viejo que ya no refleja la realidad.
   */
  private reconcileTopResult(symbol: string, fresh: FvgCascadeResultDto): void {
    const stillActionable =
      fresh.cascadeStatus !== 'NONE' &&
      (fresh.entryPriceZone?.entryStatus === 'IN_ZONE' || fresh.entryPriceZone?.entryStatus === 'APPROACHING');

    if (stillActionable) return; // nada que corregir, se deja el resultado del scan tal cual
    this.topResults.update(list => list.filter(r => r.symbol !== symbol));
  }

  private renderEntryZone(res: FvgCascadeResultDto | null): void {
    const zone = res?.entryPriceZone;
    const renderZones: FvgRenderZone[] = zone ? [{
      top: zone.top,
      bottom: zone.bottom,
      direction: zone.direction ?? 'bullish',
      slPrice: zone.slPrice,
      tpPrice: zone.tpPrice,
      isIfvg: zone.isIfvg,
      sourceInterval: zone.sourceInterval ?? '',
    }] : [];
    this.fvgPrimitive.updateZones(renderZones);
    this.volumeProfileSidebar?.render();
  }

  /**
   * El scan respeta la temporalidad elegida en el dropdown — antes escaneaba
   * 1m/5m/15m mezclados sin importar qué había elegido el usuario, lo que
   * generaba una lista con velas de distinta escala imposibles de comparar
   * a simple vista, y encima el click sobre un resultado le cambiaba el
   * dropdown por sorpresa. Un solo criterio de temporalidad en toda la
   * página: el que elegís arriba es el que se escanea Y el que se analiza.
   */
  runTopScan(): void {
    this.isTopLoading.set(true);
    const interval = this.selectedInterval();
    this.volatileSvc.getMostVolatile(VOLATILE_SCAN_SIZE).then(symbolsToScan => {
      this.fvgSvc.scan(symbolsToScan, interval).subscribe({
        next: (res) => {
          const items: TopFvgResult[] = (res.top5 ?? []).map(item => ({ ...item, interval }));
          this.topResults.set(items);
          this.isTopLoading.set(false);
          this.startTopScanAgeTracker();
        },
        error: (err) => {
          console.error('[FVG] scan error:', err);
          this.errorMsg.set('No se pudo escanear el exchange.');
          this.isTopLoading.set(false);
        },
      });
    });
  }

  zoneDirectionArrow(z: { direction?: string } | undefined): string {
    return z?.direction === 'bullish' ? '▲' : '▼';
  }

  entryStatusLabel(z: { entryStatus?: string; distToEntryPct?: number } | undefined): string {
    switch (z?.entryStatus) {
      case 'IN_ZONE': return 'EN ZONA';
      case 'APPROACHING': return `A ${(z.distToEntryPct ?? 0).toFixed(2)}%`;
      case 'EXHAUSTED': return 'YA PASÓ';
      case 'TP_HIT': return 'TP ALCANZADO';
      default: return 'LEJOS';
    }
  }

  // Texto genérico (no nombra una temporalidad fija) porque la cascada
  // ahora puede arrancar en 15m, 5m o 1m según lo elegido en el dropdown —
  // "entra con 5m" quedaría mal si la cadena en curso es 5m→1m o solo 1m.
  cascadeStageLabel(status: string | undefined): string {
    switch (status) {
      case 'READY': return 'LISTO PARA ENTRAR';
      case 'AWAITING_EXECUTION': return 'CONFIRMADO — esperando entrada más fina';
      case 'AWAITING_CONFIRMATION': return 'ESPERANDO CONFIRMACIÓN';
      case 'NONE': return 'SIN SESGO CLARO';
      default: return '—';
    }
  }
}
