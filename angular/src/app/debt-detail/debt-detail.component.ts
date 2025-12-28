import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { IonIcon } from '@ionic/angular/standalone';

@Component({
  selector: 'app-debt-detail',
  standalone: true,
  imports: [
    CommonModule,
    CardContentComponent,
    GlassButtonComponent,
    IonIcon,
    RouterLink
  ],
  templateUrl: './debt-detail.component.html'
})
export class DebtDetailComponent {
  
  // Datos mock - igual que el React
  debt = {
    name: 'Tarjeta Visa Banco Nación',
    totalAmount: 87500,
    status: 'atrasada' as 'atrasada' | 'pendiente' | 'en-curso',
    dueDate: '28 Nov 2025',
    originalAmount: 75000,
    accumulatedInterest: 12500,
    minimumPayment: 15000,
    nextInstallment: 22000,
    daysRemaining: -5 // Negative = vencida
  };

  paymentHistory = [
    { 
      id: 1, 
      date: '15 Oct 2025', 
      amount: 20000,
      status: 'acreditado' as 'acreditado' | 'pendiente' | 'rechazado' 
    },
    { 
      id: 2, 
      date: '18 Sep 2025', 
      amount: 18500,
      status: 'acreditado' 
    },
    { 
      id: 3, 
      date: '12 Ago 2025', 
      amount: 25000,
      status: 'pendiente'  // Ejemplo de pago no acreditado
    },
    { 
      id: 4, 
      date: '05 Jul 2025', 
      amount: 15000,
      status: 'rechazado'  // Otro ejemplo
    }
  ];

  constructor(private router: Router) {}

  // Método para obtener valor absoluto
  abs(value: number): number {
    return Math.abs(value);
  }

  getStatusInfo() {
    switch (this.debt.status) {
      case 'atrasada':
        return {
          label: 'Atrasada',
          color: '#EF4444',
          bgColor: 'rgba(239, 68, 68, 0.15)'
        };
      case 'pendiente':
        return {
          label: 'Pendiente',
          color: '#FBBF24',
          bgColor: 'rgba(251, 191, 36, 0.15)'
        };
      default:
        return {
          label: 'En curso',
          color: '#00C47D',
          bgColor: 'rgba(0, 196, 125, 0.15)'
        };
    }
  }

  onBack() {
    this.router.navigate(['/']);  
  }

  onRegisterPayment() {
    console.log('Registrar pago');
  }

  onEditDebt() {
    console.log('Editar deuda');
  }

  onDeleteDebt() {
    if (confirm('¿Estás seguro de eliminar esta deuda?')) {
      console.log('Eliminar deuda');
      this.onBack();
    }
  }

  getPaymentStatusLabel(status: 'acreditado' | 'pendiente' | 'rechazado'): string {
  switch (status) {
    case 'acreditado':
      return 'Acreditado';
    case 'pendiente':
      return 'En proceso'; // Opción más profesional que "No acreditado"
    case 'rechazado':
      return 'Rechazado'; // O "Fallido", "No procesado"
    default:
      return status;
  }
}

getPaymentStatusClass(status: 'acreditado' | 'pendiente' | 'rechazado') {
  switch (status) {
    case 'acreditado':
      return {
        circleClass: 'payment-circle-success',
        textClass: 'text-success small fw-medium',
        icon: 'checkmark'
      };
    case 'pendiente':
      return {
        circleClass: 'payment-circle-warning',
        textClass: 'text-warning small fw-medium',
        icon: 'time-outline' // O 'hourglass-outline', 'clock-outline'
      };
    case 'rechazado':
      return {
        circleClass: 'payment-circle-danger',
        textClass: 'text-danger small fw-medium',
        icon: 'close' // O 'alert-circle-outline'
      };
    default:
      return {
        circleClass: 'payment-circle-success',
        textClass: 'text-success small fw-medium',
        icon: 'checkmark'
      };
  }
}
}