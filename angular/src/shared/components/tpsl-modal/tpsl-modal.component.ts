import { Component, Input, Output, EventEmitter, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IonIcon } from '@ionic/angular/standalone';
import { SimulatedTradeDto } from 'src/app/proxy/trading/dtos/models';
import { SimulatedTradeService } from 'src/app/proxy/trading/simulated-trade.service';

@Component({
  selector: 'app-tpsl-modal',
  standalone: true,
  imports: [CommonModule, FormsModule, IonIcon],
  templateUrl: './tpsl-modal.component.html',
  styleUrls: ['./tpsl-modal.component.scss']
})
export class TpSlModalComponent implements OnInit {
  @Input() trade!: SimulatedTradeDto;
  @Output() close = new EventEmitter<void>();
  @Output() updated = new EventEmitter<void>();

  tpPrice: number | null = null;
  slPrice: number | null = null;
  isSaving = false;

  constructor(private simulatedTradeService: SimulatedTradeService) {}

  ngOnInit() {
    this.tpPrice = this.trade.tpPrice;
    this.slPrice = this.trade.slPrice;
  }

  get estimatedTpPnl(): number {
    if (!this.tpPrice) return 0;
    const diff = this.trade.side === 0 ? this.tpPrice - this.trade.entryPrice : this.trade.entryPrice - this.tpPrice;
    return (diff / this.trade.entryPrice) * this.trade.amount * this.trade.leverage;
  }

  get estimatedSlPnl(): number {
    if (!this.slPrice) return 0;
    const diff = this.trade.side === 0 ? this.slPrice - this.trade.entryPrice : this.trade.entryPrice - this.slPrice;
    return (diff / this.trade.entryPrice) * this.trade.amount * this.trade.leverage;
  }

  confirm() {
    this.isSaving = true;
    this.simulatedTradeService.updateTpSl(this.trade.id, {
      tpPrice: this.tpPrice,
      slPrice: this.slPrice
    }).subscribe({
      next: () => {
        this.isSaving = false;
        this.updated.emit();
        this.close.emit();
      },
      error: (err) => {
        console.error('Error updating TP/SL', err);
        this.isSaving = false;
      }
    });
  }
}
