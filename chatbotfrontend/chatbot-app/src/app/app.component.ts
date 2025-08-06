import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private apiUrl = 'http://127.0.0.1:2024'; // Your backend URL
  public threadId: string | null = null;

  constructor(private http: HttpClient) { }

  createThread(): Observable<string> {
    return this.http.post<{ thread_id: string }>(`${this.apiUrl}/threads`, {}).pipe(
      map(response => {
        this.threadId = response.thread_id;
        return this.threadId;
      })
    );
  }

  sendMessage(message: string): Observable<any> {
    if (!this.threadId) {
      throw new Error('Thread ID is not set. Please create a thread first.');
    }
    const body = {
      assistant_id: 'agent',
      input: { messages: [{ role: 'user', content: message }] }
    };
    return this.http.post<any>(`${this.apiUrl}/threads/${this.threadId}/runs/wait`, body);
  }

  chatState(): Observable<any> {
    if (!this.threadId) {
      throw new Error('Thread ID is not set. Please create a thread first.');
    }
    return this.http.get<any>(`${this.apiUrl}/threads/${this.threadId}/state`);
  }
}