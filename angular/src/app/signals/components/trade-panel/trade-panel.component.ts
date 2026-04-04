import { Component, Input, inject, computed, ViewChild, ElementRef, AfterViewInit, OnDestroy, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { statsChartOutline, trendingUpOutline, trendingDownOutline, optionsOutline, listOutline } from 'ionicons/icons';
import { createChart, IChartApi, ISeriesApi, CandlestickData, CandlestickSeries, LineSeries } from 'lightweight-charts';
import { PairBotInfo, SimulatedOrder } from '../../models/bot.models';
import { BotOrderService } from '../../services/bot-order.service';
import { MarketDataService } from '../../../proxy/trading/market-data.service';
import { Subject, takeUntil } from 'rxjs';

@Component({
  selector: 'app-trade-panel',
  standalone: true,
  imports: [CommonModule, IonIcon],
  template: `
    <div class="institutional-chart-container">
      <div class="chart-header">
        <div class="left">
          <span class="label">Bot Signal:</span>
          <span class="signal-value" [ngClass]="pair?.recommendedAction | lowercase">
            {{ pair?.recommendedAction }}
          </span>
        </div>
        <div class="right">
          <span class="score-badge">+8</span>
          <ion-icon name="options-outline"></ion-icon>
          <ion-icon name="list-outline"></ion-icon>
        </div>
      </div>

      <div class="confidence-info">
        <span class="label">Confianza:</span>
        <span class="value success">{{ pair?.score }}%</span>
      </div>

      <div class="tags-row">
        <span class="tag"><span class="dot green"></span> Whale accumulation</span>
        <span class="tag"><span class="dot green"></span> RSI oversold</span>
        <span class="tag"><span class="dot blue"></span> Breakout micro range</span>
      </div>

      <div class="chart-wrapper">
        <div #chartContainer class="full-chart"></div>
      </div>
    </div>
  `,
  styles: [`
    .institutional-chart-container {
      background: rgba(21, 26, 38, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      padding: 20px;
      color: white;
    }

    .chart-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;

      .left {
        display: flex;
        gap: 8px;
        align-items: center;
        .label { font-size: 14px; color: #8b949e; font-weight: 600; }
        .signal-value {
          font-size: 14px;
          font-weight: 800;
          &.long { color: #22c55e; }
          &.short { color: #ef4444; }
          &.wait { color: #f59e0b; }
        }
      }

      .right {
        display: flex;
        gap: 12px;
        align-items: center;
        color: #8b949e;
        
        .score-badge {
          background: rgba(38, 166, 154, 0.2);
          color: #26a69a;
          padding: 2px 8px;
          border-radius: 4px;
          font-size: 12px;
          font-weight: 700;
        }
      }
    }

    .confidence-info {
      margin-bottom: 12px;
      font-size: 14px;
      .label { color: #8b949e; }
      .value.success { color: #22c55e; font-weight: 700; margin-left: 8px; }
    }

    .tags-row {
      display: flex;
      gap: 16px;
      margin-bottom: 20px;
      
      .tag {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        color: #f0f6fc;
        
        .dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          &.green { background: #22c55e; box-shadow: 0 0 6px rgba(34, 197, 94, 0.5); }
          &.blue { background: #3b82f6; box-shadow: 0 0 6px rgba(59, 130, 246, 0.5); }
        }
      }
    }

    .chart-wrapper {
      height: 380px;
      width: 100%;
      background: #0d1117;
      border-radius: 8px;
      overflow: hidden;
      
      .full-chart { width: 100%; height: 100%; }
    }
  `]
})
export class TradePanelComponent implements AfterViewInit, OnDestroy, OnChanges {
  @Input() pair: PairBotInfo | null = null;
  @ViewChild('chartContainer') chartContainer!: ElementRef;
  
  private marketDataService = inject(MarketDataService);
  private destroy$ = new Subject<void>();

  private chart: IChartApi | null = null;
  private candlestickSeries: ISeriesApi<'Candlestick'> | null = null;
  private hmaSeries: ISeriesApi<'Line'> | null = null;

  constructor() {
    addIcons({ statsChartOutline, trendingUpOutline, trendingDownOutline, optionsOutline, listOutline });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['pair'] && !changes['pair'].firstChange) {
      this.loadData();
    }
  }

  ngAfterViewInit(): void {
    this.initChart();
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
      height: 380,
      layout: {
        background: { color: '#0d1117' },
        textColor: '#8b949e',
      },
      grid: {
        vertLines: { color: 'rgba(42, 46, 57, 0.1)' },
        horzLines: { color: 'rgba(42, 46, 57, 0.1)' },
      },
      timeScale: {
        borderColor: 'rgba(197, 203, 206, 0.2)',
        timeVisible: true,
      },
    });

    this.candlestickSeries = this.chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });

    this.hmaSeries = this.chart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 2,
    });

    this.loadData();

    const resizeObserver = new ResizeObserver(() => {
      if (this.chart && this.chartContainer) {
        this.chart.applyOptions({ width: this.chartContainer.nativeElement.clientWidth });
      }
    });
    resizeObserver.observe(this.chartContainer.nativeElement);
  }

  private loadData() {
    if (!this.pair || !this.candlestickSeries) return;
    
    const cleanSymbol = this.pair.symbol.split(':')[0].replace('/', '');
    
    this.marketDataService.getCandles({
      symbol: cleanSymbol,
      interval: '1m', // As seen in image
      limit: 100
    }).pipe(takeUntil(this.destroy$)).subscribe(data => {
      if (this.candlestickSeries && data.length > 0) {
        const sortedData = data.map(d => ({
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close
        } as CandlestickData)).sort((a, b) => (a.time as number) - (b.time as number));
        
        this.candlestickSeries.setData(sortedData);
        
        if (this.hmaSeries) {
          const maData = sortedData.map((d, i) => {
            if (i < 20) return null;
            const slice = sortedData.slice(i - 20, i);
            const sum = slice.reduce((acc, val) => acc + val.close, 0);
            return { time: d.time, value: sum / 20 };
          }).filter(d => d !== null) as any[];
          this.hmaSeries.setData(maData);
        }

        this.chart?.timeScale().fitContent();
      }
    });
  }
}
