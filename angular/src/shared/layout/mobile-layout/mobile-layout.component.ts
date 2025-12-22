import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import {
  IonApp,
  IonContent
} from '@ionic/angular/standalone';

import { MobileTopBarComponent } from '../mobile-top-bar/mobile-top-bar.component';
import { MobileBottomNavComponent } from '../mobile-bottom-nav/mobile-bottom-nav.component';

@Component({
  selector: 'app-mobile-layout',
  standalone: true,
  imports: [
    IonApp,
    IonContent,
    RouterOutlet,
    MobileTopBarComponent,
    MobileBottomNavComponent
  ],
  templateUrl: './mobile-layout.component.html',
  styleUrls: ['./mobile-layout.component.scss']
})
export class MobileLayoutComponent {
}