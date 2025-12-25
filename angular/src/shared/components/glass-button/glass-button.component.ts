import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-glass-button',
  standalone: true,
  templateUrl: './glass-button.component.html',
  styleUrls: ['./glass-button.component.scss']
})
export class GlassButtonComponent {
  @Input() variant: 'glass' | 'solid' | 'danger' = 'glass';
  @Input() color: string = '#00C47D';
  @Input() disabled: boolean = false;  
}
