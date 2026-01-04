import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { InputComponent } from 'src/shared/components/input/input.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { LabelComponent } from 'src/shared/components/label/label.component';
import { TextareaComponent } from 'src/shared/components/textarea/textarea.component';
import { IonIcon } from '@ionic/angular/standalone';
import { IconService } from 'src/shared/services/icon.service';

interface LetterForm {
  fullName: string;
  dni: string;
  address: string;
  city: string;
  bankName: string;
  cardNumber: string;  // Últimos 4 dígitos o parcial
  additionalNotes: string;
}

@Component({
  selector: 'app-generate-letter',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    CardContentComponent,
    InputComponent,
    GlassButtonComponent,
    LabelComponent,
    TextareaComponent,
    IonIcon
  ],
  templateUrl: './generate-letter.component.html'
})
export class GenerateLetterComponent {
  private iconService = inject(IconService);
  private router = inject(Router);

  // Datos del reclamo (vendrán del servicio o state - mock por ahora)
  claim = {
    bankName: 'Banco Nación',
    cardType: 'Tarjeta Visa',
    currentRate: 218,
    legalRate: 120,
    potentialSavings: 457820,
    summaryDate: '28 Ene 2026'
  };

  isProUser = false;  // Conectar con tu auth/subscription service

  formData: LetterForm = {
    fullName: '',
    dni: '',
    address: '',
    city: '',
    bankName: this.claim.bankName,
    cardNumber: '',
    additionalNotes: ''
  };

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  onBack() {
    this.router.navigate(['/debt-detail']);  // o el ID del reclamo
  }

  onGeneratePreview() {
    console.log('Generando preview de carta con datos:', this.formData);
    // Aquí llamarías a tu servicio que genera el HTML/PDF
  }

  onDownloadPDF() {
    if (!this.isProUser) {
      // Upsell
      this.router.navigate(['/plans']);
      return;
    }
    console.log('Descargando PDF personalizado');
    // Implementar html2pdf.js o similar
  }
}