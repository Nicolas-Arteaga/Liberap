import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, BehaviorSubject, of } from 'rxjs';
import { tap, catchError, map } from 'rxjs/operators';
import { Router } from '@angular/router';
import { environment } from '../../environments/environment';
import { LoginRequest } from './models/login-request.model';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = environment.apis?.default?.url || 'https://localhost:44396';
  private tokenKey = 'access_token';
  private currentUserSubject = new BehaviorSubject<any>(null);

  public currentUser$ = this.currentUserSubject.asObservable();

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
    return localStorage.getItem(this.tokenKey);
  }

  private storeToken(token: string): void {
    localStorage.setItem(this.tokenKey, token);
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
        console.error('❌ Error cargando perfil:', err);
        if (err.status === 401) {
          this.logout();
        }
      }
    });
  }
}
