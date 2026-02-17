import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonIcon } from '@ionic/angular/standalone';
import { GlassButtonComponent } from '../glass-button/glass-button.component';

@Component({
  selector: 'app-dialog',
  standalone: true,
  imports: [CommonModule, IonIcon, GlassButtonComponent],
  templateUrl: './dialog.component.html'
})
export class DialogComponent {
  @Input() title: string = '';
  @Input() variant: 'success' | 'warning' | 'danger' | 'info' = 'info';
  @Output() dismiss = new EventEmitter<void>();

  getIcon(): string {
    switch (this.variant) {
      case 'success': return 'checkmark-circle-outline';
      case 'warning': return 'warning-outline';
      case 'danger': return 'alert-circle-outline';
      case 'info': return 'information-circle-outline';
      default: return 'help-circle-outline';
    }
  }
}
