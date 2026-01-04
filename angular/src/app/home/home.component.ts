import { Component, AfterViewInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { IconService } from 'src/shared/services/icon.service';
import { RouterLink } from '@angular/router';

// Reutilizamos la misma interfaz, pero ahora representa un análisis/reclamo
interface RecentAnalysis {
  name: string;          // Nombre del banco/tarjeta
  amount: number;        // Ahorro potencial detectado
  icon: string;
  status: 'abusiva' | 'elevada' | 'normal';  // Nuevo status visual
}

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [
    CommonModule,
    CardContentComponent,
    CardIconComponent,
    GlassButtonComponent,
    RouterLink
  ],
  templateUrl: './home.component.html'
})
export class HomeComponent implements AfterViewInit {
  private iconService = inject(IconService);

  // Estado del usuario (conectarás después con servicio real)
  hasAnalyses = false;                    // false = usuario nuevo
  totalPotentialSavings = 0;              // Para dashboard superior

  // Mock temporal → después vendrá del servicio
  recentAnalyses: RecentAnalysis[] = [
    { name: 'Tarjeta Visa Banco Nación', amount: 457820, icon: 'card-outline', status: 'abusiva' },
    { name: 'Préstamo Personal Galicia', amount: 312000, icon: 'cash-outline', status: 'elevada' },
    { name: 'Tarjeta Mastercard Macro', amount: 189500, icon: 'card-outline', status: 'abusiva' },
  ];

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
    this.updateDashboard();
  }

  private updateDashboard() {
    if (this.recentAnalyses.length > 0) {
      this.hasAnalyses = true;
      this.totalPotentialSavings = this.recentAnalyses.reduce((sum, a) => sum + a.amount, 0);
    }
  }

  getStatusLabel(status: 'abusiva' | 'elevada' | 'normal'): string {
    switch (status) {
      case 'abusiva': return 'Abusiva';
      case 'elevada': return 'Elevada';
      case 'normal': return 'Normal';
      default: return '';
    }
  }

  getStatusColor(status: 'abusiva' | 'elevada' | 'normal'): 'danger' | 'warning' | 'success' {
    switch (status) {
      case 'abusiva': return 'danger';
      case 'elevada': return 'warning';
      case 'normal': return 'success';
      default: return 'success';
    }
  }
}