import { Component, inject, OnInit, ViewChild, ElementRef, AfterViewInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { StrategyProfileService } from '../../services/strategy-profile.service';
import { IonIcon } from '@ionic/angular/standalone';
import { createChart } from 'lightweight-charts';

@Component({
  selector: 'app-strategy-performance',
  standalone: true,
  imports: [CommonModule, IonIcon],
  templateUrl: './strategy-performance.component.html',
  styleUrls: ['./strategy-performance.component.scss']
})
export class StrategyPerformanceComponent implements OnInit, AfterViewInit, OnDestroy {
  private service = inject(StrategyProfileService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  @ViewChild('chartContainer') chartContainer!: ElementRef;

  id: string | null = null;
  profile: any = null;
  performance: any = null;
  isLoading = false;
  activeTab = 'summary'; // summary, equity, distribution, symbols, trades

  private chart: any;
  private lineSeries: any;

  ngOnInit() {
    this.id = this.route.snapshot.paramMap.get('id');
    if (this.id) {
      this.loadPerformance(this.id);
    }
  }

  ngAfterViewInit() {
    // Initialized when data is ready
  }

  ngOnDestroy() {
    if (this.chart) {
      this.chart.remove();
    }
  }

  loadPerformance(id: string) {
    this.isLoading = true;
    
    // Load Profile Details
    if (id === 'standard') {
      this.profile = {
        name: 'Standard Scalping',
        isActive: true,
        description: 'Estrategia base del sistema. Nexus-15 + LSE para scalping de alta frecuencia.',
        color: '#3b82f6'
      };
    } else {
      this.service.getById(id).subscribe(p => this.profile = p);
    }

    // Load Performance Data
    this.service.getPerformance(id).subscribe(data => {
      this.performance = data;
      this.isLoading = false;
      
      // Additional calculations for the institutional view
      if (this.performance && this.performance.allTrades) {
        this.processExtendedMetrics();
        setTimeout(() => this.initChart(), 0);
      }
    });
  }

  initChart() {
    if (!this.chartContainer) return;
    if (this.chart) this.chart.remove();

    this.chart = createChart(this.chartContainer.nativeElement, {
      layout: {
        background: { color: 'transparent' },
        textColor: 'rgba(255, 255, 255, 0.5)',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      width: this.chartContainer.nativeElement.clientWidth,
      height: 350,
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
        timeVisible: true,
      },
    });

    this.lineSeries = this.chart.addAreaSeries({
      lineColor: this.profile?.color || '#00C47D',
      topColor: (this.profile?.color || '#00C47D') + '33',
      bottomColor: (this.profile?.color || '#00C47D') + '00',
      lineWidth: 2,
    });

    if (this.performance.allTrades && this.performance.allTrades.length > 0) {
      // Sort trades by date ASC for chart
      const sorted = [...this.performance.allTrades].sort((a,b) => new Date(a.openedAt!).getTime() - new Date(b.openedAt!).getTime());
      let cumulative = 100;
      const chartData = sorted.map(t => {
        cumulative += (t.roiPercentage || 0);
        return {
          time: Math.floor(new Date(t.openedAt!).getTime() / 1000),
          value: cumulative
        };
      });
      this.lineSeries.setData(chartData);
      this.chart.timeScale().fitContent();
    }
  }

  processExtendedMetrics() {
    const trades = this.performance.allTrades || [];
    if (trades.length === 0) return;

    // Profit Factor
    const grossProfit = trades.filter((t: any) => t.realizedPnl > 0).reduce((acc: any, t: any) => acc + t.realizedPnl, 0);
    const grossLoss = Math.abs(trades.filter((t: any) => t.realizedPnl < 0).reduce((acc: any, t: any) => acc + t.realizedPnl, 0));
    this.performance.profitFactor = grossLoss === 0 ? grossProfit : (grossProfit / grossLoss);

    // Distribution
    const pnlValues = trades.map((t: any) => t.roiPercentage || 0);
    this.performance.maxGain = Math.max(...pnlValues);
    this.performance.maxLoss = Math.min(...pnlValues);
    
    // Hourly Heatmap (Mock logic for now based on actual trades)
    this.performance.heatmap = this.calculateHeatmap(trades);
  }

  calculateHeatmap(trades: any[]) {
    const map: any = {};
    const days = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
    days.forEach(d => map[d] = new Array(24).fill(0));
    
    trades.forEach(t => {
      const date = new Date(t.openedAt);
      const day = days[date.getDay() === 0 ? 6 : date.getDay() - 1];
      const hour = date.getHours();
      map[day][hour]++;
    });
    return map;
  }

  setTab(tab: string) {
    this.activeTab = tab;
  }

  onEdit() {
    if (this.id && this.id !== 'standard') {
      this.router.navigate(['/strategies/edit', this.id]);
    }
  }

  goBack() {
    this.router.navigate(['/strategies']);
  }
}
