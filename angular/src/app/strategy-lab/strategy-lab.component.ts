import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { IonIcon } from '@ionic/angular/standalone';

// El laboratorio corre como proceso propio dentro de agent/backtest/
// (strategy_lab.py, loop infinito sin supervision) -- este componente solo
// LEE los .jsonl que escribe, vía el mismo servicio del motor de backtest
// (agent/backtest/api.py :8010) que ya expone /backtest/*.
const LAB_API_BASE = 'http://localhost:8010';
// 2026-08-18: servicio de control aparte (:8011), corre en el HOST (no en
// Docker como :8010) -- boton de arranque/parada pedido por el usuario
// ("si algun dia no te tengo a vos, quiero resolverlo con el boton").
// agent/backtest/lab_control_server.py, auto-arranca con la tarea
// programada Verge-LabControl-AutoStart.
const LAB_CONTROL_BASE = 'http://localhost:8011';
const POLL_INTERVAL_MS = 8000;
const CURRENT_POLL_INTERVAL_MS = 3000;
const CONTROL_POLL_INTERVAL_MS = 5000;

interface LabStatus {
  progressLine: string | null;
  testedCount: number;
  foundCount: number;
  isRunning: boolean | null;
  heartbeatAgeSec: number | null;
}

interface LabCurrent {
  available: boolean;
  isRunning?: boolean;
  heartbeatAgeSec?: number;
  tried?: number;
  found?: number;
  currentLabel?: string | null;
  currentStrat?: StrategyDef | null;
  elapsedSec?: number | null;
}

interface StrategyResult {
  n: number;
  wr_pct: number;
  pnl_total: number;
  monthly: number;
  avg_pnl_per_trade: number;
  n_h1: number;
  n_h2: number;
  pnl_h1: number;
  pnl_h2: number;
  wr_h1: number;
  wr_h2: number;
  stable_between_halves: boolean;
  both_halves_positive: boolean;
  passes_bar: boolean;
  insufficient_data?: boolean;
}

interface StrategyDef {
  entry_type: string;
  tf_min: number;
  ma_pair: [number, number];
  side: string;
  atr_sl_mult: number;
  rr_mult: number;
  lookback: number;
  rsi_thresh: [number, number];
}

interface StrategyRow {
  strat: StrategyDef;
  result: StrategyResult;
  ts: string;
}

type SortKey = 'monthly' | 'wr_pct' | 'n' | 'pnl_total';

const ENTRY_TYPE_LABEL: Record<string, string> = {
  ma_cross: 'Cruce de Medias',
  level_sweep: 'Barrido de Nivel',
  band_touch: 'Toque de Banda',
  rsi_extreme: 'RSI Extremo',
};

@Component({
  selector: 'app-strategy-lab',
  standalone: true,
  imports: [CommonModule, FormsModule, IonIcon],
  templateUrl: './strategy-lab.component.html',
  styleUrls: ['./strategy-lab.component.scss'],
})
export class StrategyLabComponent implements OnInit, OnDestroy {
  private http = inject(HttpClient);
  private pollHandle: any = null;
  private currentPollHandle: any = null;
  private controlPollHandle: any = null;

  status: LabStatus | null = null;
  current: LabCurrent | null = null;
  found: StrategyRow[] = [];
  topAll: StrategyRow[] = [];
  top10: StrategyRow[] = [];

  loading = true;
  error: string | null = null;

  // Servicio de control (:8011, host) -- null = no se pudo determinar
  // todavia (primer chequeo en curso) o el servicio no esta disponible.
  controlAvailable: boolean | null = null;
  controlRunning = false;
  controlBusy = false;

  viewMode: 'found' | 'all' = 'found';
  sortKey: SortKey = 'monthly';
  sortDir: -1 | 1 = -1;
  filterEntryType = '';
  filterSide = '';
  expandedIndex: number | null = null;
  showTop10 = false;

  entryTypeLabel = ENTRY_TYPE_LABEL;

  ngOnInit(): void {
    this.refresh();
    this.refreshCurrent();
    this.refreshControlStatus();
    this.pollHandle = setInterval(() => this.refresh(), POLL_INTERVAL_MS);
    this.currentPollHandle = setInterval(() => this.refreshCurrent(), CURRENT_POLL_INTERVAL_MS);
    this.controlPollHandle = setInterval(() => this.refreshControlStatus(), CONTROL_POLL_INTERVAL_MS);
  }

  ngOnDestroy(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
    if (this.currentPollHandle) clearInterval(this.currentPollHandle);
    if (this.controlPollHandle) clearInterval(this.controlPollHandle);
  }

  refreshControlStatus(): void {
    this.http.get<{ running: boolean }>(`${LAB_CONTROL_BASE}/control/status`).subscribe({
      next: (s) => { this.controlAvailable = true; this.controlRunning = s.running; },
      error: () => { this.controlAvailable = false; },
    });
  }

  startLab(): void {
    if (this.controlBusy) return;
    this.controlBusy = true;
    this.http.post(`${LAB_CONTROL_BASE}/control/start`, {}).subscribe({
      next: () => { this.controlBusy = false; this.refreshControlStatus(); },
      error: () => { this.controlBusy = false; this.refreshControlStatus(); },
    });
  }

  stopLab(): void {
    if (this.controlBusy) return;
    if (!confirm('¿Detener el laboratorio? Va a dejar de buscar estrategias nuevas hasta que lo vuelvas a arrancar.')) return;
    this.controlBusy = true;
    this.http.post(`${LAB_CONTROL_BASE}/control/stop`, {}).subscribe({
      next: () => { this.controlBusy = false; this.refreshControlStatus(); },
      error: () => { this.controlBusy = false; this.refreshControlStatus(); },
    });
  }

  // Entry types con scan real conectado en produccion -- "Crear Estrategia"
  // solo aparece para estos (ver lab_control_server.py::/control/deploy).
  private static readonly DEPLOYABLE_TYPES = new Set(['level_sweep', 'band_touch', 'rsi_extreme', 'ma_pullback']);
  deployingKey: string | null = null;

  canDeploy(row: StrategyRow): boolean {
    const et = row.strat.entry_type;
    if (!StrategyLabComponent.DEPLOYABLE_TYPES.has(et)) return false;
    // level_sweep/band_touch son SHORT-unicamente en produccion real.
    if ((et === 'level_sweep' || et === 'band_touch') && row.strat.side !== 'SHORT') return false;
    return true;
  }

  deployStrategy(row: StrategyRow): void {
    const key = this.trackByRow(0, row);
    if (this.deployingKey) return;
    const name = prompt('Nombre para la nueva estrategia:', `${this.labelFor(row.strat)} ${row.strat.tf_min}m ${row.strat.side} (evolutivo)`);
    if (!name) return;
    if (!confirm(`¿Crear "${name}" en producción, ACTIVA de una? Va a empezar a operar con capital real apenas encuentre una señal.`)) return;
    this.deployingKey = key;
    this.http.post<{ ok: boolean; id: string; name: string }>(`${LAB_CONTROL_BASE}/control/deploy`, {
      strat: row.strat, result: row.result, name,
    }).subscribe({
      next: (r) => {
        this.deployingKey = null;
        alert(`Creada: "${r.name}" -- ya está activa en Estrategias.`);
      },
      error: (err) => {
        this.deployingKey = null;
        const detail = err?.error?.detail || 'Error desconocido';
        alert(`No se pudo crear la estrategia: ${detail}`);
      },
    });
  }

  refresh(): void {
    this.http.get<LabStatus>(`${LAB_API_BASE}/lab/status`).subscribe({
      next: (s) => { this.status = s; this.loading = false; this.error = null; },
      error: () => { this.error = 'No se pudo conectar al laboratorio (¿está corriendo el servicio de backtest en :8010?)'; this.loading = false; },
    });
    this.http.get<{ strategies: StrategyRow[] }>(`${LAB_API_BASE}/lab/strategies/found`).subscribe({
      next: (r) => { this.found = r.strategies || []; },
      error: () => {},
    });
    this.http.get<{ strategies: StrategyRow[] }>(`${LAB_API_BASE}/lab/strategies/top?limit=150`).subscribe({
      next: (r) => { this.topAll = r.strategies || []; },
      error: () => {},
    });
    this.http.get<{ strategies: StrategyRow[] }>(`${LAB_API_BASE}/lab/strategies/top?limit=10`).subscribe({
      next: (r) => { this.top10 = r.strategies || []; },
      error: () => {},
    });
  }

  refreshCurrent(): void {
    this.http.get<LabCurrent>(`${LAB_API_BASE}/lab/current`).subscribe({
      next: (c) => { this.current = c; },
      error: () => { this.current = null; },
    });
  }

  openTop10(): void { this.showTop10 = true; }
  closeTop10(): void { this.showTop10 = false; }

  get activeList(): StrategyRow[] {
    let list = this.viewMode === 'found' ? this.found : this.topAll;
    if (this.filterEntryType) list = list.filter(r => r.strat.entry_type === this.filterEntryType);
    if (this.filterSide) list = list.filter(r => r.strat.side === this.filterSide);
    const key = this.sortKey;
    const dir = this.sortDir;
    return [...list].sort((a, b) => (((a.result as any)[key] ?? -Infinity) - ((b.result as any)[key] ?? -Infinity)) * dir);
  }

  get best(): StrategyRow | null {
    return this.found.length ? this.found[0] : null;
  }

  get progressPercent(): number {
    if (!this.status?.testedCount) return 0;
    // sin techo real conocido (el lab corre infinito) -- solo referencia visual del ritmo de hallazgo
    return Math.min(100, (this.status.foundCount / Math.max(1, this.status.testedCount)) * 100 * 40);
  }

  setSort(key: SortKey): void {
    if (this.sortKey === key) { this.sortDir = this.sortDir === -1 ? 1 : -1; }
    else { this.sortKey = key; this.sortDir = -1; }
  }

  toggleExpand(i: number): void {
    this.expandedIndex = this.expandedIndex === i ? null : i;
  }

  labelFor(strat: StrategyDef): string {
    return this.entryTypeLabel[strat.entry_type] || strat.entry_type;
  }

  fmtMoney(v: number | undefined | null): string {
    if (v === undefined || v === null) return '—';
    const sign = v >= 0 ? '+' : '';
    return `${sign}$${v.toFixed(2)}`;
  }

  trackByRow(_i: number, row: StrategyRow): string {
    return `${row.strat.entry_type}-${row.strat.tf_min}-${row.strat.side}-${row.strat.atr_sl_mult}-${row.strat.rr_mult}-${row.strat.lookback}-${row.ts}`;
  }
}
