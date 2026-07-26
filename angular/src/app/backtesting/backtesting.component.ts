import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { InputComponent } from 'src/shared/components/input/input.component';
import { LabelComponent } from 'src/shared/components/label/label.component';
import { SelectComponent } from 'src/shared/components/select/select.component';
import { PaymentChartComponent } from 'src/shared/components/payment-chart/payment-chart.component';
import { IconService } from 'src/shared/services/icon.service';
import { IonIcon } from '@ionic/angular/standalone';
import { StrategyProfileService } from 'src/app/proxy/trading/strategy-profile.service';
import { StrategyProfileDto } from 'src/app/proxy/trading/dtos/models';

// El motor de backtest corre como proceso propio dentro de agent/
// (agent/backtest/api.py, necesita import directo de verge_agent.py /
// risk_manager.py) -- no pasa por el backend ABP ni por python-service.
const BACKTEST_API_BASE = 'http://localhost:8010';

interface MonthlyBreakdownEntry {
  trades: number;
  pnl: number;
  win_rate_pct: number;
}

interface BacktestResult {
  strategy_name: string;
  total_signals: number;
  accepted_trades: number;
  rejected_no_slot: number;
  win_rate_pct: number;
  total_pnl_usdt: number;
  capital: number;
  monthly_breakdown: Record<string, MonthlyBreakdownEntry>;
}

interface JobStatus {
  status: 'running' | 'completed' | 'failed';
  done: number;
  total: number;
  error?: string;
}

@Component({
  selector: 'app-backtesting',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    CardContentComponent,
    GlassButtonComponent,
    InputComponent,
    LabelComponent,
    SelectComponent,
    PaymentChartComponent,
    IonIcon,
  ],
  templateUrl: './backtesting.component.html',
})
export class BacktestingComponent implements OnInit, OnDestroy {
  private iconService = inject(IconService);
  private router = inject(Router);
  private http = inject(HttpClient);
  private strategyProfileService = inject(StrategyProfileService);

  profiles: StrategyProfileDto[] = [];
  strategyOptions: { value: string; label: string }[] = [];
  selectedProfileId = '';
  startDate = '2025-12-01';
  endDate = new Date().toISOString().slice(0, 10);

  isRunning = false;
  progressDone = 0;
  progressTotal = 0;
  errorMessage = '';
  results: BacktestResult | null = null;

  private jobId: string | null = null;
  private pollHandle: ReturnType<typeof setInterval> | null = null;

  ngOnInit() {
    this.strategyProfileService.getList().subscribe({
      next: (profiles) => {
        // Tipos ya conectados al motor (ver agent/backtest/api.py, registro
        // `runners`) -- el resto (AdnCompression, ArrowPeak, GoldenUTurn,
        // TotalSweep) se agrega con el mismo molde mas adelante.
        const SUPPORTED_TYPES = ['MaGeometry', 'FVG'];
        this.profiles = profiles.filter((p) => SUPPORTED_TYPES.includes((p as any).strategyType));
        this.strategyOptions = this.profiles.map((p) => ({ value: p.id!, label: p.name || p.id! }));
        if (this.profiles.length) {
          this.selectedProfileId = this.profiles[0].id!;
        }
      },
      error: () => {
        this.errorMessage = 'No se pudieron cargar los perfiles de estrategia.';
      },
    });
  }

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  ngOnDestroy() {
    this.stopPolling();
  }

  handleBack() {
    this.stopPolling();
    this.router.navigate(['/']);
  }

  get progressPct(): number {
    if (!this.progressTotal) return 0;
    return Math.round((this.progressDone / this.progressTotal) * 100);
  }

  get monthlyEntries(): Array<{ month: string } & MonthlyBreakdownEntry> {
    if (!this.results) return [];
    return Object.entries(this.results.monthly_breakdown)
      .map(([month, v]) => ({ month, ...v }))
      .sort((a, b) => a.month.localeCompare(b.month));
  }

  runBacktest() {
    if (!this.selectedProfileId) {
      this.errorMessage = 'Elegí una estrategia primero.';
      return;
    }
    this.isRunning = true;
    this.errorMessage = '';
    this.results = null;
    this.progressDone = 0;
    this.progressTotal = 0;

    this.http
      .post<{ jobId: string }>(`${BACKTEST_API_BASE}/backtest/run`, {
        strategyProfileId: this.selectedProfileId,
        startDate: this.startDate,
        endDate: this.endDate,
      })
      .subscribe({
        next: (resp) => {
          this.jobId = resp.jobId;
          this.startPolling();
        },
        error: (err) => {
          this.isRunning = false;
          this.errorMessage = 'No se pudo iniciar el backtest (¿está corriendo agent/backtest/api.py?).';
        },
      });
  }

  private startPolling() {
    this.pollHandle = setInterval(() => this.pollStatus(), 2000);
  }

  private stopPolling() {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
  }

  private pollStatus() {
    if (!this.jobId) return;
    this.http.get<JobStatus>(`${BACKTEST_API_BASE}/backtest/status/${this.jobId}`).subscribe({
      next: (status) => {
        this.progressDone = status.done;
        this.progressTotal = status.total;
        if (status.status === 'completed') {
          this.stopPolling();
          this.fetchResult();
        } else if (status.status === 'failed') {
          this.stopPolling();
          this.isRunning = false;
          this.errorMessage = status.error || 'El backtest falló.';
        }
      },
      error: () => {
        this.stopPolling();
        this.isRunning = false;
        this.errorMessage = 'Se perdió la conexión con el motor de backtest.';
      },
    });
  }

  private fetchResult() {
    if (!this.jobId) return;
    this.http.get<BacktestResult>(`${BACKTEST_API_BASE}/backtest/result/${this.jobId}`).subscribe({
      next: (result) => {
        this.results = result;
        this.isRunning = false;
      },
      error: () => {
        this.isRunning = false;
        this.errorMessage = 'No se pudo obtener el resultado final.';
      },
    });
  }

  formatMonth(month: string): string {
    const [y, m] = month.split('-');
    const nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
    return `${nombres[parseInt(m, 10) - 1]} ${y}`;
  }
}
