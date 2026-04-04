import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { PairBotInfo } from '../models/bot.models';
import { environment } from 'src/environments/environment';

@Injectable({
  providedIn: 'root'
})
export class BotApiService {
  private http = inject(HttpClient);
  // Base URL from environment (default to 44396 for dev)
  private baseUrl = environment.apis.default.url + '/api/app/bot';

  getActivePairs(): Observable<PairBotInfo[]> {
    return this.http.get<PairBotInfo[]>(`${this.baseUrl}/active-pairs`);
  }
}
