import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';  
import { IonIcon } from '@ionic/angular/standalone';

@Component({
  selector: 'app-card-icon',
  standalone: true,
  imports: [CommonModule, IonIcon],  
  templateUrl: './card-icon.component.html',
  styleUrls: ['./card-icon.component.scss']
})
export class CardIconComponent {
  @Input() icon!: string;
  @Input() vertical = false;
  @Input() contentClass = '';
  @Input() variant: 'inline' | 'stacked' = 'inline';
  @Input() status: 'al-dia' | 'vencida' | null = null;
  @Input() useCardContentBg = false;  
}