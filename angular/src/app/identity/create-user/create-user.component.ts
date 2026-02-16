import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { IonContent } from '@ionic/angular/standalone';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { LabelComponent } from 'src/shared/components/label/label.component';
import { InputComponent } from 'src/shared/components/input/input.component';
import { RestService } from '@abp/ng.core';

@Component({
    selector: 'app-create-user',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        ReactiveFormsModule,
        GlassButtonComponent,
        LabelComponent,
        InputComponent
    ],
    templateUrl: './create-user.component.html',
    styleUrls: ['./create-user.component.scss']
})
export class CreateUserComponent implements OnInit {
    private fb = inject(FormBuilder);
    private restService = inject(RestService);
    private router = inject(Router);

    userForm: FormGroup;
    isLoading = false;
    errorMessage = '';
    successMessage = '';

    constructor() {
        this.userForm = this.fb.group({
            userName: ['', [Validators.required]],
            name: ['', [Validators.required]],
            email: ['', [Validators.required, Validators.email]],
            password: ['', [Validators.required, Validators.minLength(6)]],
            roleNames: [['Trader']]
        });
    }

    ngOnInit(): void {
        // Cargar roles disponibles para asignar
        this.restService.request<any, any>({
            method: 'GET',
            url: '/api/identity/roles',
        }).subscribe({
            next: (response) => {
                const roles = response.items || [];
                const traderRole = roles.find((r: any) => r.name === 'Trader');
                if (traderRole) {
                    this.userForm.get('roleNames')?.setValue([traderRole.name]);
                }
            },
            error: (err) => {
                console.error('Error loading roles:', err);
            }
        });
    }

    onSubmit(): void {
        if (this.userForm.invalid || this.isLoading) {
            Object.keys(this.userForm.controls).forEach(key => {
                this.userForm.get(key)?.markAsTouched();
            });
            return;
        }

        this.isLoading = true;
        this.errorMessage = '';
        this.successMessage = '';

        const payload = {
            userName: this.userForm.value.userName,
            name: this.userForm.value.name,
            surname: this.userForm.value.name, // ABP requiere surname
            email: this.userForm.value.email,
            password: this.userForm.value.password,
            roleNames: this.userForm.value.roleNames,
            isActive: true,
            lockoutEnabled: true
        };

        this.restService.request<any, any>({
            method: 'POST',
            url: '/api/identity/users',
            body: payload
        }).subscribe({
            next: (response) => {
                this.successMessage = 'Usuario creado con éxito';
                this.userForm.reset({
                    roleNames: ['Trader']
                });
                this.isLoading = false;
                // Opcional: navegar a listado si existe
                // setTimeout(() => this.router.navigate(['/admin/users']), 2000);
            },
            error: (error) => {
                console.error('Error creating user:', error);
                this.errorMessage = error.error?.error?.message || 'Error al crear el usuario';
                this.isLoading = false;
            }
        });
    }

    hasError(controlName: string, errorType: string): boolean {
        const control = this.userForm.get(controlName);
        return control?.touched && control?.hasError(errorType) || false;
    }

    onBack(): void {
        this.router.navigate(['/profile']);
    }
}
