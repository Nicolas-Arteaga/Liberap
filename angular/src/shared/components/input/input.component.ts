import { Component, Input, forwardRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

@Component({
  selector: 'app-input',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './input.component.html',
  styleUrls: ['./input.component.scss'],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => InputComponent),
      multi: true
    }
  ]
})
export class InputComponent implements ControlValueAccessor {
  @Input() type: string = 'text';
  @Input() placeholder: string = '';
  @Input() id: string = '';
  @Input() name: string = '';
  @Input() autocomplete: string = '';
  @Input() required: boolean = false;
  @Input() set showPasswordToggle(value: boolean | string) {
    // Convertir string a boolean si es necesario
    if (typeof value === 'string') {
      this._showPasswordToggle = value === 'true' || value === '';
    } else {
      this._showPasswordToggle = value;
    }
  }
  get showPasswordToggle(): boolean {
    return this._showPasswordToggle;
  }
  private _showPasswordToggle: boolean = false;

  value = '';
  disabled = false;
  isPasswordVisible = false;

  get isPassword(): boolean {
    return this.type === 'password';
  }

  get inputType(): string {
    if (!this.isPassword) return this.type;
    return this.isPasswordVisible ? 'text' : 'password';
  }

  get hasPasswordToggle(): boolean {
    return this.isPassword && this.showPasswordToggle;
  }

  togglePasswordVisibility(): void {
    if (this.hasPasswordToggle) {
      this.isPasswordVisible = !this.isPasswordVisible;
    }
  }

  /* ===== ControlValueAccessor ===== */
  private onChange = (_: any) => {};
  private onTouched = () => {};

  writeValue(value: any): void {
    this.value = value ?? '';
  }

  registerOnChange(fn: any): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: any): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.disabled = isDisabled;
  }

  onInput(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.value = value;
    this.onChange(value);
    this.onTouched();
  }

  onBlur(): void {
    this.onTouched();
  }
}