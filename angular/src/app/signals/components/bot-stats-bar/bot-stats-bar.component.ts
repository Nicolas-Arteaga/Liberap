import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { settingsOutline, statsChartOutline, pulseOutline, flashOutline, stopwatchOutline } from 'ionicons/icons';
import { FreqtradePollService } from '../../../services/freqtrade-poll.service';

@Component({
  selector: 'app-bot-stats-bar',
  standalone: true,
  imports: [CommonModule, IonIcon],
  template: `
    <div class="stats-bar-container">
      <!-- Status -->
      <div class="stat-item main-status" *ngIf="pollService.status$ | async as status">
        <ion-icon name="pulse-outline" [class.active]="status.isRunning" class="icon-bg"></ion-icon>
        <div class="stat-content">
          <span class="label">ESTADO MOTOR</span>
          <span class="value" [class.success]="status.isRunning" [class.danger]="!status.isRunning">
            {{ status.isRunning ? 'RUNNING' : 'STOPPED' }}
          </span>
        </div>
      </div>

      <div class="stat-divider"></div>

      <!-- Strategy Info -->
      <div class="stat-item">
        <div class="stat-content">
          <span class="label">ESTRATEGIA</span>
          <span class="value">VergeFreqAI</span>
        </div>
        <div class="indicator-dot blue"></div>
      </div>

      <div class="stat-divider"></div>

      <!-- Profit Metrics -->
      <div class="stat-item pnl-total" *ngIf="pollService.profit$ | async as profit">
        <div class="stat-content text-right">
          <span class="label">BALANCE PROFIT</span>
          <span class="value" [class.success]="profit.totalProfit >= 0" [class.danger]="profit.totalProfit < 0">
            {{ profit.totalProfit >= 0 ? '+' : '' }}{{ profit.totalProfit | number:'1.2-2' }} USDT
          </span>
        </div>
      </div>

      <div class="stat-item" *ngIf="pollService.profit$ | async as profit">
        <div class="stat-content text-right">
          <span class="label">WIN RATE</span>
          <span class="value fw-bold">{{ (profit.winRate * 100) | number:'1.1-1' }}%</span>
        </div>
      </div>
      
      <div class="stat-item" *ngIf="pollService.profit$ | async as profit">
        <div class="stat-content text-right">
          <span class="label">TRADES</span>
          <span class="value">{{ profit.totalTrades }}</span>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .stats-bar-container {
      display: flex;
      align-items: center;
      background: rgba(18, 22, 33, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      padding: 12px 24px;
      gap: 24px;
      color: white;
      backdrop-filter: blur(10px);
    }

    .stat-item {
      display: flex;
      align-items: center;
      gap: 12px;

      .icon-bg {
        font-size: 20px;
        color: #8b949e;
        &.active { color: #22c55e; }
      }

      .stat-content {
        display: flex;
        flex-direction: column;

        .label {
          font-size: 10px;
          color: #8b949e;
          text-transform: uppercase;
          letter-spacing: 1px;
          margin-bottom: 2px;
        }

        .value {
          font-size: 14px;
          font-weight: 700;
          &.success { color: #22c55e; }
          &.danger { color: #ef4444; }
        }
      }

      .indicator-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-left: 4px;
        &.blue { background: #3b82f6; box-shadow: 0 0 8px rgba(59, 130, 246, 0.5); }
      }
    }

    .stat-divider {
      width: 1px;
      height: 20px;
      background: rgba(255, 255, 255, 0.1);
    }

    .text-right { text-align: right; }
    .pnl-total { margin-left: auto; }
    .fw-bold { font-weight: 800; }
  `]
})
export class BotStatsBarComponent {
  public pollService = inject(FreqtradePollService);

  constructor() {
    addIcons({ settingsOutline, statsChartOutline, pulseOutline, flashOutline, stopwatchOutline });
  }
}
