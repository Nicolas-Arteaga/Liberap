import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-toggle',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './toggle.component.html',
  styleUrls: ['./toggle.component.scss']
})
export class ToggleComponent {
  @Input() label: string = '';
  @Input() description: string = '';
  @Input() value: boolean = false;
  @Output() valueChange = new EventEmitter<boolean>();

  toggle() {
    this.value = !this.value;
    this.valueChange.emit(this.value);
  }
}