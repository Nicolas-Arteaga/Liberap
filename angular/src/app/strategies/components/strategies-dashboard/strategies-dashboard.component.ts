import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { StrategyProfileService } from '../../services/strategy-profile.service';
import { StrategyProfileDto } from '../../../proxy/trading/dtos/models';
import { StrategyCardComponent } from '../strategy-card/strategy-card.component';
import { GlassButtonComponent } from '../../../../shared/components/glass-button/glass-button.component';
import { IonIcon } from '@ionic/angular/standalone';
import { finalize } from 'rxjs/operators';

@Component({
  selector: 'app-strategies-dashboard',
  standalone: true,
  imports: [CommonModule, StrategyCardComponent, GlassButtonComponent, IonIcon],
  templateUrl: './strategies-dashboard.component.html',
  styleUrls: ['./strategies-dashboard.component.scss']
})
export class StrategiesDashboardComponent implements OnInit {
  private service = inject(StrategyProfileService);
  private router = inject(Router);

  profiles: StrategyProfileDto[] = [];
  isLoading = false;

  ngOnInit() {
    this.loadProfiles();
  }

  loadProfiles() {
    this.isLoading = true;
    this.service.getAll()
      .pipe(finalize(() => this.isLoading = false))
      .subscribe(data => this.profiles = data);
  }

  onNewStrategy() {
    this.router.navigate(['/strategies/new']);
  }

  onEdit(id: string) {
    this.router.navigate(['/strategies/edit', id]);
  }

  onDuplicate(id: string) {
    this.service.duplicate(id).subscribe(() => this.loadProfiles());
  }

  onDelete(id: string) {
    if (confirm('¿Estás seguro de eliminar este perfil de estrategia?')) {
      this.service.delete(id).subscribe(() => this.loadProfiles());
    }
  }

  onToggle(id: string) {
    this.service.toggleActive(id).subscribe(() => {
      const p = this.profiles.find(x => x.id === id);
      if (p) p.isActive = !p.isActive;
    });
  }

  onViewPerformance(id: string) {
    this.router.navigate(['/strategies/performance', id]);
  }

  get activeProfilesCount() {
    return this.profiles.filter(p => p.isActive).length;
  }

  get totalNetPnL() {
    return this.profiles.reduce((acc, curr) => acc + (curr.netPnL || 0), 0);
  }
}
