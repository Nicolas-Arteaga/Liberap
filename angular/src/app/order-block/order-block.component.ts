import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { OrderBlockService } from '../proxy/trading/order-block/order-block.service';
import { ObAnalyzeResponseDto, ObScanItemDto, ObZoneDto } from '../proxy/trading/order-block/models';
import { VolatileSymbolsService } from '../shared/services/volatile-symbols.service';

@Component({
  selector: 'app-order-block',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="ob-page">
      <div class="ob-header">
        <h2>Order Block + BOS + Liquidez</h2>
        <p class="ob-subtitle">
          Concepto SMC/ICT: última vela opuesta antes de un quiebre de estructura (BOS), TP en el
          próximo nivel de liquidez real, filtrado por confluencia con POC/HVN de volumen.
          <strong>Solo SHORT (bearish) está validado</strong> por backtest real (n=3272, WR 29.4%,
          $92.26/mes, estable entre mitades) — LONG se muestra a título informativo, no operar todavía.
        </p>
      </div>

      <div class="ob-controls">
        <input [(ngModel)]="symbol" placeholder="Símbolo (ej. BTCUSDT)" (keyup.enter)="analyze()" />
        <select [(ngModel)]="interval">
          <option value="15m">15m</option>
          <option value="5m">5m</option>
          <option value="1h">1h</option>
        </select>
        <button (click)="analyze()" [disabled]="loadingAnalyze">
          {{ loadingAnalyze ? 'Analizando...' : 'Analizar símbolo' }}
        </button>
        <button (click)="runTopScan()" [disabled]="loadingScan" class="scan-btn">
          {{ loadingScan ? 'Escaneando...' : 'Escanear Top 5 (SHORT validado)' }}
        </button>
        <label class="only-validated-toggle">
          <input type="checkbox" [(ngModel)]="onlyValidated" (change)="runTopScan()" />
          Solo SHORT validado
        </label>
      </div>

      <div *ngIf="analyzeError" class="ob-error">{{ analyzeError }}</div>

      <div *ngIf="analyzeResult" class="ob-block">
        <h3>{{ analyzeResult.symbol }} — precio actual: {{ analyzeResult.currentPrice }}</h3>
        <table class="ob-table" *ngIf="analyzeResult.zones?.length; else noZones">
          <thead>
            <tr>
              <th>Dirección</th><th>Estado</th><th>Top</th><th>Bottom</th><th>Dist. entrada %</th>
              <th>POC</th><th>SL</th><th>TP</th><th>Dist. TP %</th><th>Score</th><th>Validado</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let z of analyzeResult.zones" [class.bearish]="z.direction === 'bearish'" [class.bullish]="z.direction === 'bullish'">
              <td>{{ dirLabel(z.direction) }}</td>
              <td>{{ z.entryStatus }}</td>
              <td>{{ z.top }}</td>
              <td>{{ z.bottom }}</td>
              <td>{{ z.distToEntryPct }}%</td>
              <td>{{ z.pocConfluence ? 'Sí' : 'No' }} ({{ z.pocDistancePct }}%)</td>
              <td>{{ z.slPrice }}</td>
              <td>{{ z.tpPrice }}</td>
              <td>{{ z.tpDistancePct }}%</td>
              <td>{{ z.confluenceScore }}</td>
              <td>{{ z.validatedStable ? '✅' : '⚠️ no validado' }}</td>
            </tr>
          </tbody>
        </table>
        <ng-template #noZones><p>Sin Order Blocks pendientes de mitigar para este símbolo.</p></ng-template>
      </div>

      <div *ngIf="scanError" class="ob-error">{{ scanError }}</div>

      <div *ngIf="scanTop5.length" class="ob-block">
        <h3>Top {{ scanTop5.length }} accionables (de {{ scannedCount }} escaneados, {{ actionableCount }} accionables)</h3>
        <table class="ob-table">
          <thead>
            <tr>
              <th>#</th><th>Símbolo</th><th>Dirección</th><th>Estado</th><th>Precio</th>
              <th>POC</th><th>SL</th><th>TP</th><th>Dist. TP %</th><th>Score</th><th>Validado</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let item of scanTop5; let i = index" [class.bearish]="item.direction === 'bearish'" [class.bullish]="item.direction === 'bullish'">
              <td>{{ i + 1 }}</td>
              <td>{{ item.symbol }}</td>
              <td>{{ dirLabel(item.direction) }}</td>
              <td>{{ item.entryStatus }}</td>
              <td>{{ item.currentPrice }}</td>
              <td>{{ item.pocConfluence ? 'Sí' : 'No' }}</td>
              <td>{{ item.slPrice }}</td>
              <td>{{ item.tpPrice }}</td>
              <td>{{ item.tpDistancePct }}%</td>
              <td>{{ item.confluenceScore }}</td>
              <td>{{ item.validatedStable ? '✅' : '⚠️' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `,
  styles: [`
    .ob-page { padding: 20px; max-width: 1200px; margin: 0 auto; }
    .ob-header h2 { margin-bottom: 4px; }
    .ob-subtitle { color: #888; font-size: 0.85rem; max-width: 900px; }
    .ob-controls { display: flex; gap: 10px; align-items: center; margin: 16px 0; flex-wrap: wrap; }
    .ob-controls input[type=text], .ob-controls input:not([type]) { padding: 6px 10px; }
    .ob-controls select { padding: 6px; }
    .ob-controls button { padding: 6px 14px; cursor: pointer; }
    .scan-btn { background: #2b6cb0; color: white; border: none; border-radius: 4px; }
    .only-validated-toggle { font-size: 0.85rem; display: flex; align-items: center; gap: 4px; }
    .ob-error { color: #e53e3e; margin: 10px 0; }
    .ob-block { margin-top: 24px; }
    .ob-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    .ob-table th, .ob-table td { border: 1px solid #444; padding: 6px 8px; text-align: center; }
    .ob-table tr.bearish { background: rgba(229, 62, 62, 0.08); }
    .ob-table tr.bullish { background: rgba(56, 161, 105, 0.08); }
  `],
})
export class OrderBlockComponent {
  private obSvc = inject(OrderBlockService);
  private volatileSvc = inject(VolatileSymbolsService);

  symbol = 'BTCUSDT';
  interval = '15m';
  onlyValidated = true;

  loadingAnalyze = false;
  loadingScan = false;
  analyzeError = '';
  scanError = '';

  analyzeResult: ObAnalyzeResponseDto | null = null;
  scanTop5: ObScanItemDto[] = [];
  scannedCount = 0;
  actionableCount = 0;

  dirLabel(direction?: string): string {
    if (direction === 'bearish') return 'SHORT (bearish)';
    if (direction === 'bullish') return 'LONG (bullish)';
    return direction ?? '';
  }

  analyze() {
    if (!this.symbol.trim()) return;
    this.loadingAnalyze = true;
    this.analyzeError = '';
    this.analyzeResult = null;
    const cleanSymbol = this.symbol.trim().toUpperCase();
    this.obSvc.analyzeOnDemand(cleanSymbol, this.interval).subscribe({
      next: (res) => {
        this.analyzeResult = res;
        this.loadingAnalyze = false;
      },
      error: (err) => {
        this.analyzeError = 'No se pudo analizar el símbolo: ' + (err?.error?.error?.message ?? err?.message ?? 'error desconocido');
        this.loadingAnalyze = false;
      },
    });
  }

  async runTopScan() {
    this.loadingScan = true;
    this.scanError = '';
    this.scanTop5 = [];
    try {
      const symbols = await this.volatileSvc.getMostVolatile(80);
      this.obSvc.scan(symbols, this.interval, this.onlyValidated).subscribe({
        next: (res) => {
          this.scanTop5 = res.top5 ?? [];
          this.scannedCount = res.scannedCount ?? symbols.length;
          this.actionableCount = res.actionableCount ?? 0;
          this.loadingScan = false;
        },
        error: (err) => {
          this.scanError = 'No se pudo escanear: ' + (err?.error?.error?.message ?? err?.message ?? 'error desconocido');
          this.loadingScan = false;
        },
      });
    } catch (e: any) {
      this.scanError = 'No se pudo obtener la lista de símbolos: ' + e?.message;
      this.loadingScan = false;
    }
  }
}
