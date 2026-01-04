import { Component, inject, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { ToggleComponent } from 'src/shared/components/toggle/toggle.component';
import { IconService } from 'src/shared/services/icon.service';
import { IonIcon } from '@ionic/angular/standalone';

@Component({
  selector: 'app-add-debt',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    CardContentComponent,
    GlassButtonComponent,
    ToggleComponent,
    IonIcon
  ],
  templateUrl: './add-debt.component.html'
})
export class AddDebtComponent {
  private iconService = inject(IconService);
  private router = inject(Router);

  @ViewChild('fileInput') fileInput!: ElementRef<HTMLInputElement>;

  selectedFile: File | null = null;
  reminderEnabled = true;

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();
  }

  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      this.selectedFile = input.files[0];
    }
  }

  handleAnalyze() {
    if (!this.selectedFile) {
      alert('Por favor, subí tu resumen bancario');
      return;
    }
    console.log('Analizando:', this.selectedFile.name);
    this.router.navigate(['/claim-detail']);
  }

  handleCancel() {
    this.router.navigate(['/']);
  }
}