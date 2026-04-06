import { Component, inject, OnInit, OnDestroy, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { chevronDownOutline, pauseOutline, stopOutline, closeCircleOutline } from 'ionicons/icons';
import { FreqtradePollService } from '../../../services/freqtrade-poll.service';
import { FreqtradeService } from '../../../proxy/freqtrade/freqtrade.service';
import { ToasterService } from '@abp/ng.theme.shared';
import { TradingSignalrService } from '../../../services/trading-signalr.service';
import { FreqtradeTradeDto } from '../../../proxy/freqtrade/models';
import { combineLatest, Subscription } from 'rxjs';
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
             <span class="pair-name fw-bold">{{ selectedPairForControl.replace('/', '').split(':')[0] }}</span>
             <ion-icon name="chevron-down-outline" class="ms-1"></ion-icon>
          </div>
          
          <div class="pair-dropdown-menu shadow-xl fade-in" *ngIf="showPairSelector">
             <div class="pair-option d-flex align-items-center gap-3" 
                  *ngFor="let p of status.activePairs"
                  [class.active]="p === selectedPairForControl"
                  (click)="onSelectPair(p)">
                <span class="status-dot" [class.running]="status.isRunning"></span>
                <div class="d-flex flex-column">
                  <span class="name fw-bold">{{ p.replace('/', '').split(':')[0] }}</span>
                  <span class="text-xxs text-white-30">Motor Freqtrade</span>
                </div>
             </div>
          </div>
          <div class="dropdown-backdrop" *ngIf="showPairSelector" (click)="showPairSelector = false"></div>
        </div>
      </div>

      <!-- ESTADO VACÍO O SINCRONIZANDO -->
      <ng-container *ngIf="status.activePairs.length === 0; else activeBotControl">
        <div class="empty-state text-center py-4">
          <ng-container *ngIf="status.isRunning; else stoppedEmpty">
            <span class="text-white d-block mb-2">Sincronizando motor...</span>
            <span class="text-xs text-white-30">Detectando configuración de Freqtrade.</span>
          </ng-container>
          <ng-template #stoppedEmpty>
            <span class="text-muted d-block mb-2">Sin bots activos.</span>
            <span class="text-xs text-white-30">Configure un par en el panel izquierdo para comenzar.</span>
          </ng-template>
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
          <span class="direction" [class.long]="!selectedTrade.isShort" [class.short]="selectedTrade.isShort">
            {{ selectedTrade.isShort ? 'SHORT' : 'LONG' }}
          </span>
          <span class="amount">{{ (selectedTrade.amount * selectedTrade.openRate) | number:'1.2-2' }} USDT</span>
        </div>
        
        <div class="info-row">
          <span class="label">Entrada:</span>
          <span class="value">{{ selectedTrade.openRate | number:'1.5-5' }}</span>
        </div>
        
        <div class="info-row">
          <span class="label">PnL:</span>
          <span class="value pnl" [class.positive]="selectedTrade.profitAbs >= 0" [class.negative]="selectedTrade.profitAbs < 0">
            {{ selectedTrade.profitAbs >= 0 ? '+' : '' }}{{ selectedTrade.profitAbs | number:'1.2-2' }} USDT ({{ selectedTrade.profitPercentage | number:'1.1-1' }}%)
          </span>
        </div>
      </div>

      <ng-template #noTrade>
        <div class="position-section empty-state">
          <span class="text-muted">No hay posiciones abiertas en este bot.</span>
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
        <ion-icon name="close-circle-outline"></ion-icon>
        Cerrar posición
      </button>
      </ng-template>
    </div>
  `,
  styles: [`
    /* (Styles remain same as before) */
    .control-panel-container { background: #11141d; border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 20px; color: white; display: flex; flex-direction: column; gap: 16px; margin-bottom: 20px; }
    .panel-header h3 { margin: 0; font-size: 14px; font-weight: 700; color: #e2e8f0; text-transform: uppercase; letter-spacing: 0.5px; }
    .status-row { display: flex; gap: 8px; font-size: 16px; font-weight: 500; .label { color: #8b949e; } .value.success { color: #22c55e; } .value.paused { color: #facc15; } }
    .position-section { display: flex; flex-direction: column; gap: 8px; .section-label { font-size: 15px; font-weight: 600; color: white; } .pos-main-card { background: #191e2b; border-radius: 6px; padding: 10px 16px; display: flex; justify-content: space-between; align-items: center; .direction { font-weight: 700; font-size: 16px; &.long { color: #22c55e; } &.short { color: #ef4444; } } .amount { font-weight: 600; font-size: 16px; color: white; } } .info-row { display: flex; justify-content: space-between; font-size: 15px; .label { color: #8b949e; } .value { color: white; font-weight: 500; } .pnl { &.positive { color: #22c55e; } &.negative { color: #ef4444; } } } }
    .empty-state { display: flex; justify-content: center; align-items: center; min-height: 100px; background: #191e2b; border-radius: 8px; .text-muted { color: #8b949e; font-size: 13px; } }
    .control-buttons { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 8px; button { padding: 12px; border: none; border-radius: 6px; font-weight: 700; cursor: pointer; transition: all 0.2s; &.btn-pause { background: #facc15; color: #11141d; } &.btn-resume-active { background: #22c55e; color: white; } &.btn-stop { background: #ef4444; color: #fff; } &:hover { filter: brightness(1.1); transform: translateY(-1px); } } }
    .btn-close-pos-bottom { width: 100%; background: #191e2b; border: 1px solid rgba(255, 255, 255, 0.05); color: #8b949e; padding: 12px; border-radius: 6px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; margin-top: 8px; transition: all 0.2s; &:hover:not([disabled]) { background: rgba(255, 255, 255, 0.08); color: white; } &[disabled] { opacity: 0.5; cursor: not-allowed; } }
    .custom-pair-selector-root { .selected-pair-display { background: #191e2b; border: 1px solid rgba(255, 255, 255, 0.1); padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; color: #f0f6fc; } .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; &.running { background: #22c55e; box-shadow: 0 0 8px rgba(34, 197, 94, 0.4); } } .pair-dropdown-menu { position: absolute; top: calc(100% + 8px); right: 0; min-width: 180px; background: #1c2128; border: 1px solid #30363d; border-radius: 8px; z-index: 2000; overflow: hidden; .pair-option { padding: 10px 14px; cursor: pointer; transition: background 0.2s; &.active { background: rgba(59, 130, 246, 0.15); border-left: 2px solid #3b82f6; } &:hover { background: rgba(59, 130, 246, 0.1); } .name { font-size: 13px; color: #f8fafc; } } } .dropdown-backdrop { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 1000; } }
  `]
})
export class BotControlPanelComponent implements OnInit, OnDestroy {
  public pollService = inject(FreqtradePollService);
  private freqtradeService = inject(FreqtradeService);
  private toaster = inject(ToasterService);
  private signalR = inject(TradingSignalrService);

  selectedTrade: FreqtradeTradeDto | null = null;
  selectedPairForControl: string = '';
  showPairSelector = false;

  private scoresSub: Subscription | null = null;
  private scoresMap: Record<string, number> = {};

  constructor() {
    addIcons({ chevronDownOutline, pauseOutline, stopOutline, closeCircleOutline });
  }

  ngOnInit() {
    // Escuchar selección global
    this.pollService.selectedPair$.subscribe(pair => {
      if (pair) this.selectedPairForControl = pair;
    });

    // Escuchar scores en tiempo real
    this.scoresSub = this.signalR.superScore$.subscribe(data => {
      if (data && data.symbol) {
        const sym = data.symbol.replace('/', '').split(':')[0];
        this.scoresMap[sym] = data.score;
      }
    });

    // Match del trade basado en la selección
    combineLatest([
      this.pollService.openTrades$,
      this.pollService.selectedPair$
    ]).pipe(
      map(([trades, selectedPair]) => {
        if (!selectedPair) return trades.length > 0 ? trades[0] : null;
        const base = selectedPair.replace('/', '').split(':')[0];
        return trades.find(t => t.pair === base) || null;
      })
    ).subscribe(trade => {
      this.selectedTrade = trade;
    });
  }

  ngOnDestroy() {
    this.scoresSub?.unsubscribe();
  }

  onSelectPair(pair: string) {
    this.pollService.selectPair(pair);
    this.showPairSelector = false;
  }

  getScoreForPair(pair: string): number | string {
    const bare = pair.replace('/', '').split(':')[0];
    return this.scoresMap[bare] ?? '--';
  }

  closeTrade(id: number) {
    if (confirm(`¿Cerrar trade #${id}?`)) {
      this.freqtradeService.closeTrade(id.toString()).subscribe(() => {
        this.toaster.success('Cerrado exitosamente.');
        this.pollService.refresh();
      });
    }
  }

  pauseBot() {
    this.freqtradeService.stopBot().subscribe(() => {
       this.toaster.success('Bot pausado (No abrirá nuevas órdenes).');
       this.pollService.refresh();
    });
  }

  stopBot() { this.pauseBot(); }

  resumeBot() {
    this.freqtradeService.resumeBot().subscribe(() => {
      this.toaster.success('Bot reanudado.');
      this.pollService.refresh();
    });
  }

  deleteBot() {
    if (this.selectedPairForControl && confirm('¿Eliminar bot?')) {
      this.freqtradeService.deleteBot(this.selectedPairForControl).subscribe(() => {
        this.toaster.success('Bot eliminado.');
        this.pollService.refresh();
      });
    }
  }
}

