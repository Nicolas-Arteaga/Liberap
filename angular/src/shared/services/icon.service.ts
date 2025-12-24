import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class IconService {
  fixMissingIcons() {
    setTimeout(() => {
      const brokenIcons = document.querySelectorAll('ion-icon:not(:has(svg))');
      brokenIcons.forEach(icon => icon.parentNode?.replaceChild(icon.cloneNode(true), icon));
    }, 300);
  }
}