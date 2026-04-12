import { Component, Input, inject, ViewChild, ElementRef, AfterViewInit, OnDestroy, OnChanges, SimpleChanges, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { statsChartOutline, trendingUpOutline, trendingDownOutline, optionsOutline, listOutline, searchOutline, chevronDownOutline, chevronBackOutline, chevronForwardOutline, timeOutline, globeOutline, water, flame, settingsOutline, shieldCheckmark, closeOutline } from 'ionicons/icons';
import { createChart, IChartApi, ISeriesApi, CandlestickData, CandlestickSeries, LineSeries } from 'lightweight-charts';
import { PairBotInfo } from '../../models/bot.models';
import { BotOrderService } from '../../services/bot-order.service';
import { MarketDataService } from '../../../proxy/trading/market-data.service';
import { SymbolTickerDto } from '../../../proxy/trading/models';
import { FreqtradePollService } from '../../../services/freqtrade-poll.service';
import { FreqtradeService } from '../../../proxy/freqtrade/freqtrade.service';
import { FreqtradeTradeDto } from '../../../proxy/freqtrade/models';
import { Subject, takeUntil, interval, Subscription } from 'rxjs';

@Component({
  selector: 'app-trade-panel',
  standalone: true,
  imports: [CommonModule, IonIcon, FormsModule],
  templateUrl: './trade-panel.component.html',
  styleUrls: ['./trade-panel.component.scss']
})
export class TradePanelComponent implements OnInit, AfterViewInit, OnDestroy, OnChanges {
  @Input() pair: PairBotInfo | null = null;
  @ViewChild('chartContainer') chartContainer!: ElementRef;
  
  private marketDataService = inject(MarketDataService);
  private freqtradeService = inject(FreqtradeService);
  public pollService = inject(FreqtradePollService);
  private destroy$ = new Subject<void>();

  private chart: IChartApi | null = null;
  private candlestickSeries: ISeriesApi<'Candlestick'> | null = null;
  private hmaSeries: ISeriesApi<'Line'> | null = null;
  private ma7Series: ISeriesApi<'Line'> | null = null;
  private ma25Series: ISeriesApi<'Line'> | null = null;
  private ma99Series: ISeriesApi<'Line'> | null = null;

  // Searcher State
  selectedSymbol = 'SIRENUSDT';
  selectedTimeframe = '15m'; 
  hmaPeriod = 50;
  searchTerm = '';
  showSymbolSelector = false;
  tickers: SymbolTickerDto[] = [];
  filteredTickers: SymbolTickerDto[] = [];
  selectedTicker?: SymbolTickerDto;
  tickerSubscription?: Subscription;
  
  // Trades History
  tradeMarkers: any[] = [];
  tradeHistory: FreqtradeTradeDto[] = [];

  timeframes = [
    { value: '1m', label: '1m' },
    { value: '3m', label: '3m' },
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

  constructor() {
    addIcons({ 
      statsChartOutline, trendingUpOutline, trendingDownOutline, 
      optionsOutline, listOutline, searchOutline, chevronDownOutline,
      chevronBackOutline, chevronForwardOutline, timeOutline, 
      globeOutline, water, flame, settingsOutline, shieldCheckmark, closeOutline 
    });
  }

  ngOnInit() {
    this.pollService.selectedPair$.pipe(takeUntil(this.destroy$)).subscribe(pair => {
      if (pair) {
        const clean = pair.replace('/', '').split(':')[0];
        if (clean !== this.selectedSymbol) {
          this.selectedSymbol = clean;
          this.loadData();
        }
      }
    });
    this.loadTickers();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['pair'] && changes['pair'].currentValue) {
      const newPair = changes['pair'].currentValue as PairBotInfo;
      // Normalizar par: XRP/USDT:USDT -> XRPUSDT
      const clean = newPair.symbol.split(':')[0].replace('/', '');
      if (clean !== this.selectedSymbol) {
        this.selectedSymbol = clean;
        this.updateSelectedTicker();
        this.loadData();
      }
    }
  }

  ngAfterViewInit(): void {
    // Timeout para asegurar que el container tenga dimensiones
    setTimeout(() => this.initChart(), 0);
  }

  ngOnDestroy(): void {
    if (this.chart) {
      this.chart.remove();
      this.chart = null;
    }
    this.destroy$.next();
    this.destroy$.complete();
  }

  private initChart() {
    if (!this.chartContainer) return;

    this.chart = createChart(this.chartContainer.nativeElement, {
      width: this.chartContainer.nativeElement.clientWidth,
      height: 480,
      layout: {
        background: { color: '#0d1117' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: 'rgba(42, 46, 57, 0.2)' },
        horzLines: { color: 'rgba(42, 46, 57, 0.2)' },
      },
      rightPriceScale: {
        borderColor: 'rgba(197, 203, 206, 0.8)',
      },
      timeScale: {
        borderColor: 'rgba(197, 203, 206, 0.8)',
        timeVisible: true,
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
      lastValueVisible: true,
    });

    this.ma7Series = this.chart.addSeries(LineSeries, { color: '#fadb14', lineWidth: 1 });
    this.ma25Series = this.chart.addSeries(LineSeries, { color: '#ba55d3', lineWidth: 1 });
    this.ma99Series = this.chart.addSeries(LineSeries, { color: '#722ed1', lineWidth: 1 });

    this.loadData();

    const resizeObserver = new ResizeObserver(() => {
      if (this.chart && this.chartContainer) {
        this.chart.applyOptions({ width: this.chartContainer.nativeElement.clientWidth });
      }
    });
    resizeObserver.observe(this.chartContainer.nativeElement);
  }

  loadTickers() {
    this.marketDataService.getTickers().subscribe({
      next: (data) => {
        this.tickers = data;
        this.filterTickers();
        this.updateSelectedTicker();
      },
      error: (err) => console.error('[TradePanel] Error loading tickers', err)
    });
  }

  filterTickers() {
    const term = (this.searchTerm || '').toUpperCase();
    if (!term) {
      // Priorizar monedas con mayor volumen o simplemente las top 50 de Binance
      this.filteredTickers = this.tickers.slice(0, 50);
    } else {
      this.filteredTickers = this.tickers
        .filter(t => t.symbol.includes(term))
        .sort((a, b) => {
          // Si empieza con el término, va primero
          if (a.symbol.startsWith(term) && !b.symbol.startsWith(term)) return -1;
          if (!a.symbol.startsWith(term) && b.symbol.startsWith(term)) return 1;
          return a.symbol.localeCompare(b.symbol);
        })
        .slice(0, 50);
    }
  }

  updateSelectedTicker() {
    this.selectedTicker = this.tickers.find(t => t.symbol === this.selectedSymbol);
  }

  selectSymbol(symbol: string) {
    this.selectedSymbol = symbol;
    this.showSymbolSelector = false;
    this.updateSelectedTicker();
    this.loadData();
  }

  onTimeframeChange(tf: string) {
    this.selectedTimeframe = tf;
    this.loadData();
  }

  onHmaChange() {
    this.loadData();
  }

  private loadData() {
    if (!this.candlestickSeries) return;
    
    // El Dashboard usa el timeframe sin el 'm' para la API
    const intervalArg = this.selectedTimeframe.replace('m', '');

    this.marketDataService.getCandles({
      symbol: this.selectedSymbol,
      interval: intervalArg, 
      limit: 1000
    }).pipe(takeUntil(this.destroy$)).subscribe(data => {
      if (this.candlestickSeries && data && data.length > 0) {
        const sortedData = data.map(d => ({
          time: d.time as any,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close
        })).sort((a, b) => a.time - b.time);
        
        this.candlestickSeries.setData(sortedData);
        
        this.updateMA(sortedData, this.hmaPeriod, this.hmaSeries!);
        this.updateMA(sortedData, 7, this.ma7Series!);
        this.updateMA(sortedData, 25, this.ma25Series!);
        this.updateMA(sortedData, 99, this.ma99Series!);

        this.updateTradeMarkers();
        this.chart?.timeScale().fitContent();
      }
    });

    this.updateSelectedTicker();
    this.loadTradeHistory();
  }

  private loadTradeHistory() {
    this.freqtradeService.getTradeHistory(this.selectedSymbol).subscribe(history => {
      this.tradeHistory = history || [];
      this.updateTradeMarkers();
    });
  }

  private updateTradeMarkers() {
    if (!this.candlestickSeries || !this.tradeHistory.length) return;

    const markers: any[] = [];
    
    this.tradeHistory.forEach(trade => {
      if (trade.openDate) {
        const openTime = new Date(trade.openDate).getTime() / 1000;
        markers.push({
          time: openTime,
          position: trade.isShort ? 'aboveBar' : 'belowBar',
          color: trade.isShort ? '#ef5350' : '#26a69a',
          shape: trade.isShort ? 'arrowDown' : 'arrowUp',
          text: trade.isShort ? 'Short entry' : 'Long entry'
        });
      }

      if (trade.closeDate) {
        const closeTime = new Date(trade.closeDate).getTime() / 1000;
        markers.push({
          time: closeTime,
          position: trade.isShort ? 'belowBar' : 'aboveBar',
          color: '#fadb14',
          shape: 'diamond',
          text: 'Exit'
        });
      }
    });

    (this.candlestickSeries as any).setMarkers(markers.sort((a, b) => a.time - b.time));
  }

  private updateMA(data: any[], period: number, series: ISeriesApi<'Line'>) {
    if (!series) return;
    const maData = data.map((d, i) => {
      if (i < period) return null;
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += data[i - j].close;
      }
      return { time: d.time, value: sum / period };
    }).filter(d => d !== null);
    series.setData(maData as any[]);
  }
}
