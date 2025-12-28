import { Component, Input, Output, EventEmitter, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { InputComponent } from 'src/shared/components/input/input.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { LabelComponent } from 'src/shared/components/label/label.component';
import { SelectComponent } from 'src/shared/components/select/select.component';
import { IonIcon } from '@ionic/angular/standalone';
import { ToggleComponent } from 'src/shared/components/toggle/toggle.component';
import { IconService } from 'src/shared/services/icon.service';

interface DebtTypeOption {
  value: string;
  label: string;
}

interface ReminderDaysOption {
  value: string;
  label: string;
}

export interface DebtFormData {
  name: string;
  amount: string;
  dueDate: string;
  type: string;
  minimumPayment: string;
  reminderEnabled: boolean;
  reminderDays: string;
}

@Component({
  selector: 'app-add-debt',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    CardContentComponent,
    InputComponent,
    GlassButtonComponent,
    LabelComponent,
    SelectComponent,
    IonIcon,
    ToggleComponent
  ],
  templateUrl: './add-debt.component.html'
})
export class AddDebtComponent {
  @Input() onBack?: () => void;
  @Input() onSave?: (debtData: DebtFormData) => void;
  @Output() back = new EventEmitter<void>();
  @Output() save = new EventEmitter<DebtFormData>();

  private iconService = inject(IconService);

  formData: DebtFormData = {
    name: '',
    amount: '',
    dueDate: '',
    type: '',
    minimumPayment: '',
    reminderEnabled: false,
    reminderDays: '3'
  };

  debtTypeOptions: DebtTypeOption[] = [
    { value: 'credit-card', label: 'Tarjeta de crédito' },
    { value: 'loan', label: 'Préstamo' },
    { value: 'service', label: 'Servicio' },
    { value: 'tax', label: 'Impuesto' },
    { value: 'other', label: 'Otro' }
  ];

  reminderDaysOptions: ReminderDaysOption[] = [
    { value: '1', label: '1 día antes' },
    { value: '3', label: '3 días antes' },
    { value: '5', label: '5 días antes' },
    { value: '7', label: '7 días antes' },
    { value: '15', label: '15 días antes' }
  ];

  constructor(private router: Router) {}

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  handleSave(): void {
    // Validación
    if (!this.formData.name.trim()) {
      alert('Por favor ingresa el nombre de la deuda');
      return;
    }
    if (!this.formData.amount.trim()) {
      alert('Por favor ingresa el monto total');
      return;
    }
    if (!this.formData.dueDate) {
      alert('Por favor selecciona la fecha de vencimiento');
      return;
    }
    if (!this.formData.type) {
      alert('Por favor selecciona el tipo de deuda');
      return;
    }

    console.log('Guardando deuda:', this.formData);

    if (this.onSave) {
      this.onSave(this.formData);
    }
    this.save.emit(this.formData);

    this.navigateBack();  
  }

  handleCancel(): void {
    if (this.formData.name || this.formData.amount) {
      if (window.confirm('¿Deseas descartar los cambios?')) {
        this.navigateBack();
      }
    } else {
      this.navigateBack();
    }
  }

  private navigateBack(): void {
    if (this.onBack) {
      this.onBack();
    } else {
      this.router.navigate(['/']);
    }
    this.back.emit();
  }

  getIconForField(field: string): string {
    const icons: { [key: string]: string } = {
      name: 'document-text-outline',
      amount: 'cash-outline',
      dueDate: 'calendar-outline',
      type: 'pricetag-outline',
      minimumPayment: 'card-outline',
      reminder: 'notifications-outline'
    };
    return icons[field] || 'help-outline';
  }
}