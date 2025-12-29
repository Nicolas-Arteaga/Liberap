import { Component, Input, Output, EventEmitter, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { SelectComponent } from 'src/shared/components/select/select.component';
import { PaymentChartComponent } from 'src/shared/components/payment-chart/payment-chart.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { IonIcon } from '@ionic/angular/standalone';
import { IconService } from 'src/shared/services/icon.service';
import { LabelComponent } from "src/shared/components/label/label.component";

interface FilterOption {
  value: string;
  label: string;
}

interface ChartData {
  month: string;
  amount: number;
}

// Define HistoryItem localmente ya que eliminaste el componente
interface HistoryItem {
  id: number;
  debtName: string;
  action: 'payment' | 'overdue' | 'installment' | 'negotiation';
  amount: number;
  date: string;
}

@Component({
  selector: 'app-history',
  standalone: true,
  imports: [
    CommonModule,
    CardContentComponent,
    SelectComponent,
    PaymentChartComponent,
    GlassButtonComponent,
    IonIcon,
    LabelComponent
  ],
  templateUrl: './history.component.html'
})
export class HistoryComponent {
  @Input() onBack?: () => void;
  @Output() back = new EventEmitter<void>();

  private iconService = inject(IconService);

  // Filtros
  movementType: string = 'all';
  dateRange: string = 'all';

  movementOptions: FilterOption[] = [
    { value: 'all', label: 'Todos los movimientos' },
    { value: 'payment', label: 'Pagos realizados' },
    { value: 'installment', label: 'Cuotas pagadas' },
    { value: 'negotiation', label: 'Negociaciones' },
    { value: 'overdue', label: 'Pagos vencidos' }
  ];

  dateOptions: FilterOption[] = [
    { value: 'all', label: 'Todo el tiempo' },
    { value: 'last7', label: 'Últimos 7 días' },
    { value: 'last30', label: 'Últimos 30 días' },
    { value: 'last90', label: 'Últimos 90 días' },
    { value: 'custom', label: 'Personalizado' }
  ];

  // Datos del gráfico
  chartData: ChartData[] = [
    { month: 'Jul', amount: 12000 },
    { month: 'Ago', amount: 18500 },
    { month: 'Sep', amount: 15000 },
    { month: 'Oct', amount: 22000 },
    { month: 'Nov', amount: 18000 }
  ];

  // Datos del historial
  historyItems: HistoryItem[] = [
    { id: 1, debtName: 'Tarjeta Visa', action: 'payment', amount: 20000, date: '15 Nov 2025' },
    { id: 2, debtName: 'Préstamo Personal', action: 'negotiation', amount: 0, date: '10 Nov 2025' },
    { id: 3, debtName: 'Tarjeta Mastercard', action: 'installment', amount: 8500, date: '05 Nov 2025' },
    { id: 4, debtName: 'Servicio de Cable', action: 'overdue', amount: 3200, date: '01 Nov 2025' },
    { id: 5, debtName: 'Tarjeta Visa', action: 'payment', amount: 18000, date: '20 Oct 2025' },
    { id: 6, debtName: 'Préstamo Personal', action: 'installment', amount: 15000, date: '15 Oct 2025' }
  ];

  // Historial filtrado
  get filteredItems(): HistoryItem[] {
    return this.historyItems.filter(item => {
      if (this.movementType !== 'all' && item.action !== this.movementType) {
        return false;
      }
      // Aquí iría la lógica de filtrado por fecha en una app real
      return true;
    });
  }

  // Estadísticas
  get totalPaid(): number {
    return this.historyItems
      .filter(item => item.action === 'payment' || item.action === 'installment')
      .reduce((sum, item) => sum + item.amount, 0);
  }

  get completedPayments(): number {
    return this.historyItems
      .filter(item => item.action === 'payment' || item.action === 'installment')
      .length;
  }

  constructor(private router: Router) {}

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  handleBack(): void {
    if (this.onBack) {
      this.onBack();
    } else {
      this.router.navigate(['/']);
    }
    this.back.emit();
  }

  formatCurrency(amount: number): string {
    return amount.toLocaleString('es-AR');
  }

  getPaymentStatusClass(action: 'payment' | 'overdue' | 'installment' | 'negotiation') {
  switch (action) {
    case 'payment':
    case 'installment':
      return {
        circleClass: 'payment-circle-success',
        textClass: 'text-success small fw-medium',
        icon: 'checkmark-circle-outline'
      };
    case 'overdue':
      return {
        circleClass: 'payment-circle-danger',
        textClass: 'text-danger small fw-medium',
        icon: 'close' 
      };
    case 'negotiation':
      return {
        circleClass: 'payment-circle-warning',
        textClass: 'text-warning small fw-medium',
        icon: 'people-outline'
      };
    default:
      return {
        circleClass: 'payment-circle-success',
        textClass: 'text-success small fw-medium',
        icon: 'checkmark-circle-outline'
      };
  }
}

  getPaymentStatusLabel(action: 'payment' | 'overdue' | 'installment' | 'negotiation'): string {
    switch (action) {
      case 'payment':
        return 'Pago realizado';
      case 'installment':
        return 'Cuota pagada';
      case 'overdue':
        return 'Pago vencido';
      case 'negotiation':
        return 'Negociación iniciada';
      default:
        return action;
    }
  }
}