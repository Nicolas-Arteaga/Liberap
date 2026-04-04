import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonIcon } from '@ionic/angular/standalone';

@Component({
  selector: 'app-glass-button',
  standalone: true,
  imports: [CommonModule, IonIcon],
  templateUrl: './glass-button.component.html',
  styleUrls: ['./glass-button.component.scss']
})
export class GlassButtonComponent {
  @Input() label?: string;
  @Input() icon?: string;
  @Input() variant: 'glass' | 'solid' | 'danger' = 'glass';
  @Input() color: string = '#00C47D';
  @Input() disabled: boolean = false;  
}
