import { Component, Input, Output, EventEmitter } from '@angular/core';
import {
  IonFooter,
  IonIcon
} from '@ionic/angular/standalone';

import { addIcons } from 'ionicons';
import { homeOutline, cardOutline, personOutline } from 'ionicons/icons';

@Component({
  selector: 'app-mobile-bottom-nav',
  standalone: true,
  imports: [
    IonFooter,
    IonIcon
  ],
  templateUrl: './mobile-bottom-nav.component.html',
  styleUrls: ['./mobile-bottom-nav.component.scss']
})
export class MobileBottomNavComponent {
  @Input() activeTab!: 'home' | 'debts' | 'profile';
  @Output() tabChange = new EventEmitter<'home' | 'debts' | 'profile'>();

  constructor() {
    addIcons({
      homeOutline,
      cardOutline,
      personOutline
    });
  }

  onTabClick(tab: 'home' | 'debts' | 'profile') {
    this.tabChange.emit(tab);
  }
}
