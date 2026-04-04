import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { terminalOutline, pulseOutline, checkmarkCircleOutline, alertCircleOutline } from 'ionicons/icons';
import { BotSignalRService } from '../../services/bot-signalr.service';

@Component({
  selector: 'app-bot-activity-feed',
  standalone: true,
  imports: [CommonModule, IonIcon],
  templateUrl: './bot-activity-feed.component.html',
  styleUrls: ['./bot-activity-feed.component.scss']
})
export class BotActivityFeedComponent {
  private botSignalRService = inject(BotSignalRService);
  
  logs = this.botSignalRService.botLogs;

  constructor() {
    addIcons({ terminalOutline, pulseOutline, checkmarkCircleOutline, alertCircleOutline });
  }

  getIcon(log: string): string {
    if (log.includes('🔍')) return 'pulse-outline';
    if (log.includes('✅')) return 'checkmark-circle-outline';
    if (log.includes('❌')) return 'alert-circle-outline';
    return 'terminal-outline';
  }

  trackByLog(index: number, log: string): string {
    return `${index}-${log}`;
  }
}
