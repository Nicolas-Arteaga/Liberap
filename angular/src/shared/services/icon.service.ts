import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class IconService {
  fixMissingIcons() {
    setTimeout(() => {
      const brokenIcons = document.querySelectorAll('ion-icon:not(:has(svg))');
      brokenIcons.forEach(icon => {
        const name = icon.getAttribute('name');
        // Only attempt to replace if it has a valid name to prevent base URL errors
        if (name && name !== 'undefined' && name.trim() !== '') {
          icon.parentNode?.replaceChild(icon.cloneNode(true), icon);
        }
      });
    }, 300);
  }
}
