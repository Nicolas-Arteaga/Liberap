import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-paginator',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="paginator-container" *ngIf="shouldShow()">
      <div class="paginator-info">
        Mostrando {{ getStartRange() }}-{{ getEndRange() }} de {{ totalItems }} trades
      </div>

      <div class="paginator-controls">
        <button 
          class="paginator-btn"
          [disabled]="currentPage === 1"
          (click)="goToPage(1)"
          title="Primera página">
          «
        </button>
        
        <button 
          class="paginator-btn"
          [disabled]="currentPage === 1"
          (click)="onPrev()"
          title="Página anterior">
          ‹
        </button>

        <div class="paginator-pages">
          @for (page of visiblePages(); track page) {
            <button
              class="paginator-page"
              [class.active]="page === currentPage"
              (click)="goToPage(page)">
              {{ page }}
            </button>
          }
        </div>

        <button 
          class="paginator-btn"
          [disabled]="currentPage === totalPages"
          (click)="onNext()"
          title="Página siguiente">
          ›
        </button>

        <button 
          class="paginator-btn"
          [disabled]="currentPage === totalPages"
          (click)="goToPage(totalPages)"
          title="Última página">
          »
        </button>
      </div>

      <div class="paginator-size">
        <label>Tamaño de página:</label>
        <select [value]="pageSize" (change)="onPageSizeChange($event)">
          @for (size of pageSizeOptions; track size) {
            <option [value]="size">{{ size }}</option>
          }
        </select>
      </div>
    </div>
  `,
  styles: [`
    .paginator-container {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 1rem;
      padding: 1rem;
      margin-top: 1rem;
      background: rgba(8, 12, 17, 0.9);
      border: 1px solid rgba(0, 243, 255, 0.15);
      border-radius: 6px;
    }

    .paginator-info {
      font-size: 0.75rem;
      color: #94a3b8;
      font-family: 'JetBrains Mono', monospace;
    }

    .paginator-controls {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .paginator-btn {
      background: rgba(0, 243, 255, 0.08);
      border: 1px solid rgba(0, 243, 255, 0.25);
      color: #00f3ff;
      padding: 0.35rem 0.65rem;
      border-radius: 4px;
      cursor: pointer;
      font-size: 0.85rem;
      font-family: inherit;
      transition: all 0.2s;

      &:hover:not(:disabled) {
        background: rgba(0, 243, 255, 0.15);
        border-color: rgba(0, 243, 255, 0.45);
      }

      &:disabled {
        opacity: 0.3;
        cursor: not-allowed;
      }
    }

    .paginator-pages {
      display: flex;
      gap: 0.25rem;
    }

    .paginator-page {
      background: transparent;
      border: 1px solid rgba(148, 163, 184, 0.2);
      color: #94a3b8;
      padding: 0.35rem 0.65rem;
      border-radius: 4px;
      cursor: pointer;
      font-size: 0.75rem;
      font-family: inherit;
      min-width: 32px;
      transition: all 0.2s;

      &:hover:not(.active) {
        background: rgba(0, 243, 255, 0.08);
        border-color: rgba(0, 243, 255, 0.3);
        color: #00f3ff;
      }

      &.active {
        background: rgba(0, 243, 255, 0.2);
        border-color: #00f3ff;
        color: #00f3ff;
        font-weight: 600;
      }
    }

    .paginator-size {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.75rem;
      color: #94a3b8;
      font-family: 'JetBrains Mono', monospace;

      label {
        color: #64748b;
      }

      select {
        background: rgba(8, 12, 17, 0.9);
        border: 1px solid rgba(0, 243, 255, 0.25);
        color: #00f3ff;
        padding: 0.3rem 0.5rem;
        border-radius: 4px;
        font-family: inherit;
        font-size: 0.75rem;
        cursor: pointer;
      }
    }

    @media (max-width: 768px) {
      .paginator-container {
        flex-direction: column;
        align-items: stretch;
      }

      .paginator-controls {
        justify-content: center;
      }

      .paginator-size {
        justify-content: center;
      }
    }
  `]
})
export class PaginatorComponent {
  @Input() totalItems: number = 0;
  @Input() pageSize: number = 10;
  @Input() currentPage: number = 1;
  @Input() showAlways: boolean = false;
  @Input() pageSizeOptions: number[] = [10, 25, 50, 100];
  @Output() pageChange = new EventEmitter<number>();
  @Output() pageSizeChange = new EventEmitter<number>();

  get totalPages(): number {
    return Math.ceil(this.totalItems / this.pageSize) || 1;
  }

  shouldShow(): boolean {
    if (this.showAlways) return true;
    return this.totalPages > 1;
  }

  getStartRange(): number {
    if (this.totalItems === 0) return 0;
    return (this.currentPage - 1) * this.pageSize + 1;
  }

  getEndRange(): number {
    return Math.min(this.currentPage * this.pageSize, this.totalItems);
  }

  visiblePages(): number[] {
    const pages: number[] = [];
    const maxVisible = 5;
    let start = Math.max(1, this.currentPage - Math.floor(maxVisible / 2));
    let end = Math.min(this.totalPages, start + maxVisible - 1);
    
    if (end - start < maxVisible - 1) {
      start = Math.max(1, end - maxVisible + 1);
    }

    for (let i = start; i <= end; i++) {
      pages.push(i);
    }

    return pages;
  }

  goToPage(page: number) {
    if (page >= 1 && page <= this.totalPages && page !== this.currentPage) {
      this.pageChange.emit(page);
    }
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

  onPageSizeChange(event: Event) {
    const value = (event.target as HTMLSelectElement).value;
    const newSize = parseInt(value, 10);
    this.pageSizeChange.emit(newSize);
  }
}
