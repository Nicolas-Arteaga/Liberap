import { Component } from '@angular/core';
import { IonCard } from '@ionic/angular/standalone';

@Component({
  selector: 'app-card-content',
  standalone: true,
  imports: [IonCard],
  templateUrl: './card-content.component.html',
  styleUrls: ['./card-content.component.scss']
})
export class CardContentComponent {}
