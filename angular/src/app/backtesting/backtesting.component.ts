import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { of } from 'rxjs';
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

// El job sigue vivo en el servidor Python aunque la pagina se recargue (F5,
// hot-reload de ng serve al editar el componente, cambio de pestaña) -- el
// job_id se guarda en localStorage para poder reengancharse al volver, en
// vez de perder el progreso visualmente mientras el backtest real sigue
// corriendo huerfano del lado del servidor.
const RUN_JOB_STORAGE_KEY = 'verge_backtest_active_run_job';
const SYNC_JOB_STORAGE_KEY = 'verge_backtest_active_sync_job';

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
  symbols_used?: string[] | null;
  symbols_count?: number | null;
}

interface JobStatus {
  status: 'running' | 'completed' | 'failed';
  done: number;
  total: number;
  error?: string;
}

interface RunSummary {
  id: string;
  strategyProfileId: string;
  strategyName: string;
  strategyType: string;
  startDate: string;
  endDate: string;
  runAt: string;
  totalPnlUsdt: number;
  winRatePct: number;
  acceptedTrades: number;
}

interface CoverageResponse {
  gaps: Record<string, Record<string, string[]>>;
  total_missing_symbol_days: number;
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

  // Alcance de símbolos: todo el watchlist (400+) o solo el top 40 por
  // capitalización/liquidez (menos ruido de pares chicos).
  symbolScope: 'all' | 'top40' = 'all';

  isRunning = false;
  progressDone = 0;
  progressTotal = 0;
  errorMessage = '';
  results: BacktestResult | null = null;

  // Cobertura de datos / "Actualizar datos"
  isSyncing = false;
  syncDone = 0;
  syncTotal = 0;
  syncMessage = '';
  coverageGapCount: number | null = null;

  // Historial de corridas
  runs: RunSummary[] = [];
  viewingRun: BacktestResult | null = null;

  private jobId: string | null = null;
  private pollHandle: ReturnType<typeof setInterval> | null = null;
  private syncJobId: string | null = null;
  private syncPollHandle: ReturnType<typeof setInterval> | null = null;

  ngOnInit() {
    this.strategyProfileService.getList().subscribe({
      next: (profiles) => {
        // Tipos ya conectados al motor (ver agent/backtest/api.py) -- el
        // resto (ArrowPeak, GoldenUTurn, TotalSweep, Generic) se agrega con
        // el mismo molde mas adelante.
        const SUPPORTED_TYPES = ['MaGeometry', 'FVG', 'AdnCompression'];
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
    this.loadRuns();
    this.resumeActiveJobs();
  }

  /** Reengancha polling de jobs que quedaron corriendo del lado del servidor
   * de una carga anterior de la pagina (reload, hot-reload, cambio de pestaña).
   * Primero mira localStorage; si no hay nada guardado ahi (ej. el job
   * arranco antes de que existiera este guardado, o se abre desde otro
   * navegador), pregunta al servidor por jobs activos como fallback. */
  private resumeActiveJobs() {
    const savedRunJob = localStorage.getItem(RUN_JOB_STORAGE_KEY);
    if (savedRunJob) {
      this.jobId = savedRunJob;
      this.isRunning = true;
      this.pollStatus();
      this.startPolling();
    }
    const savedSyncJob = localStorage.getItem(SYNC_JOB_STORAGE_KEY);
    if (savedSyncJob) {
      this.syncJobId = savedSyncJob;
      this.isSyncing = true;
      this.pollSyncStatus();
      this.startSyncPolling();
    }

    if (savedRunJob && savedSyncJob) return;

    this.http.get<{ active: { jobId: string; kind: 'run' | 'sync'; done: number; total: number }[] }>(
      `${BACKTEST_API_BASE}/backtest/jobs/active`
    ).subscribe({
      next: (resp) => {
        for (const job of resp.active) {
          if (job.kind === 'run' && !savedRunJob) {
            this.jobId = job.jobId;
            this.isRunning = true;
            this.progressDone = job.done;
            this.progressTotal = job.total;
            localStorage.setItem(RUN_JOB_STORAGE_KEY, job.jobId);
            this.startPolling();
          } else if (job.kind === 'sync' && !savedSyncJob) {
            this.syncJobId = job.jobId;
            this.isSyncing = true;
            this.syncDone = job.done;
            this.syncTotal = job.total;
            localStorage.setItem(SYNC_JOB_STORAGE_KEY, job.jobId);
            this.startSyncPolling();
          }
        }
      },
      error: () => {
        // silencioso -- si el servidor esta caido, el resto de la pantalla igual funciona
      },
    });
  }

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  ngOnDestroy() {
    this.stopPolling();
    this.stopSyncPolling();
  }

  handleBack() {
    this.stopPolling();
    this.stopSyncPolling();
    this.router.navigate(['/']);
  }

  get progressPct(): number {
    if (!this.progressTotal) return 0;
    return Math.round((this.progressDone / this.progressTotal) * 100);
  }

  get syncProgressPct(): number {
    if (!this.syncTotal) return 0;
    return Math.round((this.syncDone / this.syncTotal) * 100);
  }

  monthlyEntries(result: BacktestResult | null): Array<{ month: string } & MonthlyBreakdownEntry> {
    if (!result) return [];
    return Object.entries(result.monthly_breakdown)
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
    this.viewingRun = null;
    this.progressDone = 0;
    this.progressTotal = 0;

    // symbolScope=top40 -> pide la lista de símbolos top 40 al servidor
    // (por capitalización/liquidez, ya intersectada con lo que hay
    // cacheado) y la manda explícita; symbolScope=all -> no manda `symbols`,
    // el servidor usa el watchlist completo (comportamiento de siempre).
    const symbols$ =
      this.symbolScope === 'top40'
        ? this.http.get<{ symbols: string[] }>(`${BACKTEST_API_BASE}/backtest/symbols/top40`)
        : of<{ symbols: string[] | undefined }>({ symbols: undefined });

    symbols$.subscribe({
      next: (resp) => {
        this.http
          .post<{ jobId: string }>(`${BACKTEST_API_BASE}/backtest/run`, {
            strategyProfileId: this.selectedProfileId,
            startDate: this.startDate,
            endDate: this.endDate,
            symbols: resp.symbols,
          })
          .subscribe({
            next: (runResp) => {
              this.jobId = runResp.jobId;
              localStorage.setItem(RUN_JOB_STORAGE_KEY, runResp.jobId);
              this.startPolling();
            },
            error: () => {
              this.isRunning = false;
              this.errorMessage = 'No se pudo iniciar el backtest (¿está corriendo agent/backtest/api.py?).';
            },
          });
      },
      error: () => {
        this.isRunning = false;
        this.errorMessage = 'No se pudo obtener la lista de símbolos top 40.';
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
          localStorage.removeItem(RUN_JOB_STORAGE_KEY);
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
        localStorage.removeItem(RUN_JOB_STORAGE_KEY);
        this.loadRuns();
      },
      error: () => {
        this.isRunning = false;
        this.errorMessage = 'No se pudo obtener el resultado final.';
      },
    });
  }

  // ── Actualizar datos ──────────────────────────────────────────────────
  checkCoverage() {
    this.http
      .get<CoverageResponse>(`${BACKTEST_API_BASE}/backtest/data/coverage`, {
        params: { startDate: this.startDate, endDate: this.endDate },
      })
      .subscribe({
        next: (resp) => {
          this.coverageGapCount = resp.total_missing_symbol_days;
        },
        error: () => {
          this.errorMessage = 'No se pudo chequear la cobertura de datos.';
        },
      });
  }

  syncData() {
    this.isSyncing = true;
    this.syncMessage = '';
    this.syncDone = 0;
    this.syncTotal = 0;

    this.http
      .post<{ jobId: string }>(`${BACKTEST_API_BASE}/backtest/data/sync`, {
        startDate: this.startDate,
        endDate: this.endDate,
      })
      .subscribe({
        next: (resp) => {
          this.syncJobId = resp.jobId;
          localStorage.setItem(SYNC_JOB_STORAGE_KEY, resp.jobId);
          this.startSyncPolling();
        },
        error: () => {
          this.isSyncing = false;
          this.errorMessage = 'No se pudo iniciar la actualización de datos.';
        },
      });
  }

  private startSyncPolling() {
    this.syncPollHandle = setInterval(() => this.pollSyncStatus(), 2000);
  }

  private stopSyncPolling() {
    if (this.syncPollHandle) {
      clearInterval(this.syncPollHandle);
      this.syncPollHandle = null;
    }
  }

  private pollSyncStatus() {
    if (!this.syncJobId) return;
    this.http.get<JobStatus>(`${BACKTEST_API_BASE}/backtest/status/${this.syncJobId}`).subscribe({
      next: (status) => {
        this.syncDone = status.done;
        this.syncTotal = status.total;
        if (status.status === 'completed') {
          this.stopSyncPolling();
          this.isSyncing = false;
          this.syncMessage = this.syncTotal === 0
            ? 'Los datos ya estaban al día — no hizo falta descargar nada.'
            : `Actualización completa (${this.syncTotal} descargas).`;
          localStorage.removeItem(SYNC_JOB_STORAGE_KEY);
          this.checkCoverage();
        } else if (status.status === 'failed') {
          this.stopSyncPolling();
          this.isSyncing = false;
          this.errorMessage = status.error || 'La actualización de datos falló.';
          localStorage.removeItem(SYNC_JOB_STORAGE_KEY);
        }
      },
      error: () => {
        this.stopSyncPolling();
        this.isSyncing = false;
        this.errorMessage = 'Se perdió la conexión durante la actualización de datos.';
      },
    });
  }

  // ── Historial de corridas ─────────────────────────────────────────────
  loadRuns() {
    this.http.get<{ runs: RunSummary[] }>(`${BACKTEST_API_BASE}/backtest/runs`).subscribe({
      next: (resp) => {
        this.runs = resp.runs;
      },
      error: () => {
        // silencioso -- no bloquea el resto de la pantalla si el historial falla
      },
    });
  }

  viewRun(runId: string) {
    this.http.get<BacktestResult>(`${BACKTEST_API_BASE}/backtest/runs/${runId}`).subscribe({
      next: (result) => {
        this.viewingRun = result;
        this.results = null;
      },
      error: () => {
        this.errorMessage = 'No se pudo cargar el detalle de esa corrida.';
      },
    });
  }

  closeRunDetail() {
    this.viewingRun = null;
  }

  formatMonth(month: string): string {
    const [y, m] = month.split('-');
    const nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
    return `${nombres[parseInt(m, 10) - 1]} ${y}`;
  }
}
