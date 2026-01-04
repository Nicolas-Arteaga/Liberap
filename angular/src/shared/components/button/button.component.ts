import { Component, Input, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-button',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './button.component.html',
  styleUrls: ['./button.component.scss']
})
export class ButtonComponent {
  @Input() label!: string;
  @Input() count?: number;
  @Input() variant: 'default' | 'success' | 'danger' | 'warning' = 'default';
  @Input() active = false;
  @Input() disabled = false;
  
}
