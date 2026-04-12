import { Component, inject, OnInit, OnDestroy, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { chevronDownOutline, pauseOutline, stopOutline, closeCircleOutline, playOutline, refreshOutline, trashOutline, flashOutline } from 'ionicons/icons';
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
    <div class="control-panel-container" *ngIf="pollService.status$ | async as status">
      
      <!-- GLOBAL MOTOR SECTION -->
      <div class="motor-section mb-4">
        <h3 class="section-title text-center mb-3">MOTOR FREQTRADE</h3>
        <div class="status-indicator d-flex justify-content-center align-items-center gap-2 mb-3">
          <span class="status-dot" [class.running]="status.isRunning"></span>
          <span class="status-text fw-bold" [class.text-success]="status.isRunning" [class.text-warning]="!status.isRunning">
            {{ status.isRunning ? 'ONLINE' : 'STOPPED' }}
          </span>
        </div>
        
        <div class="global-controls d-flex justify-content-center gap-2">
          <button class="btn-icon play" title="Start Engine" (click)="startEngine()" [disabled]="status.isRunning">
            <ion-icon name="play-outline"></ion-icon>
          </button>
          <button class="btn-icon pause" title="Pause (StopBuy)" (click)="pauseEngine()" [disabled]="!status.isRunning">
            <ion-icon name="pause-outline"></ion-icon>
          </button>
          <button class="btn-icon stop" title="Stop Engine" (click)="stopEngine()" [disabled]="!status.isRunning">
            <ion-icon name="stop-outline"></ion-icon>
          </button>
          <button class="btn-icon reload" title="Reload Config" (click)="reloadConfig()">
            <ion-icon name="refresh-outline"></ion-icon>
          </button>
        </div>
      </div>

      <!-- SEPARATOR -->
      <div class="divider border-top border-secondary opacity-25 my-3"></div>

      <!-- PAIR SPECIFIC SECTION -->
      <div class="pair-section">
        <div class="panel-header d-flex align-items-center justify-content-between mb-3">
          <h3 class="section-title m-0">CONTROL DEL PAR</h3>
          
          <div class="custom-pair-selector-root position-relative" *ngIf="status.activePairs.length > 0">
            <div class="selected-pair-display d-flex align-items-center gap-2" (click)="showPairSelector = !showPairSelector">
               <span class="pair-name fw-bold">{{ selectedPairForControl.replace('/', '').split(':')[0] || 'Seleccionar' }}</span>
               <ion-icon name="chevron-down-outline" class="ms-1"></ion-icon>
            </div>
            
            <div class="pair-dropdown-menu shadow-xl fade-in" *ngIf="showPairSelector">
               <div class="pair-option d-flex align-items-center gap-3 justify-content-between" 
                    *ngFor="let p of status.activePairs"
                    [class.active]="p === selectedPairForControl"
                    (click)="onSelectPair(p)">
                  <span class="name fw-bold">{{ p.replace('/', '').split(':')[0] }}</span>
                  <span class="ms-auto" style="font-size: 11px;" [class.text-success]="getTradeForPair(p)?.profitAbs >= 0" [class.text-danger]="getTradeForPair(p)?.profitAbs < 0">
                    {{ getTradeForPair(p) ? (getTradeForPair(p)!.profitAbs >= 0 ? '+' : '') + (getTradeForPair(p)!.profitAbs | number:'1.2-2') + ' USDT' : '' }}
                  </span>
               </div>
            </div>
            <div class="dropdown-backdrop" *ngIf="showPairSelector" (click)="showPairSelector = false"></div>
          </div>
        </div>

        <ng-container *ngIf="!selectedPairForControl || status.activePairs.length === 0; else activeBotControl">
          <div class="empty-state text-center py-3">
            <span class="text-muted d-block text-xs">Aún no hay pares activos<br>o ninguno ha sido seleccionado.</span>
          </div>
        </ng-container>

        <ng-template #activeBotControl>
          <div class="position-section mb-3" *ngIf="selectedTrade; else noTrade">
            <span class="text-xs text-white-50 d-block mb-1">POSICIÓN ACTUAL</span>
            <div class="pos-main-card">
              <span class="direction" [class.long]="!selectedTrade.isShort" [class.short]="selectedTrade.isShort">
                {{ selectedTrade.isShort ? 'SHORT' : 'LONG' }}
              </span>
              <span class="amount">{{ (selectedTrade.amount * selectedTrade.openRate) | number:'1.2-2' }} USDT</span>
            </div>
            
            <div class="info-row mt-2">
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
            <div class="position-section empty-state mb-3">
              <span class="text-muted text-xs">No hay posiciones abiertas en este par.</span>
            </div>
          </ng-template>

          <!-- Bot Control Buttons -->
          <div class="pair-controls d-flex flex-wrap gap-2 mt-2">
            <button class="btn-pair outline-danger flex-grow-1" (click)="deleteBot()" title="Eliminar de la Lista de Trading">
              <ion-icon name="trash-outline"></ion-icon> Delete Bot
            </button>
            <button class="btn-pair fill-danger flex-grow-1" [disabled]="!selectedTrade" (click)="selectedTrade && forceExit(selectedTrade.id)" title="Forzar salida al mercado">
              <ion-icon name="flash-outline"></ion-icon> Force Exit Trade
            </button>
          </div>
        </ng-template>
      </div>
    </div>
  `,
  styles: [`
    .control-panel-container { background: #11141d; border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 20px; color: white; display: flex; flex-direction: column; }
    .section-title { margin: 0; font-size: 13px; font-weight: 700; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    
    .status-dot { width: 10px; height: 10px; border-radius: 50%; background: #ef4444; box-shadow: 0 0 8px rgba(239, 68, 68, 0.4); }
    .status-dot.running { background: #22c55e; box-shadow: 0 0 8px rgba(34, 197, 94, 0.4); }
    
    .btn-icon { width: 44px; height: 44px; border-radius: 8px; border: none; background: rgba(255,255,255,0.05); color: white; display: flex; align-items: center; justify-content: center; font-size: 20px; cursor: pointer; transition: all 0.2s; }
    .btn-icon:hover:not([disabled]) { transform: translateY(-2px); }
    .btn-icon[disabled] { opacity: 0.3; cursor: not-allowed; }
    .btn-icon.play:hover:not([disabled]) { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
    .btn-icon.pause:hover:not([disabled]) { background: rgba(250, 204, 21, 0.2); color: #facc15; }
    .btn-icon.stop:hover:not([disabled]) { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
    .btn-icon.reload:hover:not([disabled]) { background: rgba(59, 130, 246, 0.2); color: #3b82f6; }

    .position-section { display: flex; flex-direction: column; gap: 4px;}
    .pos-main-card { background: #191e2b; border-radius: 6px; padding: 10px 16px; display: flex; justify-content: space-between; align-items: center; }
    .pos-main-card .direction { font-weight: 700; font-size: 14px; }
    .pos-main-card .direction.long { color: #22c55e; }
    .pos-main-card .direction.short { color: #ef4444; }
    .pos-main-card .amount { font-weight: 600; font-size: 14px; color: white; }
    .info-row { display: flex; justify-content: space-between; font-size: 13px; }
    .info-row .label { color: #8b949e; }
    .info-row .value.pnl.positive { color: #22c55e; }
    .info-row .value.pnl.negative { color: #ef4444; }
    
    .empty-state { background: #191e2b; border-radius: 8px; min-height: 80px; display: flex; align-items: center; justify-content: center; }
    
    .btn-pair { padding: 10px; border-radius: 6px; font-weight: 600; font-size: 13px; display: flex; align-items: center; justify-content: center; gap: 6px; cursor: pointer; transition: all 0.2s; border: 1px solid transparent; }
    .btn-pair[disabled] { opacity: 0.4; cursor: not-allowed; }
    .btn-pair.outline-warning { background: transparent; border-color: rgba(250, 204, 21, 0.3); color: #facc15; }
    .btn-pair.outline-warning:hover:not([disabled]) { background: rgba(250, 204, 21, 0.1); }
    .btn-pair.fill-success { background: rgba(34, 197, 94, 0.15); color: #22c55e; border-color: rgba(34, 197, 94, 0.3); }
    .btn-pair.fill-success:hover:not([disabled]) { background: rgba(34, 197, 94, 0.25); }
    .btn-pair.outline-danger { background: transparent; border-color: rgba(239, 68, 68, 0.3); color: #ef4444; }
    .btn-pair.outline-danger:hover:not([disabled]) { background: rgba(239, 68, 68, 0.1); }
    .btn-pair.fill-danger { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
    .btn-pair.fill-danger:hover:not([disabled]) { background: rgba(239, 68, 68, 0.3); }

    .custom-pair-selector-root .selected-pair-display { background: #191e2b; border: 1px solid rgba(255, 255, 255, 0.1); padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; color: #f0f6fc; }
    .pair-dropdown-menu { position: absolute; top: calc(100% + 8px); right: 0; min-width: 160px; background: #1c2128; border: 1px solid #30363d; border-radius: 8px; z-index: 2000; overflow: hidden; }
    .pair-option { padding: 10px 14px; cursor: pointer; border-left: 2px solid transparent;}
    .pair-option:hover { background: rgba(255,255,255,0.05); }
    .pair-option.active { background: rgba(59, 130, 246, 0.15); border-left-color: #3b82f6; }
    .dropdown-backdrop { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 1000; }
  `]
})
export class BotControlPanelComponent implements OnInit, OnDestroy {
  public pollService = inject(FreqtradePollService);
  private freqtradeService = inject(FreqtradeService);
  private toaster = inject(ToasterService);
  private signalR = inject(TradingSignalrService);

  selectedTrade: FreqtradeTradeDto | null = null;
  allOpenTrades: FreqtradeTradeDto[] = [];
  selectedPairForControl: string = '';
  showPairSelector = false;

  private scoresSub: Subscription | null = null;
  private scoresMap: Record<string, number> = {};

  constructor() {
    addIcons({ chevronDownOutline, pauseOutline, stopOutline, closeCircleOutline, playOutline, refreshOutline, trashOutline, flashOutline });
  }

  ngOnInit() {
    this.pollService.selectedPair$.subscribe(pair => {
      if (pair) this.selectedPairForControl = pair;
    });

    this.pollService.openTrades$.subscribe(trades => {
      this.allOpenTrades = trades;
    });

    this.scoresSub = this.signalR.superScore$.subscribe(data => {
      if (data && data.symbol) {
        const sym = data.symbol.replace('/', '').split(':')[0];
        this.scoresMap[sym] = data.score;
      }
    });

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

  // --- MOTOR GLOBAL ACTIONS ---

  startEngine() {
    this.freqtradeService.resumeBot().subscribe(() => {
      this.toaster.success('Motor Iniciado.');
      this.pollService.refresh();
    });
  }

  pauseEngine() {
    this.freqtradeService.pauseBot().subscribe(() => {
      this.toaster.success('Motor en pausa (No abrirá nuevos trades).');
      this.pollService.refresh();
    });
  }

  stopEngine() {
    if (confirm('¿Detener completamente el motor Freqtrade? Esto apagará todos los bots activos.')) {
      this.freqtradeService.stopBot().subscribe(() => {
        this.toaster.success('Motor Detenido.');
        this.pollService.refresh();
      });
    }
  }

  reloadConfig() {
    this.freqtradeService.reloadConfig().subscribe(() => {
      this.toaster.info('Recargando configuración de Freqtrade...');
      this.pollService.refresh();
    });
  }

  // --- PAIR ACTIONS ---

  deleteBot() {
    if (this.selectedPairForControl && confirm(`¿Eliminar ${this.selectedPairForControl} completamente del motor?`)) {
      this.freqtradeService.deleteBot(this.selectedPairForControl).subscribe(() => {
        this.toaster.success('Par eliminado exitosamente.');
        this.selectedPairForControl = '';
        this.pollService.refresh();
      });
    }
  }

  forceExit(id: number) {
    if (confirm(`¿Forzar venta del trade #${id} al precio de mercado?`)) {
      this.freqtradeService.forceExit(id.toString()).subscribe(() => {
        this.toaster.success('Orden Force Exit enviada.');
        this.pollService.refresh();
      });
    }
  }

  getTradeForPair(pair: string): FreqtradeTradeDto | null {
    const base = pair.replace('/', '').split(':')[0];
    return this.allOpenTrades.find(t => t.pair === base) || null;
  }
}

