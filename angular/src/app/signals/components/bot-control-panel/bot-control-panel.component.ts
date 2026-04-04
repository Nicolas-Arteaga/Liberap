import { Component, inject, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { chevronDownOutline, pauseOutline, stopOutline, closeCircleOutline } from 'ionicons/icons';
import { FreqtradePollService } from '../../../services/freqtrade-poll.service';
import { FreqtradeService } from '../../../proxy/freqtrade/freqtrade.service';
import { ToasterService } from '@abp/ng.theme.shared';

@Component({
  selector: 'app-bot-control-panel',
  standalone: true,
  imports: [CommonModule, IonIcon],
  template: `
    <div class="control-panel-container" *ngIf="selectedTrade; else emptyState">
      <div class="panel-header">
        <h3>TRADE CONTROL</h3>
        <ion-icon name="chevron-down-outline"></ion-icon>
      </div>

      <div class="status-row">
        <span class="label">Estado:</span>
        <span class="value success">OPEN</span>
      </div>

      <div class="position-card">
        <div class="pos-header">
          <span class="label">Posición en {{ selectedTrade.pair }}:</span>
        </div>
        <div class="pos-main">
          <span class="direction long">LONG</span>
          <span class="amount">{{ selectedTrade.amount | number:'1.4-4' }} Units</span>
        </div>
        <div class="pos-row">
          <span class="label">Entrada:</span>
          <span class="value">{{ selectedTrade.openRate | number:'1.2-5' }}</span>
        </div>
        <div class="pos-row">
          <span class="label">Actual:</span>
          <span class="value">{{ selectedTrade.currentRate | number:'1.2-5' }}</span>
        </div>
        <div class="pos-row">
          <span class="label">PnL:</span>
          <span class="value pnl" [class.positive]="selectedTrade.pnl >= 0" [class.negative]="selectedTrade.pnl < 0">
            {{ selectedTrade.pnl >= 0 ? '+' : '' }}{{ selectedTrade.pnl | number:'1.2-2' }} USDT
          </span>
        </div>
      </div>

      <div class="control-buttons full">
        <button class="btn-stop" (click)="closeTrade(selectedTrade.id)">
          <ion-icon name="stop-outline"></ion-icon>
          Cerrar Posición
        </button>
      </div>

      <div class="mini-list-section" *ngIf="(pollService.openTrades$ | async)?.length">
        <h3>Otros Trades</h3>
        <div class="mini-bot-item" *ngFor="let other of pollService.openTrades$ | async" (click)="selectedTrade = other">
          <span class="name">#{{ other.id }}</span>
          <span class="pair">{{ other.pair }}</span>
          <span class="status running">OPEN</span>
          <button class="btn-mini-stop" (click)="$event.stopPropagation(); closeTrade(other.id)">Close</button>
        </div>
      </div>
    </div>

    <ng-template #emptyState>
      <div class="control-panel-container empty" *ngIf="pollService.status$ | async as status">
        <ng-container *ngIf="status.isRunning; else completelyOffline">
          <div class="panel-header">
             <h3>MOTOR FREQTRADE</h3>
             <ion-icon name="pulse-outline" style="color: #22c55e;"></ion-icon>
          </div>
          
          <div class="position-card">
            <div class="pos-main">
              <span class="direction long">RUNNING</span>
              <span class="amount">{{ status.currentPair !== 'No configurado' ? status.currentPair : 'Esperando datos...' }}</span>
            </div>
            <p style="color: #8b949e; font-size: 13px;">El motor está encendido analizando el mercado con IA en este par.<br>Cuando ejecute una entrada, aparecerá aquí como un Trade Abierto.</p>
          </div>

          <div class="control-buttons full" style="margin-top: 10px;">
            <!-- Not calling endpoint directly here for simplicity, reusing the UI style -->
            <button class="btn-stop" style="opacity: 0.5; cursor: not-allowed;" title="Detener el motor (Disponible pronto)">
              <ion-icon name="stop-outline"></ion-icon>
              Parar Motor
            </button>
          </div>
        </ng-container>

        <ng-template #completelyOffline>
           <p style="color: #8b949e; text-align: center; margin-top: 40px;">No hay bots activos. Inicia un bot desde el panel izquierdo.</p>
        </ng-template>
      </div>
    </ng-template>
  `,
  styles: [`
    .control-panel-container {
      background: rgba(21, 26, 38, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 16px;
      padding: 20px;
      color: white;
      height: 100%;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      h3 { margin: 0; font-size: 14px; font-weight: 700; color: #8b949e; letter-spacing: 0.5px; }
      ion-icon { color: #8b949e; }
    }

    .status-row {
      display: flex;
      gap: 8px;
      font-size: 14px;
      .label { color: #8b949e; }
      .value.success { color: #22c55e; }
    }

    .position-card {
      background: rgba(255, 255, 255, 0.03);
      border-radius: 12px;
      padding: 16px;
      border: 1px solid rgba(255, 255, 255, 0.05);

      .pos-header { margin-bottom: 12px; .label { color: #8b949e; font-size: 13px; } }
      .pos-main {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
        
        .direction {
          font-size: 18px;
          font-weight: 800;
          &.long { color: #22c55e; }
          &.short { color: #ef4444; }
        }
        .amount { font-size: 16px; font-weight: 600; color: #f0f6fc; }
      }
      
      .pos-row {
        display: flex;
        justify-content: space-between;
        margin-bottom: 8px;
        font-size: 13px;
        .label { color: #8b949e; }
        .value { color: #f0f6fc; font-weight: 500; }
        .pnl { font-weight: 700; &.positive { color: #22c55e; } &.negative { color: #ef4444; } }
      }
    }

    .control-buttons {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      
      button {
        padding: 10px;
        border: none;
        border-radius: 8px;
        font-weight: 700;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        transition: all 0.2s;
        
        &.btn-pause { background: #f59e0b; color: #000; }
        &.btn-stop { background: #ef4444; color: #fff; }
        &:hover { filter: brightness(1.1); }
      }
    }

    .btn-close-pos {
      width: 100%;
      background: #161b22;
      border: 1px solid #30363d;
      color: #8b949e;
      padding: 12px;
      border-radius: 8px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      &:hover { background: #21262d; border-color: #8b949e; }
    }

    .mini-list-section {
      margin-top: auto;
      h3 { font-size: 14px; color: #f0f6fc; margin-bottom: 12px; }
      
      .mini-bot-item {
        background: rgba(255, 255, 255, 0.02);
        padding: 10px;
        border-radius: 8px;
        margin-bottom: 8px;
        display: grid;
        grid-template-columns: 1.5fr 1.5fr 1fr 1fr;
        align-items: center;
        font-size: 12px;
        cursor: pointer;
        
        .name { color: #f0f6fc; font-weight: 600; }
        .pair { color: #8b949e; }
        .status { &.running { color: #22c55e; } &.paused { color: #f59e0b; } &.stopped { color: #ef4444; } }
        .btn-mini-stop { background: none; border: none; color: #ef4444; text-decoration: underline; cursor: pointer; }
        
        &:hover { background: rgba(255, 255, 255, 0.05); }
      }
    }
  `]
})
export class BotControlPanelComponent {
  public pollService = inject(FreqtradePollService);
  private freqtradeService = inject(FreqtradeService);
  private toaster = inject(ToasterService);

  selectedTrade: any = null;

  constructor() {
    addIcons({ chevronDownOutline, pauseOutline, stopOutline, closeCircleOutline });
    
    // Auto-select first trade if none selected
    this.pollService.openTrades$.subscribe(trades => {
      if (trades.length > 0 && !this.selectedTrade) {
        this.selectedTrade = trades[0];
      } else if (trades.length === 0) {
        this.selectedTrade = null;
      }
    });
  }

  closeTrade(id: number) {
    if (confirm(`¿Cerrar trade #${id} en el exchange?`)) {
      this.freqtradeService.closeTrade(id.toString()).subscribe(() => {
        this.toaster.success('Trade cerrado exitosamente.');
      });
    }
  }
}
