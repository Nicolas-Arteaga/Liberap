import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, BehaviorSubject, of } from 'rxjs';
import { tap, catchError, map } from 'rxjs/operators';
import { Router } from '@angular/router';
import { environment } from '../../environments/environment';
import { LoginRequest } from './models/login-request.model';

export const AUTH_TOKEN_KEY = 'verge_access_token';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = environment.apis?.default?.url || 'https://localhost:44396';
  private tokenKey = AUTH_TOKEN_KEY;
  private currentUserSubject = new BehaviorSubject<any>(null);

  public currentUser$ = this.currentUserSubject.asObservable();
  public isAdmin$ = this.currentUser$.pipe(
    map(user => {
      if (!user) return false;

      // Opción 1: Array de strings
      if (user?.roles?.includes?.('admin') || user?.roles?.includes?.('Admin')) return true;

      // Opción 2: Array de objetos con name
      if (user?.roles?.some?.((r: any) => r.name === 'admin' || r.name === 'Admin')) return true;

      // Opción 3: roleNames array
      if (user?.roleNames?.includes?.('admin') || user?.roleNames?.includes?.('Admin')) return true;

      // Opción 4: isInRole object (ABP)
      if (user?.isInRole?.admin === true || user?.isInRole?.Admin === true) return true;

      return false;
    })
  );

  private http = inject(HttpClient);
  private router = inject(Router);

  constructor() {
    this.loadInitialUser();
  }

  login(request: LoginRequest): Observable<any> {
    const url = `${this.apiUrl}/connect/token`;

    // El endpoint /connect/token requiere x-www-form-urlencoded
    const body = new HttpParams()
      .set('grant_type', 'password')
      .set('username', request.userNameOrEmailAddress)
      .set('password', request.password)
      .set('client_id', 'Verge_App')
      .set('scope', 'offline_access Verge email profile roles');

    const headers = new HttpHeaders({
      'Content-Type': 'application/x-www-form-urlencoded'
    });

    console.log('📤 Enviando login OAuth2 a:', url);

    return this.http.post<any>(url, body.toString(), { headers }).pipe(
      tap({
        next: (response) => {
          console.log('✅ Login exitoso:', response);
          if (response.access_token) {
            this.storeToken(response.access_token);
            this.loadUserProfile();
          }
          if (response.refresh_token) {
            localStorage.setItem('refresh_token', response.refresh_token);
          }
        },
        error: (error) => {
          console.error('❌ Error en login:', error);
        }
      })
    );
  }

  logout(): void {
    localStorage.removeItem(this.tokenKey);
    localStorage.removeItem('user_profile');
    localStorage.removeItem('refresh_token');
    this.currentUserSubject.next(null);
    this.router.navigate(['/login']);
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }

  getToken(): string | null {
    const token = localStorage.getItem(this.tokenKey);
    console.log('🔍 Leyendo token de localStorage:', token ? 'EXISTE' : 'NO EXISTE');
    return token;
  }

  private storeToken(token: string): void {
    console.log('💾 Guardando token en localStorage');
    localStorage.setItem(this.tokenKey, token);
    console.log('📦 localStorage después de guardar:', {
      access_token: localStorage.getItem(this.tokenKey)
    });
  }

  private loadInitialUser(): void {
    const token = this.getToken();
    if (token) {
      // Intentar cargar perfil persistido primero para mayor velocidad
      const savedProfile = localStorage.getItem('user_profile');
      if (savedProfile) {
        this.currentUserSubject.next(JSON.parse(savedProfile));
      }
      this.loadUserProfile();
    }
  }

  private loadUserProfile(): void {
    const url = `${this.apiUrl}/api/account/my-profile`;
    this.http.get(url).subscribe({
      next: (profile: any) => {
        console.log('👤 Perfil cargado:', profile);
        this.currentUserSubject.next(profile);
        localStorage.setItem('user_profile', JSON.stringify(profile));
      },
      error: (err) => {
        if (err.status === 401) {
          console.log('ℹ️ Token inválido o sesión expirada al cargar perfil.');
          this.currentUserSubject.next(null);
          localStorage.removeItem('user_profile');
        } else {
          console.error('❌ Error cargando perfil:', err);
        }
      }
    });
  }
}
