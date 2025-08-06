import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Chatbot } from './chatbot/chatbot';

@Component({
  selector: 'app-root',
  imports: [Chatbot],
  template: `
  <app-chatbot></app-chatbot>
  `, 
  styleUrl: './app.scss'
})
export class App {
  isOpen = false;
  toggleChat() {
    this.isOpen = !this.isOpen;
  }

  protected title = 'chatdemo';
}
