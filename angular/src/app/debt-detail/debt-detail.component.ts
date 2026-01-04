import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { IonIcon } from '@ionic/angular/standalone';

interface ClaimStatus {
  label: string;
  color: string;
  bgColor: string;
}

@Component({
  selector: 'app-claim-detail',  // Puedes renombrar el selector si querés, o dejarlo
  standalone: true,
  imports: [
    CommonModule,
    CardContentComponent,
    GlassButtonComponent,
    IonIcon,
    RouterLink
  ],
  templateUrl: './debt-detail.component.html'  // Reutilizamos el mismo HTML con cambios
})
export class DebtDetailComponent {
  
  // Datos del análisis/reclamo (mock realista)
  claim = {
    name: 'Tarjeta Visa Banco Nación',
    potentialSavings: 457820,           // AHORA EL NÚMERO GRANDE ES EL AHORRO
    currentRate: 218,                   // TEA detectada
    legalRate: 120,                     // Máximo razonable según BCRA/ley
    originalAmount: 500000,
    abusiveInterest: 457820,
    minimumPayment: 85000,
    dueDate: '28 Ene 2026',
    abuseLevel: 'alta' as 'alta' | 'media' | 'baja'
  };

  // Historial del reclamo (en vez de pagos)
  claimHistory = [
    { id: 1, date: '02 Ene 2026', description: 'Subiste el resumen PDF', status: 'completado' },
    { id: 2, date: '02 Ene 2026', description: 'IA detectó tasa abusiva 218% TEA', status: 'completado' },
    { id: 3, date: '03 Ene 2026', description: 'Generaste carta documento', status: 'completado' },
    { id: 4, date: 'Pendiente', description: 'Envío de carta al banco', status: 'pendiente' },
  ];

  constructor(private router: Router) {}

  onBack() {
    this.router.navigate(['/']);
  }

  onGenerateLetter() {
    console.log('Generar carta personalizada (Pro feature)');
    // Aquí iría routerLink a generador o download PDF
  }

  onContactLawyer() {
    console.log('Conectar con abogado partner');
  }

  getAbuseLevelInfo(): ClaimStatus {
    switch (this.claim.abuseLevel) {
      case 'alta':
        return { label: 'ABUSIVA DETECTADA', color: '#EF4444', bgColor: 'rgba(239, 68, 68, 0.2)' };
      case 'media':
        return { label: 'TASA ELEVADA', color: '#FBBF24', bgColor: 'rgba(251, 191, 36, 0.2)' };
      default:
        return { label: 'NORMAL', color: '#00C47D', bgColor: 'rgba(0, 196, 125, 0.2)' };
    }
  }

  getHistoryStatusClass(status: 'completado' | 'pendiente') {
    return status === 'completado' 
      ? { circleClass: 'payment-circle-success', icon: 'checkmark' }
      : { circleClass: 'payment-circle-warning', icon: 'time-outline' };
  }
}