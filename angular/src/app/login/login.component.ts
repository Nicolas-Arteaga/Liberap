import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { IonContent } from '@ionic/angular/standalone';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { LabelComponent } from 'src/shared/components/label/label.component';
import { InputComponent } from 'src/shared/components/input/input.component';
import { AuthService } from '../core/auth.service';
import { LoginRequest } from '../core/models/login-request.model';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    IonContent,
    GlassButtonComponent,
    LabelComponent,
    InputComponent
  ],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent implements OnInit {
  private fb = inject(FormBuilder);
  private authService = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  loginForm: FormGroup;
  isLoading = false;
  errorMessage = '';
  returnUrl = '/dashboard';

  constructor() {
    this.loginForm = this.fb.group({
      username: ['', [Validators.required]],
      password: ['', [Validators.required, Validators.minLength(4)]],
      rememberMe: [true]
    });
  }

  ngOnInit(): void {
    if (this.authService.isAuthenticated()) {
      this.router.navigate(['/home']);
      return;
    }

    this.route.queryParams.subscribe(params => {
      if (params['returnUrl']) {
        this.returnUrl = params['returnUrl'];
      }
      if (params['sessionExpired']) {
        this.errorMessage = 'Tu sesión ha expirado. Por favor, inicia sesión nuevamente.';
      }
    });
  }

  onSubmit(): void {
    if (this.loginForm.invalid || this.isLoading) {
      Object.keys(this.loginForm.controls).forEach(key => {
        this.loginForm.get(key)?.markAsTouched();
      });
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';
    console.log('🔄 Iniciando login OAuth2...');

    const loginRequest: LoginRequest = {
      userNameOrEmailAddress: this.loginForm.value.username,
      password: this.loginForm.value.password,
      rememberMe: this.loginForm.value.rememberMe,
      twoFactorRememberClientToken: null,
      twoFactorCode: null,
      twoFactorProvider: null
    };

    this.authService.login(loginRequest).subscribe({
      next: (response) => {
        console.log('✅ Login completado con éxito.');
        setTimeout(() => {
          this.router.navigateByUrl(this.returnUrl).then(success => {
            if (!success) {
              console.warn('⚠️ Falló la navegación por Angular Router. Forzando recarga de página...');
              window.location.href = this.returnUrl;
            }
          });
        }, 100);
      },
      error: (error) => {
        console.error('❌ Error en login:', error);

        if (error.status === 400 || error.status === 401) {
          this.errorMessage = 'Usuario o contraseña incorrectos';
        } else if (error.status === 0) {
          this.errorMessage = 'No se puede conectar con el servidor. Verifica que el backend esté corriendo.';
        } else {
          this.errorMessage = error.error?.error_description || 'Error al iniciar sesión';
        }

        this.isLoading = false;
      },
      complete: () => {
        this.isLoading = false;
      }
    });
  }

  hasError(controlName: string, errorType: string): boolean {
    const control = this.loginForm.get(controlName);
    return control?.touched && control?.hasError(errorType) || false;
  }

  onForgotPassword(): void {
    this.router.navigate(['/account/forgot-password']);
  }


}