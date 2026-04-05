import { Component, inject, OnInit, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { chevronDownOutline, pauseOutline, stopOutline, closeCircleOutline } from 'ionicons/icons';
import { FreqtradePollService } from '../../../services/freqtrade-poll.service';
import { FreqtradeService } from '../../../proxy/freqtrade/freqtrade.service';
import { ToasterService } from '@abp/ng.theme.shared';
import { BotSignalRService } from '../../services/bot-signalr.service';
import { FreqtradeTradeDto } from '../../../proxy/freqtrade/models';
import { combineLatest } from 'rxjs';
import { map } from 'rxjs/operators';

@Component({
  selector: 'app-bot-control-panel',
  standalone: true,
  imports: [CommonModule, FormsModule, IonIcon],
  template: `
    <!-- MAIN BOT CONTROL PANEL -->
    <div class="control-panel-container" *ngIf="pollService.status$ | async as status">
      <div class="panel-header d-flex align-items-center justify-content-between mb-3">
        <h3 class="m-0">BOT CONTROL</h3>
        
        <!-- Premium Custom Dropdown Selector -->
        <div class="custom-pair-selector-root position-relative" *ngIf="status.activePairs.length > 0">
          <div class="selected-pair-display d-flex align-items-center gap-2" (click)="showPairSelector = !showPairSelector">
             <span class="status-dot" [class.running]="status.isRunning"></span>
             <span class="pair-name fw-bold">{{ selectedPairForControl.replace('/USDT:USDT', 'USDT') }}</span>
             <ion-icon name="chevron-down-outline" class="ms-1"></ion-icon>
          </div>
          
          <div class="pair-dropdown-menu shadow-xl fade-in" *ngIf="showPairSelector">
             <div class="pair-option d-flex align-items-center gap-3" 
                  *ngFor="let p of status.activePairs"
                  [class.active]="p === selectedPairForControl"
                  (click)="onSelectPair(p)">
                <span class="status-dot" [class.running]="status.isRunning"></span>
                <div class="d-flex flex-column">
                  <span class="name fw-bold">{{ p.replace('/USDT:USDT', 'USDT') }}</span>
                  <span class="text-xxs text-white-30">Motor Freqtrade</span>
                </div>
             </div>
          </div>
          <div class="dropdown-backdrop" *ngIf="showPairSelector" (click)="showPairSelector = false"></div>
        </div>
      </div>

      <!-- ESTADO VACÍO (CUANDO EL BOT HA SIDO ELIMINADO/NO CONFIGURADO) -->
      <ng-container *ngIf="status.activePairs.length === 0; else activeBotControl">
        <div class="empty-state text-center py-4">
          <span class="text-muted d-block mb-2">Sin pares activos.</span>
          <span class="text-xs text-white-30">Inicie un bot desde el panel izquierdo para comenzar.</span>
        </div>
      </ng-container>

      <ng-template #activeBotControl>
        <div class="status-row">
          <span class="label">Estado:</span>
          <span class="value" [class.success]="status.isRunning" [class.paused]="!status.isRunning">
            {{ status.isRunning ? 'Ejecutando' : 'Pausado' }}
          </span>
        </div>

      <div class="position-section" *ngIf="selectedTrade; else noTrade">
        <span class="section-label">Posición actual:</span>
        <div class="pos-main-card">
          <span class="direction long">LONG</span>
          <span class="amount">{{ selectedTrade.amount * selectedTrade.openRate | number:'1.2-2' }} USDT</span>
        </div>
        
        <div class="info-row">
          <span class="label">Entrada:</span>
          <span class="value">{{ selectedTrade.openRate | number:'1.5-5' }}</span>
        </div>
        
        <div class="info-row">
          <span class="label">PnL:</span>
          <span class="value pnl" [class.positive]="selectedTrade.pnl >= 0" [class.negative]="selectedTrade.pnl < 0">
            {{ selectedTrade.pnl >= 0 ? '+' : '' }}{{ selectedTrade.pnl | number:'1.2-2' }} USDT ({{ (selectedTrade.pnl / (selectedTrade.amount * selectedTrade.openRate)) * 100 | number:'1.1-1' }}%)
          </span>
        </div>
      </div>

      <ng-template #noTrade>
        <div class="position-section empty-state">
          <span class="text-muted">Seleccione un trade o espere a que el motor abra una posición.</span>
        </div>
      </ng-template>

      <!-- Bot Control Buttons -->
      <div class="control-buttons">
        <ng-container *ngIf="status.isRunning; else pausedState">
          <button class="btn-pause" (click)="pauseBot()">
            Pausar
          </button>
          <button class="btn-stop" (click)="stopBot()">
            <ion-icon name="stop-outline"></ion-icon> Stop
          </button>
        </ng-container>
        <ng-template #pausedState>
          <button class="btn-resume-active" (click)="resumeBot()">
            Continuar
          </button>
          <button class="btn-stop" (click)="deleteBot()">
            Eliminar
          </button>
        </ng-template>
      </div>

      <!-- Trade Control Button -->
      <button class="btn-close-pos-bottom" [disabled]="!selectedTrade" (click)="selectedTrade && closeTrade(selectedTrade.id)">
        <ion-icon name="chevron-down-outline"></ion-icon>
        Cerrar posición
      </button>
      </ng-template>
    </div>

    <!-- BOTS ACTIVOS LIST (FORZAR ACCIONES) -->
    <div class="control-panel-container bots-activos-panel" *ngIf="(pollService.status$ | async)?.activePairs?.length">
      <div class="panel-header">
        <h3>Forzar Acciones (IA)</h3>
      </div>
      
      <table class="mini-bots-table">
        <thead>
          <tr>
            <th>Par</th>
            <th>SCORE</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          <!-- Dynamic rows for each active pair -->
          <ng-container *ngIf="pollService.status$ | async as status">
            <tr *ngFor="let pair of status.activePairs">
              <td class="pair">{{ pair.replace('/USDT:USDT', 'USDT') }}</td>
              <td><span class="score-badge warning">{{ getScoreForPair(pair) }}</span></td>
              <td class="actions">
                <button class="btn-long" (click)="forceEnter(pair, 'long')" [disabled]="isForcingTrade || !status.isRunning">Long</button>
                <button class="btn-short" (click)="forceEnter(pair, 'short')" [disabled]="isForcingTrade || !status.isRunning">Short</button>
              </td>
            </tr>
          </ng-container>
        </tbody>
      </table>
    </div>
  `,
  styles: [`
    .control-panel-container {
      background: #11141d;
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      padding: 20px;
      color: white;
      margin-bottom: 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .bots-activos-panel {
      padding: 16px;
      gap: 12px;
    }

    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      h3 { margin: 0; font-size: 14px; font-weight: 700; color: #e2e8f0; text-transform: uppercase; letter-spacing: 0.5px; }
      ion-icon { color: #8b949e; cursor: pointer; }
    }

    .status-row {
      display: flex;
      gap: 8px;
      font-size: 16px;
      font-weight: 500;
      margin-bottom: 8px;
      .label { color: #8b949e; }
      .value.success { color: white; }
      .value.paused { color: #facc15; }
    }

    .position-section {
      display: flex;
      flex-direction: column;
      gap: 8px;
      
      .section-label {
        font-size: 15px;
        font-weight: 600;
        color: white;
        margin-bottom: 4px;
      }

      .pos-main-card {
        background: #191e2b;
        border-radius: 6px;
        padding: 10px 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        
        .direction {
          font-weight: 700;
          font-size: 16px;
          &.long { color: #22c55e; }
          &.short { color: #ef4444; }
        }
        .amount {
          font-weight: 600;
          font-size: 16px;
          color: white;
        }
      }

      .info-row {
        display: flex;
        justify-content: space-between;
        font-size: 15px;
        margin-top: 4px;
        .label { color: #8b949e; }
        .value { color: white; font-weight: 500; }
        .pnl {
          &.positive { color: #22c55e; }
          &.negative { color: #ef4444; }
        }
      }
    }

    .empty-state {
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 120px;
      background: #191e2b;
      border-radius: 8px;
      .text-muted { color: #8b949e; font-size: 13px; text-align: center; padding: 0 20px; }
    }

    .control-buttons {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 8px;
      
      button {
        padding: 12px;
        border: none;
        border-radius: 6px;
        font-weight: 700;
        font-size: 15px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        transition: all 0.2s;
        
        &.btn-pause { background: #facc15; color: #11141d; }
        &.btn-resume-active { background: #22c55e; color: white; }
        &.btn-stop { background: #ef4444; color: #fff; }
        &:hover { filter: brightness(1.1); transform: translateY(-1px); }
      }
    }

    .btn-close-pos-bottom {
      width: 100%;
      background: #191e2b;
      border: 1px solid rgba(255, 255, 255, 0.05);
      color: #8b949e;
      padding: 12px;
      border-radius: 6px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.2s;
      margin-top: 8px;
      &:hover:not([disabled]) { background: rgba(255, 255, 255, 0.08); color: white; }
      &[disabled] { opacity: 0.5; cursor: not-allowed; }
    }

    /* Custom Pair Selector Styles */
    .custom-pair-selector-root {
      .selected-pair-display {
        background: #191e2b;
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 6px 12px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
        color: #f0f6fc;
        transition: all 0.2s;
        &:hover { background: #212631; border-color: #3b82f6; }
      }

      .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #94a3b8;
        &.running { background: #22c55e; box-shadow: 0 0 8px rgba(34, 197, 94, 0.4); }
      }

      .pair-dropdown-menu {
        position: absolute;
        top: calc(100% + 8px);
        right: 0;
        min-width: 180px;
        background: #1c2128;
        border: 1px solid #30363d;
        border-radius: 8px;
        z-index: 2000;
        overflow: hidden;
        
        .pair-option {
          padding: 10px 14px;
          cursor: pointer;
          transition: background 0.2s;
          border-bottom: 1px solid rgba(255,255,255,0.03);
          &:hover { background: rgba(59, 130, 246, 0.1); }
          &.active { background: rgba(59, 130, 246, 0.15); border-left: 2px solid #3b82f6; }
          
          .name { font-size: 13px; color: #f8fafc; }
        }
      }
      
      .dropdown-backdrop {
        position: fixed;
        top: 0; left: 0; width: 100vw; height: 100vh;
        z-index: 1000;
      }
    }

    /* Mini Bots Table */
    .mini-bots-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;

      th { 
        text-align: left; 
        color: #8b949e; 
        font-weight: 500; 
        padding-bottom: 12px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        font-size: 11px;
        line-height: 1.2;
      }
      
      td { 
        padding: 12px 0; 
        border-bottom: 1px solid rgba(255, 255, 255, 0.02);
        color: #e2e8f0;
      }

      .name { font-weight: 600; }
      .pair { color: #8b949e; }
      
      .score-badge {
        padding: 2px 6px;
        border-radius: 4px;
        background: rgba(255, 255, 255, 0.05);
        font-weight: 600;
        &.warning { color: #facc15; }
        &.info { color: #38bdf8; }
        &.neutral { color: #8b949e; }
      }

      .actions {
        display: flex;
        gap: 4px;
        justify-content: flex-end;
        
        button {
          padding: 4px 8px;
          border-radius: 4px;
          border: none;
          font-size: 10px;
          font-weight: 700;
          cursor: pointer;
          color: white;
          opacity: 0.9;
          
          &.btn-long { background: #22c55e; }
          &.btn-short { background: #ef4444; opacity: 0.8; }
          
          &:hover:not([disabled]) { opacity: 1; transform: scale(1.05); }
          &[disabled] { cursor: not-allowed; opacity: 0.5; }
        }
      }
    }
  `]
})
export class BotControlPanelComponent implements OnInit {
  public pollService = inject(FreqtradePollService);
  private freqtradeService = inject(FreqtradeService);
  private toaster = inject(ToasterService);
  private signalRService = inject(BotSignalRService);

  selectedTrade: FreqtradeTradeDto | null = null;
  selectedPairForControl: string = '';
  isForcingTrade = false;
  showPairSelector = false;

  onSelectPair(pair: string) {
    this.pollService.selectPair(pair);
    this.showPairSelector = false;
  }

  constructor() {
    addIcons({ chevronDownOutline, pauseOutline, stopOutline, closeCircleOutline });
  }

  ngOnInit() {
    // Sincronizar selección desde el servicio centralizado
    this.pollService.selectedPair$.subscribe(pair => {
      if (pair) {
        this.selectedPairForControl = pair;
        this.showPairSelector = false;
      }
    });

    this.pollService.status$.subscribe(status => {
      if (status && status.activePairs && status.activePairs.length > 0) {
        if (!this.selectedPairForControl || !status.activePairs.includes(this.selectedPairForControl)) {
          // Si no hay nada seleccionado, tomamos el del servicio o el primero
          const currentGlobal = this.pollService.selectedPair$.value;
          this.selectedPairForControl = currentGlobal || status.activePairs[0];
          if (!currentGlobal) this.pollService.selectPair(status.activePairs[0]);
        }
      } else {
        this.selectedPairForControl = '';
      }
    });
    // Escuchar el trade seleccionado centralizado en pollService
    combineLatest([
      this.pollService.openTrades$,
      this.pollService.selectedTradeId$
    ]).pipe(
      map(([trades, selectedId]) => {
        if (!selectedId && trades.length > 0) return trades[0];
        return trades.find(t => t.id === selectedId) || null;
      })
    ).subscribe(trade => {
      this.selectedTrade = trade;
    });
  }

  getScoreForPair(pairName: string): number | string {
    if (!pairName || pairName === 'No configurado' || pairName === 'Offline') return '--';
    const barePair = pairName.replace('/USDT:USDT', 'USDT').replace('/', '');
    const botPairs = this.signalRService.activePairs();
    const found = botPairs.find(p => p.symbol === barePair);
    return found ? found.score : '--';
  }

  closeTrade(id: number) {
    if (confirm(`¿Está seguro de cerrar prematuramente el trade #${id}?`)) {
      this.freqtradeService.closeTrade(id.toString()).subscribe({
        next: () => {
          this.toaster.success('Orden de cierre enviada exitosamente al Exchange.');
          this.pollService.refresh();
        },
        error: () => this.toaster.error('Hubo un error cerrando el trade.')
      });
    }
  }

  forceEnter(pair: string, side: string) {
    this.isForcingTrade = true;
    this.toaster.info(`Enviando Force ${side.toUpperCase()} para ${pair} al motor Freqtrade...`);
    this.freqtradeService.forceEnter(pair, side, 100, 10).subscribe({
      next: () => {
        this.toaster.success(`Trade ${side.toUpperCase()} inyectado en el mercado.`);
        this.isForcingTrade = false;
        this.pollService.refresh();
      },
      error: (err) => {
        this.toaster.error('Error desde Binance, revisa los logs.', 'Operación rechazada');
        this.isForcingTrade = false;
      }
    });
  }

  pauseBot() {
    // Emulate "Pausar" which is actually Freqtrade's /api/v1/stop keeping the container alive
    this.freqtradeService.stopBot().subscribe({
      next: () => {
        this.toaster.success('El motor de IA fue pausado, ya no abrirá nuevas posiciones.');
        this.pollService.refresh();
      },
      error: () => this.toaster.error('Hubo un error al intentar pausar el motor.')
    });
  }

  stopBot() {
    // In many UI contexts stop is similar or it kills the loop
    this.pauseBot(); 
  }

  resumeBot() {
    this.freqtradeService.resumeBot().subscribe({
      next: () => {
        this.toaster.success('Motor reanudado con éxito.');
        this.pollService.refresh();
      },
      error: (err) => this.toaster.error('Error al intentar reanudar el motor.')
    });
  }

  deleteBot() {
    if (!this.selectedPairForControl) return;
    
    if (confirm(`¿Desea detener y eliminar el bot en ${this.selectedPairForControl}?`)) {
      this.freqtradeService.deleteBot(this.selectedPairForControl).subscribe({
        next: () => {
          this.toaster.success(`El bot para ${this.selectedPairForControl} ha sido eliminado.`);
          this.pollService.refresh();
        },
        error: () => this.toaster.error('Hubo un error al intentar eliminar el bot.')
      });
    }
  }
}
