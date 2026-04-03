import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { IonFooter, IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { homeOutline, cardOutline, personOutline } from 'ionicons/icons';

@Component({
  selector: 'app-mobile-bottom-nav',
  standalone: true,
  imports: [IonFooter, IonIcon, RouterLink, RouterLinkActive],
  templateUrl: './mobile-bottom-nav.component.html',
  styleUrls: ['./mobile-bottom-nav.component.scss']
})
export class MobileBottomNavComponent {
  constructor() {
    addIcons({ homeOutline, cardOutline, personOutline });
  }
}