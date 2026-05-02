import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonIcon } from '@ionic/angular/standalone';

@Component({
  selector: 'app-paginator',
  standalone: true,
  imports: [CommonModule, IonIcon],
  template: `
    <div class="d-flex justify-content-between align-items-center mt-3 pt-3 border-top border-secondary border-opacity-25" *ngIf="totalPages > 1">
      <button 
        class="btn btn-sm btn-outline-secondary text-white-50 border-0 d-flex align-items-center gap-1"
        [disabled]="currentPage === 1"
        (click)="onPrev()">
        <ion-icon name="chevron-back-outline"></ion-icon>
        <span>Ant</span>
      </button>

      <span class="text-white-50 text-xs">
        Página {{ currentPage }} de {{ totalPages }}
      </span>

      <button 
        class="btn btn-sm btn-outline-secondary text-white-50 border-0 d-flex align-items-center gap-1"
        [disabled]="currentPage === totalPages"
        (click)="onNext()">
        <span>Sig</span>
        <ion-icon name="chevron-forward-outline"></ion-icon>
      </button>
    </div>
  `
})
export class PaginatorComponent {
  @Input() totalItems: number = 0;
  @Input() pageSize: number = 10;
  @Input() currentPage: number = 1;
  @Output() pageChange = new EventEmitter<number>();

  get totalPages(): number {
    return Math.ceil(this.totalItems / this.pageSize) || 1;
  }

  onPrev() {
    if (this.currentPage > 1) {
      this.pageChange.emit(this.currentPage - 1);
    }
  }

  onNext() {
    if (this.currentPage < this.totalPages) {
      this.pageChange.emit(this.currentPage + 1);
    }
  }
}
