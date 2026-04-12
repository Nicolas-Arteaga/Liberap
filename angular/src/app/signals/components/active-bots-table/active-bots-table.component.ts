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
            <!-- Iteramos sobre pares configurados en el bot -->
            <tr *ngFor="let pair of (pollService.status$ | async)?.activePairs; let i = index" 
                [class.selected]="(pollService.selectedPair$ | async) === pair">
              <td class="name-cell">Bot #{{ i + 1 }}</td>
              <td>{{ pair.replace('/USDT:USDT', 'USDT').replace('/', '') }}</td>
              <td>
                <ng-container *ngIf="getTradeForPair(pair) as trade; else scanning">
                  <span class="type-badge" [class.long]="!trade.isShort" [class.short]="trade.isShort">
                    {{ trade.isShort ? 'SHORT' : 'LONG' }}
                  </span>
                </ng-container>
                <ng-template #scanning>-</ng-template>
              </td>
              <td>
                <ng-container *ngIf="getTradeForPair(pair) as trade; else scanningStatus">
                  <span class="status-badge open">IN TRADE</span>
                </ng-container>
                <ng-template #scanningStatus>
                  <span class="status-badge scanning">SCANNING</span>
                </ng-template>
              </td>
              <td class="pnl-cell" [class.positive]="getTradeForPair(pair)?.pnl >= 0" [class.negative]="getTradeForPair(pair)?.pnl < 0">
                <ng-container *ngIf="getTradeForPair(pair) as trade; else scanningPnl">
                  {{ trade.pnl >= 0 ? '+' : '' }}{{ trade.pnl | number:'1.2-2' }} USDT
                </ng-container>
                <ng-template #scanningPnl>0.00 USDT</ng-template>
              </td>
              <td class="actions-cell">
                <button class="btn-ver" (click)="viewPair(pair)">Analizar</button>
                <button *ngIf="getTradeForPair(pair) as trade" class="btn-action btn-stop" (click)="closeTrade(trade.id)">Cerrar</button>
              </td>
            </tr>

            <tr *ngIf="!(pollService.status$ | async)?.activePairs?.length">
              <td colspan="6" class="text-center text-muted" style="padding: 40px;">
                <div class="empty-trades">
                  <span class="d-block mb-1">Cero bots configurados.</span>
                  <span class="text-xxs">Agregue una moneda para comenzar.</span>
                </div>
              </td>
            </tr>
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

    .type-badge {
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
      &.long { background: rgba(34, 197, 94, 0.1); color: #22c55e; }
      &.short { background: rgba(239, 68, 68, 0.1); color: #ef4444; }
    }

    .status-badge {
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 800;
      &.open { background: #3b82f6; color: white; }
      &.scanning { background: rgba(255, 255, 255, 0.05); color: #8b949e; border: 1px solid rgba(255, 255, 255, 0.1); }
    }

    .pnl-cell {
      font-weight: 600;
      font-size: 14px;
      &.positive { color: #22c55e; }
      &.negative { color: #ef4444; }
    }
    
    .empty-trades {
      opacity: 0.6;
      .text-xxs { font-size: 10px; color: #8b949e; }
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
        
        &.btn-stop { background: #ef4444; color: #fff; }
        &.btn-stop:hover { filter: brightness(1.1); }
      }
    }
  `]
})
export class ActiveBotsTableComponent {
  public pollService = inject(FreqtradePollService);
  private freqtradeService = inject(FreqtradeService);
  private toaster = inject(ToasterService);

  private openTrades: any[] = [];

  constructor() {
    this.pollService.openTrades$.subscribe(t => this.openTrades = t || []);
  }

  getTradeForPair(pair: string) {
    const base = pair.replace('/', '').split(':')[0];
    return this.openTrades.find(t => t.pair === base);
  }

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
