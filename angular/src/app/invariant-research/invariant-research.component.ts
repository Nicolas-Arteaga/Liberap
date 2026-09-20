import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { IonIcon } from '@ionic/angular/standalone';

// La UI habla con el dev-server; éste reenvía /vire-api al backtest :8010.
// Evita depender de CORS o de que el navegador permita un puerto local distinto.
const API = '/vire-api';
interface TradeDiagnostics { attribution_scope?: string; count?: number; by_exit?: Record<string, { trades?: number; wins?: number; losses?: number; pnl?: number }>; trades?: Array<{ entry_time_ms?: number; exit_time_ms?: number; side?: string; reason?: string; mfe?: number; mae?: number; pnl?: number }>; }
interface Candidate { symbol_a: string; symbol_b: string; status: string; relationship: any; policy: any; train: any; validation: any; oos: any; stressed_oos: any; rejection_reasons: string[]; trade_diagnostics?: { validation?: TradeDiagnostics; oos?: TradeDiagnostics }; }
interface Coverage { available: boolean; symbols?: number; rows?: number; role: string; universe_sufficient?: boolean; }
interface Run { run_id: string; created_at: string; summary: { pairs_screened: number; relationships_eligible: number; paper_ready: number; universe_symbols?: number; universe_symbols_represented?: number }; candidates?: Candidate[]; data_coverage?: { price: Coverage; funding: Coverage; open_interest: Coverage; liquidations: Coverage }; promotion_policy?: { paper_ready_allowed: boolean; reason: string }; }

@Component({ selector: 'app-invariant-research', standalone: true, imports: [CommonModule, FormsModule, IonIcon], templateUrl: './invariant-research.component.html', styleUrls: ['./invariant-research.component.scss'] })
export class InvariantResearchComponent implements OnInit, OnDestroy {
  private http = inject(HttpClient); private poll: ReturnType<typeof setInterval> | null = null; jobId = ''; running = false; error = '';
  startDate = '2025-12-01'; endDate = new Date().toISOString().slice(0, 10); maxPairs = 80; minOosTrades = 8; runs: Run[] = []; researchStrategies: any[] = []; fundingRuns: any[] = []; oiRuns: any[] = []; forcedFlowRuns: any[] = []; crossVenueRuns: any[] = []; liquidationRuns: any[] = []; executionAudit: any = null; liquidationEligibility: any = null; selected: Run | null = null; inspectedCandidate: Candidate | null = null; inspectedResearchStrategy: any = null;
  ngOnInit() { this.loadRuns(); this.loadResearchStrategies(); this.loadFundingRuns(); this.loadOiRuns(); this.loadForcedFlowRuns(); this.loadCrossVenueRuns(); this.loadLiquidationRuns(); this.loadExecutionAudit(); this.loadLiquidationEligibility(); }
  ngOnDestroy() { if (this.poll) clearInterval(this.poll); }
  run() {
    this.error = ''; this.running = true;
    this.http.post<{jobId:string}>(`${API}/research/invariants/run`, { startDate: this.startDate, endDate: this.endDate, maxPairs: this.maxPairs, minOosTrades: this.minOosTrades }).subscribe({
      next: r => { this.jobId = r.jobId; this.poll = setInterval(() => this.check(), 1500); }, error: () => { this.running = false; this.error = 'No se pudo iniciar VIRE. Verificá el contenedor backtest.'; }
    });
  }
  check() { this.http.get<any>(`${API}/backtest/status/${this.jobId}`).subscribe({ next: s => { if (s.status === 'completed') { if (this.poll) clearInterval(this.poll); this.running = false; this.loadRuns(true); this.loadResearchStrategies(); } if (s.status === 'failed') { if (this.poll) clearInterval(this.poll); this.running = false; this.error = s.error || 'La investigación falló.'; }}, error: () => { this.running = false; this.error = 'Se perdió conexión con VIRE.'; }}); }
  loadRuns(selectLatest = false) { this.http.get<{runs:Run[]}>(`${API}/research/invariants/runs`).subscribe({ next: r => { this.runs = r.runs; if (selectLatest && r.runs[0]) this.open(r.runs[0]); }, error: () => this.error = 'No se pudo leer el ledger de investigación.' }); }
  loadResearchStrategies() { this.http.get<{strategies:any[]}>(`${API}/research/strategies`).subscribe({ next: r => this.researchStrategies = r.strategies, error: () => {} }); }
  private versioned(runs: any[]) { return runs.filter(run => String(run.strategy?.id || '').startsWith('vire:')); }
  loadFundingRuns() { this.http.get<{runs:any[]}>(`${API}/research/funding/runs`).subscribe({ next: r => this.fundingRuns = this.versioned(r.runs), error: () => {} }); }
  loadOiRuns() { this.http.get<{runs:any[]}>(`${API}/research/oi/runs`).subscribe({ next: r => this.oiRuns = this.versioned(r.runs), error: () => {} }); }
  loadForcedFlowRuns() { this.http.get<{runs:any[]}>(`${API}/research/forced-flow/runs`).subscribe({ next: r => this.forcedFlowRuns = this.versioned(r.runs), error: () => {} }); }
  loadCrossVenueRuns() { this.http.get<{runs:any[]}>(`${API}/research/cross-venue/runs`).subscribe({ next: r => this.crossVenueRuns = this.versioned(r.runs), error: () => {} }); }
  loadLiquidationRuns() { this.http.get<{runs:any[]}>(`${API}/research/liquidations/runs`).subscribe({ next: r => this.liquidationRuns = r.runs, error: () => {} }); }
  loadExecutionAudit() { this.http.get<any>(`${API}/research/execution-audit`).subscribe({ next: r => this.executionAudit = r, error: () => {} }); }
  loadLiquidationEligibility() { this.http.get<any>(`${API}/research/liquidations/eligibility`).subscribe({ next: r => this.liquidationEligibility = r, error: () => {} }); }
  open(run: Run) { this.http.get<Run>(`${API}/research/invariants/runs/${run.run_id}`).subscribe({ next: r => { this.selected = r; this.inspectedCandidate = null; }, error: () => this.error = 'No se pudo cargar la corrida.' }); }
  inspect(candidate: Candidate) { this.inspectedCandidate = this.inspectedCandidate === candidate ? null : candidate; }
  inspectResearch(strategy: any) {
    if (this.inspectedResearchStrategy?.strategy_id === strategy.strategy_id) { this.inspectedResearchStrategy = null; return; }
    this.http.get<any>(`${API}/research/strategies/${encodeURIComponent(strategy.strategy_id)}`).subscribe({
      next: detail => this.inspectedResearchStrategy = detail,
      error: () => this.error = 'No se pudo cargar la evidencia de esta hipótesis.'
    });
  }
  date(ms: number | null | undefined) { return ms ? new Date(ms).toLocaleString('es-AR') : '—'; }
  money(v: number) { return `${v >= 0 ? '+' : ''}$${(v || 0).toFixed(2)}`; }
}
