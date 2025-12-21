import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IonContent } from '@ionic/angular/standalone';  
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { LabelComponent } from 'src/shared/components/label/label.component';
import { InputComponent } from 'src/shared/components/input/input.component';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IonContent,  
    GlassButtonComponent,
    LabelComponent,
    InputComponent  
  ],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent {
  email = '';
  password = '';
  isLoading = false;

  onSubmit(event: Event) {
    event.preventDefault();
    this.isLoading = true;

    setTimeout(() => {
      this.isLoading = false;
      window.location.href = '/';
    }, 1000);
  }

  onForgotPassword() {}
  onCreateAccount() {}
}