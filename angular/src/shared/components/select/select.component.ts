import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

interface SelectOption {
  value: string;
  label: string;
}

@Component({
  selector: 'app-select',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './select.component.html',
  styleUrls: ['./select.component.scss']
})
export class SelectComponent {
  @Input() label: string = '';
  @Input() placeholder: string = 'Seleccionar...';
  @Input() options: SelectOption[] = [];
  
  @Input() value: string = '';
  @Output() valueChange = new EventEmitter<string>();

  isOpen = false;

  select(option: SelectOption) {
    this.value = option.value;
    this.valueChange.emit(this.value);
    this.isOpen = false;
  }

  getSelectedText(): string {
    const option = this.options.find(opt => opt.value === this.value);
    return option ? option.label : '';
  }
}