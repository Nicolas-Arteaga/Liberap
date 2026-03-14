import { Component, Input, Output, EventEmitter, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IonIcon } from '@ionic/angular/standalone';

@Component({
  selector: 'app-leverage-modal',
  standalone: true,
  imports: [CommonModule, FormsModule, IonIcon],
  templateUrl: './leverage-modal.component.html',
  styleUrls: ['./leverage-modal.component.scss']
})
export class LeverageModalComponent implements OnInit {
  @Input() currentLeverage: number = 20;
  @Output() confirm = new EventEmitter<number>();
  @Output() close = new EventEmitter<void>();

  tempLeverage: number = 20;
  quickOptions = [1, 30, 60, 90, 120, 150];

  ngOnInit() {
    this.tempLeverage = this.currentLeverage;
  }

  updateLeverage(val: number) {
    this.tempLeverage = Math.min(150, Math.max(1, val));
  }

  adjust(delta: number) {
    this.updateLeverage(this.tempLeverage + delta);
  }

  onConfirm() {
    this.confirm.emit(this.tempLeverage);
  }

  onClose() {
    this.close.emit();
  }
}
