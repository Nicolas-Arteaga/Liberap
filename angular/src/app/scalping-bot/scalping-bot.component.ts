import { Component, OnInit, OnDestroy, inject, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IonIcon, IonBadge } from '@ionic/angular/standalone';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { CardContentComponent } from "src/shared/components/card-content/card-content.component";
import { ToggleComponent } from 'src/shared/components/toggle/toggle.component';
import { Subject, timer } from 'rxjs';
import { takeUntil, switchMap } from 'rxjs/operators';
import { ScalpingBotService } from '../proxy/trading/scalping-bot.service';
import { ScalpingBotStatusDto, ScalpingBotConfigDto, BotTradeDto } from '../proxy/trading/bot/models';
import { TradingSignalrService } from '../services/trading-signalr.service';

@Component({
  selector: 'app-scalping-bot',
  standalone: true,
  imports: [
    CommonModule, 
    FormsModule, 
    IonIcon, 
    IonBadge,
    GlassButtonComponent, 
    CardContentComponent,
    ToggleComponent
  ],
  templateUrl: './scalping-bot.component.html',
  styleUrls: ['./scalping-bot.component.scss']
})
export class ScalpingBotComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('terminalBody') private terminalBody!: ElementRef;
  private botService = inject(ScalpingBotService);
  private signalrService = inject(TradingSignalrService);
  private destroy$ = new Subject<void>();

  status: ScalpingBotStatusDto | null = null;
  config: ScalpingBotConfigDto | null = null;
  activeTrades: BotTradeDto[] = [];
  tradeHistory: BotTradeDto[] = [];

  isLoading = true;
  isSaving = false;

  whitelistText = '';
  blacklistText = '';
  botLogs: any[] = [];

  ngOnInit() {
    this.loadStatus();
    this.subscribeToRealtimeUpdates();
  }

  ngOnDestroy() {
    this.destroy$.complete();
  }

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  private scrollToBottom(): void {
    try {
      this.terminalBody.nativeElement.scrollTop = this.terminalBody.nativeElement.scrollHeight;
    } catch (err) { }
  }

  loadStatus() {
    this.isLoading = true;
    this.botService.getStatus().subscribe({
      next: (res) => {
        this.status = res;
        this.config = JSON.parse(JSON.stringify(res.config)); // Clonar
        this.whitelistText = this.config?.whitelistSymbols?.join(', ') || '';
        this.blacklistText = this.config?.blacklistSymbols?.join(', ') || '';
        this.botLogs = res.recentLogs || [];
        this.loadOpenTrades();
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Error loading bot status', err);
        this.isLoading = false;
      }
    });
  }

  loadOpenTrades() {
    this.botService.getTrades(50).subscribe({
      next: (trades) => {
        this.activeTrades = trades.filter(t => t.status === 'Open' || t.status === 'PartialClose');
      }
    });
  }

  toggleBot() {
    this.isLoading = true;
    const action = this.status?.isRunning ? this.botService.stopBot() : this.botService.startBot();
    
    action.subscribe({
      next: () => {
        // En backend startBot y stopBot retornan void, asi que recargamos el status manual.
        this.loadStatus();
      },
      error: (err) => {
        console.error('Error toggling bot', err);
        this.isLoading = false;
      }
    });
  }

  saveConfig() {
    if (!this.config) return;
    this.isSaving = true;

    // Convert strings back to arrays
    this.config.whitelistSymbols = this.whitelistText.split(',').map(s => s.trim()).filter(s => s.length > 0);
    this.config.blacklistSymbols = this.blacklistText.split(',').map(s => s.trim()).filter(s => s.length > 0);

    const savedConfig = JSON.parse(JSON.stringify(this.config));

    this.botService.updateConfig(this.config).subscribe({
      next: () => {
        // En backend updateConfig retorna void
        this.config = savedConfig;
        if (this.status) {
          this.status.config = savedConfig;
        }
        this.isSaving = false;
      },
      error: (err) => {
        console.error('Error updating config', err);
        this.isSaving = false;
      }
    });
  }

  subscribeToRealtimeUpdates() {
    // 1. Logs de actividad del bot
    this.signalrService.botActivityLog$
      .pipe(takeUntil(this.destroy$))
      .subscribe(log => {
        this.botLogs.push(log);
        if (this.botLogs.length > 100) this.botLogs.shift();
      });

    // 2. Apertura de trades del bot
    this.signalrService.botTradeOpened$
      .pipe(takeUntil(this.destroy$))
      .subscribe(trade => {
        // Evitar duplicados
        if (!this.activeTrades.find(t => t.id === trade.botTradeId)) {
          // El DTO de SignalR puede ser ligeramente distinto, mapeamos lo necesario
          this.activeTrades.unshift({
            id: trade.botTradeId,
            symbol: trade.symbol,
            direction: trade.direction === 'Long' ? 0 : 1,
            entryPrice: trade.entryPrice,
            currentPrice: trade.entryPrice,
            stopLoss: trade.stopLoss,
            takeProfit1: trade.takeProfit1,
            takeProfit2: trade.takeProfit2,
            leverage: trade.leverage,
            status: 'Open',
            totalPnl: 0,
            openedAt: trade.openedAt
          } as any);
          
          if (this.status) this.status.dailyTrades++;
        }
      });

    // 3. Cierre de trades (evento estándar de la app)
    this.signalrService.tradeClosed$
      .pipe(takeUntil(this.destroy$))
      .subscribe(trade => {
        this.activeTrades = this.activeTrades.filter(t => t.id !== trade.id);
        // Actualizar estadísticas diarias si el trade era del bot
        this.botService.getStatus().subscribe(res => this.status = res);
      });
    
    // Polling backup cada 30 segundos para PNL y trades
    timer(30000, 30000).pipe(
      takeUntil(this.destroy$),
      switchMap(() => this.botService.getStatus())
    ).subscribe({
      next: (status) => {
        this.status = status;
        this.loadOpenTrades(); // Refrescar trades vivos
      }
    });
  }

  formatCurrency(value: number | null | undefined): string {
    if (value === null || value === undefined) return '$0.00';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
  }
}
