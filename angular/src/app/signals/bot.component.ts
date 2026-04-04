import { Component, computed, signal, inject, OnInit, OnDestroy, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { notificationsOutline, personCircleOutline, searchOutline } from 'ionicons/icons';
import { BotOrderService } from './services/bot-order.service';
import { BotSignalRService } from './services/bot-signalr.service';
import { BotApiService } from './services/bot-api.service';
import { interval, Subscription } from 'rxjs';
import { startWith, switchMap, tap } from 'rxjs/operators';
import { FreqtradePollService } from '../services/freqtrade-poll.service';

// New V2 Components
import { BotStatsBarComponent } from './components/bot-stats-bar/bot-stats-bar.component';
import { CreateBotFormComponent } from './components/create-bot-form/create-bot-form.component';
import { ActiveBotsTableComponent } from './components/active-bots-table/active-bots-table.component';
import { BotControlPanelComponent } from './components/bot-control-panel/bot-control-panel.component';
import { TradePanelComponent } from './components/trade-panel/trade-panel.component';

@Component({
  selector: 'app-bot',
  standalone: true,
  imports: [
    CommonModule, 
    BotStatsBarComponent, 
    CreateBotFormComponent, 
    ActiveBotsTableComponent, 
    BotControlPanelComponent,
    TradePanelComponent
  ],
  templateUrl: './bot.component.html',
  styleUrls: ['./bot.component.scss']
})
export class BotComponent implements OnInit, OnDestroy {
  private botApiService = inject(BotApiService);
  private botSignalRService = inject(BotSignalRService);
  private botOrderService = inject(BotOrderService);
  private freqtradePollService = inject(FreqtradePollService);
  private pollingSubscription?: Subscription;

  activePairs = this.botSignalRService.activePairs;
  selectedBot = this.botOrderService.selectedOrder;
  
  // For the chart to show the pair of the selected bot, or a default
  displayPair = computed(() => {
    const bot = this.selectedBot();
    if (bot) {
      return this.activePairs().find(p => p.symbol === bot.symbol) || this.activePairs()[0];
    }
    return this.activePairs()[0];
  });

  constructor() {
    addIcons({ notificationsOutline, personCircleOutline, searchOutline });
    
    // Reactively refresh when SignalR says status changed
    effect(() => {
      const status = this.botSignalRService.botStatus();
      console.log(`[BotComponent] SignalR status flip: ${status}. Refreshing poll...`);
      this.freqtradePollService.refresh();
    });
  }

  ngOnInit(): void {
    this.startPolling();
    this.freqtradePollService.startPolling();
  }

  ngOnDestroy(): void {
    this.pollingSubscription?.unsubscribe();
    this.freqtradePollService.stopPolling();
  }

  private startPolling() {
    this.pollingSubscription = interval(5000)
      .pipe(
        startWith(0),
        switchMap(() => this.botApiService.getActivePairs().pipe(
          tap(pairs => this.botSignalRService.updatePairs(pairs))
        ))
      )
      .subscribe();
  }
}
