import { Component, EventEmitter, Input, Output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { flame, trendingUp, trendingDown } from 'ionicons/icons';
import { PairBotInfo } from '../../models/bot.models';

@Component({
  selector: 'app-pair-list',
  standalone: true,
  imports: [CommonModule, IonIcon],
  templateUrl: './pair-list.component.html',
  styleUrls: ['./pair-list.component.scss']
})
export class PairListComponent {
  constructor() {
    addIcons({ flame, trendingUp, trendingDown });
  }
  @Output() pairSelected = new EventEmitter<PairBotInfo>();
  @Output() orderCreated = new EventEmitter<{ pair: PairBotInfo, direction: 'LONG' | 'SHORT' }>();

  selectedSymbol = signal<string | null>(null);
  lastUpdatedSymbol = signal<string | null>(null);

  private updateTimer: any;

  // We detect changes in the input array to trigger the "pulse" animation
  private _pairs: PairBotInfo[] = [];
  @Input() set pairs(value: PairBotInfo[]) {
    if (!value) {
      this._pairs = [];
      return;
    }
    
    // If we have previous data, detect what changed to trigger animations
    if (this._pairs.length > 0) {
      value.forEach(newPair => {
        const oldPair = this._pairs.find(p => p.symbol === newPair.symbol);
        if (oldPair && oldPair.score !== newPair.score) {
          this.triggerUpdateVisual(newPair.symbol);
        }
      });
    }
    this._pairs = [...value];
  }
  get pairs() { return this._pairs; }

  formatSymbol(symbol: string): string {
    // Convierte "BTC/USDT:USDT" -> "BTC/USDT"
    if (!symbol) return '';
    return symbol.includes(':') ? symbol.split(':')[0] : symbol;
  }

  private triggerUpdateVisual(symbol: string) {
    this.lastUpdatedSymbol.set(symbol);
    if (this.updateTimer) clearTimeout(this.updateTimer);
    this.updateTimer = setTimeout(() => this.lastUpdatedSymbol.set(null), 2000);
  }

  selectPair(pair: PairBotInfo) {
    this.selectedSymbol.set(pair.symbol);
    this.pairSelected.emit(pair);
  }

  createOrder(event: Event, pair: PairBotInfo, direction: 'LONG' | 'SHORT') {
    event.stopPropagation();
    this.orderCreated.emit({ pair, direction });
  }

  trackBySymbol(index: number, pair: PairBotInfo): string {
    return pair.symbol;
  }

  getScoreColor(score: number): string {
    if (score >= 85) return '#00C47D';
    if (score >= 70) return '#F5A623';
    return '#EF4444';
  }

  getScoreFillGradient(score: number): string {
    if (score >= 85) return 'linear-gradient(90deg, #00C47D 0%, #10B981 100%)';
    if (score >= 70) return 'linear-gradient(90deg, #F5A623 0%, #FF8C00 100%)';
    return 'linear-gradient(90deg, #EF4444 0%, #B91C1C 100%)';
  }

  getBiasColor(bias: string, alpha: number = 1): string {
    if (bias === 'Bullish') return `rgba(0, 196, 125, ${alpha})`;
    if (bias === 'Bearish') return `rgba(239, 68, 68, ${alpha})`;
    return `rgba(255, 255, 255, ${alpha * 0.5})`;
  }
}

