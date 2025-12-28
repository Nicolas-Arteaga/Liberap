import { Component, Input, Output, EventEmitter, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { InputComponent } from 'src/shared/components/input/input.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { LabelComponent } from 'src/shared/components/label/label.component';
import { IonIcon } from "@ionic/angular/standalone";
import { SelectComponent } from 'src/shared/components/select/select.component';
import { TextareaComponent } from 'src/shared/components/textarea/textarea.component';
import { IconService } from 'src/shared/services/icon.service';

interface PaymentMethodOption {
  value: string;
  label: string;
}

interface DebtInfo {
  name: string;
  totalAmount: number;
  status: 'overdue' | 'pending' | 'current';
  nextDueDate: string;
}

interface FormData {
  amount: string;
  paymentDate: string;
  paymentMethod: string;
  note: string;
}

@Component({
  selector: 'app-register-payment',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    CardIconComponent,
    CardContentComponent,
    InputComponent,
    GlassButtonComponent,
    LabelComponent,
    IonIcon,
    SelectComponent,
    TextareaComponent
],
  templateUrl: './register-payment.component.html',
  styleUrls: ['./register-payment.component.scss']
})
export class RegisterPaymentComponent {
  @Input() onBack?: () => void;
  @Input() onSuccess?: () => void;
  @Output() back = new EventEmitter<void>();
  @Output() success = new EventEmitter<void>();
  private iconService = inject(IconService);  

  // Mock data
  debtInfo: DebtInfo = {
    name: 'Tarjeta Visa',
    totalAmount: 45000,
    status: 'overdue',
    nextDueDate: '15 Dic 2025'
  };

  formData: FormData = {
    amount: '',
    paymentDate: '',
    paymentMethod: '',
    note: ''
  };

  constructor(private router: Router) {}

  ngOnInit(): void {
    console.log('Opciones del select:', this.paymentMethodOptions);  
  }

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();  
  }

  paymentMethodOptions: PaymentMethodOption[] = [
    { value: 'bank-transfer', label: 'Transferencia bancaria' },
    { value: 'debit-card', label: 'Tarjeta de débito' },
    { value: 'credit-card', label: 'Tarjeta de crédito' },
    { value: 'cash', label: 'Efectivo' },
    { value: 'other', label: 'Otro' }
  ];

  getStatusInfo() {
    switch (this.debtInfo.status) {
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
          label: 'Al día',
          color: '#00C47D',
          bgColor: 'rgba(0, 196, 125, 0.15)'
        };
    }
  }

  handleBack(): void {
    if (this.onBack) {
      this.onBack();
    } else {
      this.router.navigate(['/debt-detail']);
    }
    this.back.emit();
  }

  handleSubmit(): void {
    // Validación
    if (!this.formData.amount.trim()) {
      alert('Por favor ingresa el monto pagado');
      return;
    }
    if (!this.formData.paymentDate) {
      alert('Por favor selecciona la fecha del pago');
      return;
    }
    if (!this.formData.paymentMethod) {
      alert('Por favor selecciona el método de pago');
      return;
    }

    console.log('Registrando pago:', this.formData);
    
    // Simular llamada API
    setTimeout(() => {
      if (this.onSuccess) {
        this.onSuccess();
      } else {
        this.handleBack();
      }
      // toast.success('Pago registrado exitosamente');
    }, 1500);
  }

  formatCurrency(amount: number): string {
    return amount.toLocaleString('es-AR');
  }

  getStatusIcon(): string {
    switch (this.debtInfo.status) {
      case 'overdue': return 'alert-circle-outline';
      case 'pending': return 'time-outline';
      default: return 'checkmark-circle-outline';
    }
  }

  getCardIcon(): string {
    return 'card-outline';
  }
  
  goToRegisterPayment() {
    this.router.navigate(['/register-payment']);
  }
}