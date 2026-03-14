import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IonIcon } from '@ionic/angular/standalone';
import { LeverageModalComponent } from '../leverage-modal/leverage-modal.component';

@Component({
  selector: 'app-trading-panel',
  standalone: true,
  imports: [CommonModule, FormsModule, IonIcon, LeverageModalComponent],
  templateUrl: './trading-panel.component.html',
  styleUrls: ['./trading-panel.component.scss']
})
export class TradingPanelComponent {
  @Input() symbol: string = 'BTCUSDT';
  @Input() balance: number = 0;
  
  orderType: 'limit' | 'market' | 'stop-limit' = 'limit';
  
  price: number = 71039.3;
  stopPrice: number = 0;
  amount: number | null = null;
  leverage: number = 5;
  marginType: 'Cruzado' | 'Aislado' = 'Cruzado';
  showLeverageModal: boolean = false;

  setOrderType(type: 'limit' | 'market' | 'stop-limit') {
    this.orderType = type;
  }

  onBuy() {
    console.log('Buy order:', { type: this.orderType, price: this.price, amount: this.amount });
  }

  onSell() {
    console.log('Sell order:', { type: this.orderType, price: this.price, amount: this.amount });
  }
}
