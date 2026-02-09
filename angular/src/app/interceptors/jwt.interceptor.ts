import { Injectable, inject } from '@angular/core';
import {
    HttpRequest,
    HttpHandler,
    HttpEvent,
    HttpInterceptor,
    HttpErrorResponse
} from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { Router } from '@angular/router';
import { AuthService } from '../core/auth.service';

@Injectable()
export class JwtInterceptor implements HttpInterceptor {
    private authService = inject(AuthService);
    private router = inject(Router);

    intercept(request: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
        const token = this.authService.getToken();

        let clonedRequest = request;

        // Solo añadir token si existe y NO es una request de autenticación
        if (token && !this.isAuthRequest(request)) {
            clonedRequest = request.clone({
                setHeaders: {
                    Authorization: `Bearer ${token}`
                }
            });
        }

        return next.handle(clonedRequest).pipe(
            catchError((error: HttpErrorResponse) => {
                if (error.status === 401) {
                    console.warn('⚠️ 401 Unauthorized - Cerrando sesión');
                    this.authService.logout();
                    this.router.navigate(['/login'], {
                        queryParams: { sessionExpired: true }
                    });
                }
                return throwError(() => error);
            })
        );
    }

    private isAuthRequest(request: HttpRequest<any>): boolean {
        const url = request.url.toLowerCase();
        return url.includes('/api/account/login') ||
            url.includes('/connect/token') ||
            url.includes('/api/tokenauth/authenticate');
    }
}
