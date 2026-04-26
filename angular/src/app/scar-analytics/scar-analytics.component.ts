import { Component, OnInit, OnDestroy, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ScarService } from '../proxy/trading/scar/scar.service';
import { ScarPredictionDto, ScarAccuracyDto } from '../proxy/trading/scar/models';
import { RouterModule } from '@angular/router';

@Component({
  selector: 'app-scar-analytics',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './scar-analytics.component.html',
  styleUrls: ['./scar-analytics.component.scss'],
})
export class ScarAnalyticsComponent implements OnInit, OnDestroy {
  private scarSvc = inject(ScarService);

  // State
  activeTab = signal<'system' | 'trader'>('system');
  isLoading = signal(false);
  autoRefresh = signal(false);
  
  // Data
  predictions = signal<ScarPredictionDto[]>([]);
  accuracy = signal<ScarAccuracyDto | null>(null);

  private refreshTimer: any;

  ngOnInit() {
    this.loadData();
  }

  ngOnDestroy() {
    this.stopAutoRefresh();
  }

  loadData() {
    this.isLoading.set(true);
    // Load Global Accuracy
    this.scarSvc.getAccuracy(undefined).subscribe({
      next: (acc) => this.accuracy.set(acc),
      error: (err) => console.error(err)
    });

    // Load Recent Predictions
    this.scarSvc.getPredictions(undefined, 50).subscribe({
      next: (preds) => {
        this.predictions.set(preds);
        this.isLoading.set(false);
      },
      error: (err) => {
        console.error(err);
        this.isLoading.set(false);
      }
    });
  }

  toggleAutoRefresh() {
    this.autoRefresh.set(!this.autoRefresh());
    if (this.autoRefresh()) {
      this.refreshTimer = setInterval(() => this.loadData(), 30000); // 30s
    } else {
      this.stopAutoRefresh();
    }
  }

  private stopAutoRefresh() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  }

  getHitRateColor(rate: number): string {
    if (rate >= 70) return '#00ff88'; // green
    if (rate >= 50) return '#ffdd00'; // yellow
    return '#ff4466'; // red
  }

  getRoiColor(roi: number): string {
    return roi > 0 ? '#00ff88' : '#ff4466';
  }

  getStatusBadge(status: string, roi: number, maxPrice: number | undefined, alertPrice: number) {
    if (status === 'pending') {
      return { class: 'badge-pending', icon: '⏳', text: 'PENDING' };
    }
    
    // Pattern logic
    if (this.activeTab() === 'system') {
      const ratio = maxPrice && alertPrice ? maxPrice / alertPrice : 0;
      if (ratio >= 2.0) {
         return { class: 'badge-hit', icon: '🎯', text: 'PATRÓN DETECTADO' };
      } else if (status === 'false_alarm') {
         return { class: 'badge-miss', icon: '❌', text: 'FALLO' };
      }
      return { class: 'badge-miss', icon: '❌', text: 'FALLO' };
    } 
    // Trader logic
    else {
      if (roi > 0.10) {
        return { class: 'badge-hit', icon: '💰', text: 'RENTABLE' };
      } else if (status === 'false_alarm') {
        return { class: 'badge-miss', icon: '📉', text: 'PÉRDIDA' };
      } else if (roi > 0) {
        return { class: 'badge-warn', icon: '➖', text: 'BREAKEVEN' };
      }
      return { class: 'badge-miss', icon: '📉', text: 'PÉRDIDA' };
    }
  }
}
