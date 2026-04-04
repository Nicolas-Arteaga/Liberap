import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FreqtradePollService } from '../../../services/freqtrade-poll.service';
import { FreqtradeService } from '../../../proxy/freqtrade/freqtrade.service';

@Component({
  selector: 'app-active-bots-table',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="active-bots-container">
      <h3>Bots Activos</h3>
      
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
            <!-- Main Motor Status Row -->
            <tr *ngIf="pollService.status$ | async as status">
              <td class="name-cell">Motor Principal</td>
              <td>{{ status.currentPair !== 'No configurado' ? status.currentPair : '--' }}</td>
              <td>VergeFreqAI</td>
              <td>
                <span class="status-badge" [class.running]="status.isRunning" [class.stopped]="!status.isRunning">
                  {{ status.isRunning ? 'RUNNING' : 'STOPPED' }}
                </span>
              </td>
              <td class="pnl-cell text-muted">
                {{ status.isRunning ? 'Analizando...' : '--' }}
              </td>
              <td class="actions-cell">
                <button class="btn-ver" [disabled]="true">
                  <span class="icon">ℹ️</span> System
                </button>
              </td>
            </tr>

            <!-- Open Trades List -->
            <tr *ngFor="let trade of pollService.openTrades$ | async">
              <td class="name-cell">Trade #{{ trade.id }}</td>
              <td>{{ trade.pair }}</td>
              <td>Posición O.</td>
              <td>
                <span class="status-badge running">
                  OPEN
                </span>
              </td>
              <td class="pnl-cell" [class.positive]="trade.pnl >= 0" [class.negative]="trade.pnl < 0">
                {{ trade.pnl >= 0 ? '+' : '' }}{{ trade.pnl | number:'1.2-2' }}$
              </td>
              <td class="actions-cell">
                <button class="btn-stop" (click)="$event.stopPropagation(); closeTrade(trade.id)">
                  <span class="icon">⏹</span> Cerrar
                </button>
              </td>
            </tr>
            
            <tr *ngIf="(pollService.openTrades$ | async)?.length === 0">
               <td colspan="6" class="text-center py-4" style="color: #4b5563;">(Aún no hay trades abiertos por el motor)</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `,
  styles: [`
    .active-bots-container {
      background: rgba(21, 26, 38, 0.4);
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
      
      th { text-align: left; padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.05); font-weight: 500; }
      td { padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.03); }
      
      tr {
        cursor: pointer;
        transition: all 0.2s;
        &:hover { background: rgba(255, 255, 255, 0.02); }
        &.selected { background: rgba(59, 130, 246, 0.1); border-left: 2px solid #3b82f6; }
      }
    }

    .name-cell { font-weight: 700; color: #f0f6fc; }

    .status-badge {
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 600;
      
      &.running { background: rgba(38, 166, 154, 0.1); color: #26a69a; }
      &.paused { background: rgba(245, 158, 11, 0.1); color: #f59e0b; }
      &.stopped { background: rgba(239, 68, 68, 0.1); color: #ef4444; }
    }

    .pnl-cell {
      font-weight: 600;
      &.positive { color: #26a69a; }
      &.negative { color: #ef4444; }
    }

    .actions-cell {
      display: flex;
      gap: 8px;
      
      button {
        padding: 4px 12px;
        border: none;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
        display: flex;
        align-items: center;
        gap: 4px;
        
        &.btn-ver { background: rgba(59, 130, 246, 0.1); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.2); }
        &.btn-stop { background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); }
        
        &:hover { filter: brightness(1.2); }
      }
    }
  `]
})
export class ActiveBotsTableComponent {
  public pollService = inject(FreqtradePollService);
  private freqtradeService = inject(FreqtradeService);

  closeTrade(id: number) {
    if (confirm(`¿Cerrar trade #${id} manualmente?`)) {
      this.freqtradeService.closeTrade(id.toString()).subscribe();
    }
  }
}
