import { Component } from '@angular/core';
import { addIcons } from 'ionicons';
import { personOutline } from 'ionicons/icons';
import {
  IonHeader,
  IonToolbar,
  IonTitle,
  IonButtons,
  IonButton,
  IonIcon
} from '@ionic/angular/standalone';

@Component({
  selector: 'app-mobile-top-bar',
  standalone: true,
  imports: [
    IonHeader,
    IonToolbar,
    IonButton,
    IonIcon
  ],
  templateUrl: './mobile-top-bar.component.html',
  styleUrls: ['./mobile-top-bar.component.scss']
})
export class MobileTopBarComponent {
  constructor() {
    addIcons({ personOutline });
  }

  onProfileClick() {}
}
