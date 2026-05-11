import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StrategyProfileDto } from '../../../proxy/trading/dtos/models';
import { CardContentComponent } from '../../../../shared/components/card-content/card-content.component';
import { GlassButtonComponent } from '../../../../shared/components/glass-button/glass-button.component';
import { ToggleComponent } from '../../../../shared/components/toggle/toggle.component';

@Component({
  selector: 'app-strategy-card',
  standalone: true,
  imports: [CommonModule, CardContentComponent, GlassButtonComponent, ToggleComponent],
  templateUrl: './strategy-card.component.html',
  styleUrls: ['./strategy-card.component.scss']
})
export class StrategyCardComponent {
  @Input() profile!: StrategyProfileDto;
  @Output() edit = new EventEmitter<string>();
  @Output() duplicate = new EventEmitter<string>();
  @Output() delete = new EventEmitter<string>();
  @Output() toggle = new EventEmitter<string>();
  @Output() viewPerformance = new EventEmitter<string>();

  onToggle() {
    this.toggle.emit(this.profile.id);
  }
}
