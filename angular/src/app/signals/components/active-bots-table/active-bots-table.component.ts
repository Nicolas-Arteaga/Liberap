import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FreqtradePollService } from '../../../services/freqtrade-poll.service';
import { FreqtradeService } from '../../../proxy/freqtrade/freqtrade.service';
import { ToasterService } from '@abp/ng.theme.shared';

@Component({
  selector: 'app-active-bots-table',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="active-bots-container">
      <h3>Bots Activos (Trades en Freqtrade)</h3>
      
      <div class="table-responsive">
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Par</th>
              <th>Tipo</th>
              <th>Estado</th>
              <th>PnL</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            <!-- Real Open Trades List -->
            <tr *ngFor="let trade of pollService.openTrades$ | async; let i = index" 
                [class.selected]="(pollService.selectedTradeId$ | async) === trade.id || (pollService.selectedPair$ | async) === trade.pair">
              <td class="name-cell">Trade Abierto #{{ trade.id }}</td>
              <td>{{ trade.pair.replace('/USDT:USDT', 'USDT') }}</td>
              <td>Posición Activa</td>
              <td>
                <span class="status-text running">Open</span>
              </td>
              <td class="pnl-cell" [class.positive]="trade.pnl >= 0" [class.negative]="trade.pnl < 0">
                {{ trade.pnl >= 0 ? '+' : '' }}{{ trade.pnl | number:'1.2-2' }}$
              </td>
              <td class="actions-cell">
                <button class="btn-ver" (click)="viewTrade(trade.id, trade.pair)">Ver</button>
                <button class="btn-action btn-stop" (click)="closeTrade(trade.id)">Cerrar</button>
              </td>
            </tr>

            <!-- Standby Motor Rows for each active pair -->
            <ng-container *ngIf="pollService.status$ | async as status">
              <tr *ngFor="let pair of status.activePairs" 
                  [class.selected]="(pollService.selectedPair$ | async) === pair && !(pollService.selectedTradeId$ | async)">
                <td class="name-cell">Motor Scanner</td>
                <td>{{ pair.replace('/USDT:USDT', 'USDT') }}</td>
                <td>FreqAI Scanner</td>
                <td>
                  <span class="status-text" [class.running]="status.isRunning" [class.paused]="!status.isRunning">
                    {{ status.isRunning ? 'Analizando...' : 'Detenido' }}
                  </span>
                </td>
                <td class="pnl-cell text-muted">0.00$</td>
                <td class="actions-cell">
                   <button class="btn-ver" (click)="viewPair(pair)">Ver</button>
                </td>
              </tr>
              <tr *ngIf="status.activePairs.length === 0 && (pollService.openTrades$ | async)?.length === 0">
                <td colspan="6" class="text-center text-muted" style="padding: 20px;">No hay bots configurados.</td>
              </tr>
            </ng-container>
          </tbody>
        </table>
      </div>
    </div>
  `,
  styles: [`
    .active-bots-container {
      background: #11141d;
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      padding: 16px;
      margin-top: 20px;
    }

    h3 { margin-bottom: 16px; font-size: 16px; font-weight: 700; color: #f0f6fc; }

    .table-responsive { width: 100%; overflow-x: auto; }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      color: #8b949e;
      
      th { text-align: left; padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.05); font-weight: 500; font-size: 12px; }
      td { padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.03); color: #e2e8f0; }
      
      tr {
        transition: all 0.2s;
        &:hover { background: rgba(255, 255, 255, 0.02); }
        &.selected { background: rgba(59, 130, 246, 0.08); border-left: 2px solid #3b82f6; }
      }
    }

    .name-cell { font-weight: 600; color: #f0f6fc; }

    .status-text {
      font-weight: 600;
      &.running { color: #22c55e; }
      &.paused { color: #ef4444; }
      &.stopped { color: #8b949e; }
    }

    .pnl-cell {
      font-weight: 600;
      font-size: 14px;
      &.positive { color: #22c55e; }
      &.negative { color: #ef4444; }
    }
    
    .text-muted { color: #8b949e !important; }

    .actions-cell {
      display: flex;
      gap: 8px;
      
      button {
        padding: 6px 16px;
        border: none;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        
        &.btn-ver { background: #1c2230; color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.3); }
        &.btn-ver:hover { background: rgba(59, 130, 246, 0.1); }
        
        &.btn-stop { background: #eab308; color: #000; } /* yellow stop */
        &.btn-stop:hover { filter: brightness(1.1); }
        
        &.btn-resume { background: #1c2230; border: 1px solid rgba(255,255,255,0.1); color: #22c55e; }
        &.btn-resume:hover { background: rgba(34, 197, 94, 0.1); border-color: rgba(34, 197, 94, 0.3); }
      }
    }
  `]
})
export class ActiveBotsTableComponent {
  public pollService = inject(FreqtradePollService);
  private freqtradeService = inject(FreqtradeService);
  private toaster = inject(ToasterService);

  viewTrade(id: number, pair: string) {
    this.pollService.selectTrade(id);
    this.pollService.selectPair(pair);
  }

  viewPair(pair: string) {
    this.pollService.selectedTradeId$.next(null); // Deseleccionar trade si vemos el scanner
    this.pollService.selectPair(pair);
    this.toaster.info(`Viendo control para ${pair.replace('/USDT:USDT', 'USDT')}`);
  }

  closeTrade(id: number) {
    if (confirm(`¿Cerrar trade #${id} manualmente?`)) {
      this.freqtradeService.closeTrade(id.toString()).subscribe(() => {
        this.toaster.success('Trade cerrado exitosamente.');
        this.pollService.refresh();
      });
    }
  }

  viewMotor() {
    this.pollService.clearSelection();
    this.toaster.info('Motor principal seleccionado en Panel de Control.');
  }

  pauseMotor() {
    this.freqtradeService.stopBot().subscribe({
      next: () => {
        this.toaster.success('Motor pausado correctamente.');
        this.pollService.refresh();
      }
    });
  }
}
