### Step 1: Set Up Angular Project

If you haven't already created an Angular project, you can do so using the Angular CLI:

```bash
ng new chatbot-app
cd chatbot-app
ng serve
```

### Step 2: Install Required Packages

You will need to install `@angular/common/http` for making HTTP requests. If you haven't already, you can install it using:

```bash
npm install @angular/common
```

### Step 3: Create the Chat Service

Create a service to handle the communication with your backend. You can create a file named `chat.service.ts` in the `src/app` directory.

```typescript
// src/app/chat.service.ts
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private apiUrl = 'http://127.0.0.1:2024'; // Your LangGraph backend URL
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

  chatState(threadID: string): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/threads/${threadID}/state`);
  }
}
```

### Step 4: Create the Chat Component

Create a component for the chatbot interface. You can create a file named `chat.component.ts` in the `src/app` directory.

```typescript
// src/app/chat.component.ts
import { Component, OnInit } from '@angular/core';
import { ChatService } from './chat.service';

@Component({
  selector: 'app-chat',
  templateUrl: './chat.component.html',
  styleUrls: ['./chat.component.css']
})
export class ChatComponent implements OnInit {
  messages: { role: string, content: string }[] = [];
  userMessage: string = '';

  constructor(private chatService: ChatService) { }

  ngOnInit(): void {
    this.chatService.createThread().subscribe(threadId => {
      console.log('Thread created:', threadId);
    });
  }

  sendMessage(): void {
    if (this.userMessage.trim()) {
      this.messages.push({ role: 'user', content: this.userMessage });
      this.chatService.sendMessage(this.userMessage).subscribe(response => {
        this.messages.push({ role: 'assistant', content: response.output });
        this.userMessage = '';
      }, error => {
        console.error('Error sending message:', error);
      });
    }
  }
}
```

### Step 5: Create the Chat Component Template

Create a template for the chat component. You can create a file named `chat.component.html` in the `src/app` directory.

```html
<!-- src/app/chat.component.html -->
<div class="chat-container">
  <div class="messages">
    <div *ngFor="let message of messages" [ngClass]="message.role">
      <strong>{{ message.role }}:</strong> {{ message.content }}
    </div>
  </div>
  <input [(ngModel)]="userMessage" (keyup.enter)="sendMessage()" placeholder="Type your message..." />
  <button (click)="sendMessage()">Send</button>
</div>
```

### Step 6: Add Styles

You can add some basic styles in `chat.component.css` to make it look better.

```css
/* src/app/chat.component.css */
.chat-container {
  width: 400px;
  margin: auto;
  border: 1px solid #ccc;
  padding: 10px;
  border-radius: 5px;
  background-color: #f9f9f9;
}

.messages {
  max-height: 300px;
  overflow-y: auto;
  margin-bottom: 10px;
}

.user {
  color: blue;
}

.assistant {
  color: green;
}
```

### Step 7: Update App Module

Make sure to declare the `ChatComponent` and import `HttpClientModule` and `FormsModule` in your `app.module.ts`.

```typescript
// src/app/app.module.ts
import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { AppComponent } from './app.component';
import { ChatComponent } from './chat.component';

@NgModule({
  declarations: [
    AppComponent,
    ChatComponent
  ],
  imports: [
    BrowserModule,
    HttpClientModule,
    FormsModule
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule { }
```

### Step 8: Use the Chat Component

Finally, use the `ChatComponent` in your `app.component.html`.

```html
<!-- src/app/app.component.html -->
<h1>Chatbot</h1>
<app-chat></app-chat>
```

### Step 9: Run Your Application

Now you can run your Angular application:

```bash
ng serve
```

### Conclusion

This setup provides a basic chatbot interface that communicates with a backend using LangGraph. You can enhance it further by adding features like error handling, loading indicators, and more sophisticated message formatting. Make sure your backend is running and accessible at the specified URL.