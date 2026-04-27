import { Component, Input, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IonIcon } from '@ionic/angular/standalone';
import { LeverageModalComponent } from '../leverage-modal/leverage-modal.component';
import { SimulatedTradeService } from 'src/app/proxy/trading/simulated-trade.service';
import { SignalDirection } from 'src/app/proxy/trading/signal-direction.enum';

@Component({
  selector: 'app-trading-panel',
  standalone: true,
  imports: [CommonModule, FormsModule, IonIcon, LeverageModalComponent],
  templateUrl: './trading-panel.component.html',
  styleUrls: ['./trading-panel.component.scss']
})
export class TradingPanelComponent implements OnInit {
  @Input() symbol: string = 'BTCUSDT';
  @Input() balance: number = 0;
  @Input() price: number = 0;
  
  private simulatedTradeService = inject(SimulatedTradeService);
  
  orderType: 'limit' | 'market' | 'stop-limit' = 'market';
  
  stopPrice: number = 0;
  amount: number | null = 100;
  leverage: number = 10;
  marginType: 'Cruzado' | 'Aislado' = 'Aislado';
  showLeverageModal: boolean = false;
  showTpSl: boolean = false;
  tpPrice: number | null = null;
  slPrice: number | null = null;

  async ngOnInit() {
    this.refreshBalance();
  }

  refreshBalance() {
    this.simulatedTradeService.getVirtualBalance().subscribe(b => this.balance = b);
  }

  setOrderType(type: 'limit' | 'market' | 'stop-limit') {
    this.orderType = type;
  }

  onBuy() {
    this.executeTrade(SignalDirection.Long);
  }

  onSell() {
    this.executeTrade(SignalDirection.Short);
  }

  private executeTrade(side: SignalDirection) {
    if (!this.amount || this.amount <= 0) return;

    this.simulatedTradeService.openTrade({
      symbol: this.symbol,
      side: side,
      amount: this.amount,
      leverage: this.leverage,
      tpPrice: this.showTpSl ? (this.tpPrice ?? undefined) : undefined,
      slPrice: this.showTpSl ? (this.slPrice ?? undefined) : undefined
    }).subscribe({
      next: (res) => {
        console.log('Trade success:', res);
        this.refreshBalance();
        // SignalR will handle the toast and list update
      },
      error: (err) => {
        console.error('Trade error:', err);
      }
    });
  }
}
