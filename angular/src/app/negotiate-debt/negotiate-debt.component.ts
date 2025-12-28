import { Component, Input, Output, EventEmitter, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { IonIcon } from '@ionic/angular/standalone';
import { IconService } from 'src/shared/services/icon.service';

interface SelectedDebt {
  id: number;
  name: string;
  amount: number;
  status: 'overdue' | 'pending' | 'current';
  lastUpdate: string;
}

interface StatusInfo {
  label: string;
  color: string;
  bgColor: string;
}

interface NegotiationOptionData {
  icon: string;
  title: string;
  description: string;
  action: () => void;
}

@Component({
  selector: 'app-negotiate-debt',
  standalone: true,
  imports: [
    CommonModule,
    CardIconComponent,
    GlassButtonComponent,
    IonIcon
  ],
  templateUrl: './negotiate-debt.component.html'
})
export class NegotiateDebtComponent {
  @Input() onBack?: () => void;
  @Input() onViewPaymentPlan?: () => void;
  @Input() onViewOneTimeOffer?: () => void;
  @Input() onContactAdvisor?: () => void;
  
  @Output() back = new EventEmitter<void>();
  @Output() viewPaymentPlan = new EventEmitter<void>();
  @Output() viewOneTimeOffer = new EventEmitter<void>();
  @Output() contactAdvisor = new EventEmitter<void>();

  private iconService = inject(IconService);

  // Mock data
  selectedDebt: SelectedDebt = {
    id: 1,
    name: 'Tarjeta Visa',
    amount: 45000,
    status: 'overdue',
    lastUpdate: '28 Nov 2025'
  };

  negotiationOptions: NegotiationOptionData[] = [
    {
      icon: 'calendar-outline',
      title: 'Plan de pagos',
      description: 'Dividir la deuda en cuotas accesibles según tu capacidad de pago',
      action: () => this.handlePaymentPlan()
    },
    {
      icon: 'cash-outline',
      title: 'Oferta de pago único',
      description: 'Ofrecer un pago total con descuento para liquidar la deuda',
      action: () => this.handleOneTimeOffer()
    },
    {
      icon: 'chatbubble-outline',
      title: 'Hablar con un asesor',
      description: 'Contactar soporte para evaluar alternativas personalizadas',
      action: () => this.handleContactAdvisor()
    }
  ];

  constructor(private router: Router) {}

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  getStatusInfo(): StatusInfo {
    switch (this.selectedDebt.status) {
      case 'overdue':
        return {
          label: 'Vencida',
          color: '#EF4444',
          bgColor: 'rgba(239, 68, 68, 0.15)'
        };
      case 'pending':
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

  handleBack(): void {
    if (this.onBack) {
      this.onBack();
    } else {
      this.router.navigate(['/']);
    }
    this.back.emit();
  }

  handlePaymentPlan(): void {
    console.log('Ir a plan de pagos');
    if (this.onViewPaymentPlan) {
      this.onViewPaymentPlan();
    }
    this.viewPaymentPlan.emit();
  }

  handleOneTimeOffer(): void {
    console.log('Ir a oferta de pago único');
    if (this.onViewOneTimeOffer) {
      this.onViewOneTimeOffer();
    }
    this.viewOneTimeOffer.emit();
  }

  handleContactAdvisor(): void {
    console.log('Contactar asesor');
    if (this.onContactAdvisor) {
      this.onContactAdvisor();
    }
    this.contactAdvisor.emit();
  }

  handleContinue(): void {
    console.log('Continuar con negociación');
    // Aquí iría la lógica para continuar
  }

  formatCurrency(amount: number): string {
    return amount.toLocaleString('es-AR');
  }
}