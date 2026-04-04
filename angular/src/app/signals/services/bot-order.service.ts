import { Injectable, signal, computed, inject } from '@angular/core';
import { SimulatedOrder, PairBotInfo, BotStatus, StrategyType } from '../models/bot.models';
import { MarketDataService } from '../../proxy/trading/market-data.service';

@Injectable({
  providedIn: 'root'
})
export class BotOrderService {
  private _orders = signal<SimulatedOrder[]>([]);
  private marketDataService = inject(MarketDataService);

  // Public readonly view
  public orders = this._orders.asReadonly();

  // Selected Order for the Control Panel
  public selectedOrderId = signal<string | null>(null);
  
  public selectedOrder = computed(() => 
    this._orders().find(o => o.id === this.selectedOrderId()) || null
  );

  public totalPnL = computed(() => 
    this._orders().reduce((acc, o) => acc + o.pnl, 0)
  );

  public totalPnLPercent = computed(() => {
    const totalCapital = this._orders().reduce((acc, o) => acc + o.capital, 0);
    if (totalCapital === 0) return 0;
    return (this.totalPnL() / totalCapital) * 100;
  });

  constructor() {
    // Initial mock bots to match the mockup image
    this._orders.set([
      {
        id: '1',
        name: 'Bot #1',
        symbol: 'SIRENUSDT',
        type: 'Scalping',
        direction: 'LONG',
        status: 'Running',
        entryTime: new Date(),
        entryPrice: 0.19265,
        currentPrice: 0.19961,
        entryScore: 78,
        prediction: 0.05,
        atr: 1.2,
        sl: 0.5,
        tp: 0.8,
        leverage: 10,
        capital: 100,
        pnl: 12.00,
        pnlPercent: 2.1
      },
      {
        id: '2',
        name: 'Bot #2',
        symbol: 'BTCUSDT',
        type: 'Grid',
        direction: 'SHORT',
        status: 'Paused',
        entryTime: new Date(),
        entryPrice: 65000,
        currentPrice: 65100,
        entryScore: 45,
        prediction: -0.02,
        atr: 0.8,
        sl: 1.0,
        tp: 2.0,
        leverage: 5,
        capital: 500,
        pnl: -3.00,
        pnlPercent: -0.5
      },
      {
        id: '3',
        name: 'Bot #3',
        symbol: 'ETHUSDT',
        type: 'DCA',
        direction: 'LONG',
        status: 'Running',
        entryTime: new Date(),
        entryPrice: 3500,
        currentPrice: 3510,
        entryScore: 60,
        prediction: 0.03,
        atr: 1.5,
        sl: 2.0,
        tp: 5.0,
        leverage: 3,
        capital: 1000,
        pnl: 5.00,
        pnlPercent: 0.4
      }
    ]);

    this.selectedOrderId.set('1');

    // Start a simple PnL simulation loop
    setInterval(() => this.simulatePnLUpdate(), 3000);
  }

  createBot(config: {
    pair: PairBotInfo,
    type: StrategyType,
    capital: number,
    leverage: number,
    tp: number,
    sl: number,
    direction: 'LONG' | 'SHORT'
  }) {
    const newOrder: SimulatedOrder = {
      id: crypto.randomUUID(),
      name: `Bot #${this._orders().length + 1}`,
      symbol: config.pair.symbol,
      type: config.type,
      direction: config.direction,
      status: 'Running',
      entryTime: new Date(),
      entryPrice: 100, // Placeholder, would fetch real price
      currentPrice: 100,
      entryScore: config.pair.score,
      prediction: config.pair.prediction,
      atr: config.pair.atr,
      sl: config.sl,
      tp: config.tp,
      leverage: config.leverage,
      capital: config.capital,
      pnl: 0,
      pnlPercent: 0
    };

    this._orders.update(orders => [newOrder, ...orders]);
    if (!this.selectedOrderId()) {
      this.selectedOrderId.set(newOrder.id);
    }
  }

  pauseBot(id: string) {
    this._orders.update(orders => orders.map(o => 
      o.id === id ? { ...o, status: o.status === 'Paused' ? 'Running' : 'Paused' as BotStatus } : o
    ));
  }

  stopBot(id: string) {
    this._orders.update(orders => orders.map(o => 
      o.id === id ? { ...o, status: 'Stopped' as BotStatus } : o
    ));
  }

  closeBot(id: string) {
    this._orders.update(orders => orders.filter(o => o.id !== id));
    if (this.selectedOrderId() === id) {
      this.selectedOrderId.set(this._orders().length > 0 ? this._orders()[0].id : null);
    }
  }

  selectBot(id: string) {
    this.selectedOrderId.set(id);
  }

  private simulatePnLUpdate() {
    this._orders.update(orders => orders.map(o => {
      if (o.status !== 'Running') return o;
      
      // Random walk for PnL simulation
      const change = (Math.random() - 0.48) * 2; // Slightly biased to positive
      const newPnL = o.pnl + (o.capital * (change / 100));
      const newPercent = (newPnL / o.capital) * 100;
      
      return {
        ...o,
        pnl: newPnL,
        pnlPercent: newPercent,
        currentPrice: o.entryPrice * (1 + (newPercent / 100 / o.leverage))
      };
    }));
  }
}
