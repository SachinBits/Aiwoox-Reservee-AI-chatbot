import { Component } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { Chatservice } from '../chatservice';
import { firstValueFrom, pipe } from 'rxjs';
import { Queryservice } from '../queryservice';
import { SpeechService } from '../speechservice';



@Component({
  selector: 'app-chatbot',
  templateUrl: './chatbot.html',
  styleUrls: ['./chatbot.scss'],
  imports: [FormsModule,CommonModule]
})

export class Chatbot {
  muted=false;
  designing = false;
  isOpen = false;
  loading: boolean = false;
  userMessage = '';
  voiceChat = false;
  isSpeaking = false;
  isListening = false;
  messages: { sender: 'user' | 'bot'| 'divs', divtype?: 'room' | 'hotel' | 'invoice',text?: string, hotelCards?: { id: string;name: string; description: string; image: string; url: string}[], roomCards?: { id: string; name: string; description: string; image: string, hotelId: string}[], invoice ?: { hotelname: string; roomType: string; price: number} } [] = [];
  chat = [];
  follow_up = ["What is Reservee?", "I'm clueless..😭"]

  constructor(private chatService: Chatservice, private queryService: Queryservice, private speechSvc: SpeechService) {
  }

  toggleChat() {
    this.isOpen = !this.isOpen;
  }

  scrollToBottom() {
    setTimeout(() => {
      const chatBody = document.querySelector('.chat-body');
      if (chatBody) {
        chatBody.scrollTop = chatBody.scrollHeight;
      }
    }, 50);
  }

  async ngOnInit() {
    const threadId = localStorage.getItem('chat_thread_id');
    // const threadId = "16ef0a8d-72b1-4351-adef-26216ad1b9b5"
    if (threadId) {
      this.chatService.threadId = threadId;
      this.messages.push({ sender: 'bot', text: "Hello there!! how can i help you?" });
      this.chatService.chatState(threadId).subscribe(
        response => {
          // console.log('Chat history response:', response);
            try {
            response.values.messages.forEach((element: any) => {
              if (element.content != '') {
              if (element.type == "ai") this.messages.push({sender:'bot', text:element.content});
              else if (element.type == "human") this.messages.push({sender:'user', text:element.content});
            }
            });
            
            if (response.values?.follow_up) {
              console.log('Follow up:', response.values.follow_up);
              this.follow_up = response.values.follow_up.splice(0, 2);
            }
            const showhotels = response.values?.hotel_list?.length > 0;
            // const showhotels = response.values?.show_hotel_list;
            console.log('Show hotels:', showhotels);
            if (showhotels) {
              const hotelCards = []; // Note
              // this.messages.push({ sender: 'bot', text: 'Here are some hotels you might like.' });
              (async () => {
                for (const hotel of response.values?.hotel_list) {
                  const data = await this.queryService.getHotelById(hotel);
                  // console.log('Debug:',data.data[0])
                  if (data && data.data[0]) {
                    hotelCards.push({
                        id: hotel,
                        name: data.data[0].hotelName,
                        description: data.data[0].discountPrice,
                        image: data.data[0].img,
                        url: '#'
                      });
                  } else {
                    console.warn('Hotel data is null for hotel:', hotel[0]);
                  }
                }
                if (hotelCards.length > 0) {
                  this.messages.push({
                    sender: 'divs',
                    divtype: 'hotel',
                    hotelCards: hotelCards
                  });
                }
              })();
            }
            } catch (err) {
            console.error('Error processing chat history:', err);
            }
        },
        error => {
          console.error('Error fetching chat history:', error);
        }
      );
    }
    else {
      const id = await firstValueFrom(this.chatService.createThread());
      localStorage.setItem('chat_thread_id', id);
      this.messages.push({ sender: 'bot', text: "Hello there!! how can i help you?" });
    }

    this.scrollToBottom();
  }

  async newThread() {
    const id = await firstValueFrom(this.chatService.createThread());
    localStorage.setItem('chat_thread_id', id);
    this.messages = [];
    this.messages.push({ sender: 'bot', text: "Hello there! How can i help you?" });
  }

  async handleSpeech(botMessage: string) {
    this.isSpeaking = true;
    this.isListening = false;
    await this.speechSvc.speakAndListen(botMessage); // waits until TTS ends
    // console.log('Chicken Curry');
    this.isSpeaking = false;
    this.isListening = true;
  }

  async finalSpeech(botMessage: string) {
    this.isSpeaking = true;
    this.isListening = false;
    await this.speechSvc.initTTS(botMessage); // waits until TTS ends
    this.isSpeaking = false;
    this.isListening = false;
    this.speechSvc.stopSTT();
  }

  followUpMessage(text: string) {
    this.userMessage = text;
    this.sendMessage();
  }

  sendMessage() {
    console.log(this.messages);
    const message = this.userMessage.trim();
    if (!message) return;
    
    this.messages.push({ sender: 'user', text: message });
    this.userMessage = '';
    this.loading = true;
    this.speechSvc.stopSTT();
    this.isListening = this.speechSvc.isListening;

    this.chatService.sendMessage(message).subscribe(
      response => {
        console.log('Response from server:', response);
        if (response?.follow_up) {
          
              this.follow_up = response?.follow_up.splice(0, 2);
            }
        const bbmsg = response?.messages;
        const botMessage = bbmsg[bbmsg.length - 1]?.content || 'No response from bot';
        this.loading = false;
        // if (this.voiceChat) {
        //   this.isSpeaking = true;
        //   this.speechSvc.speakAndListen(botMessage);
        //   this.isSpeaking = false;
        //   // console.log('Should speak')
        // }
        if(this.voiceChat) this.handleSpeech(botMessage);
        this.messages.push({ sender: 'bot', text: botMessage });
        // const showhotels = response.values?.hotel_list?.length > 0;
        // console.log('Chicken',response.values);
        const showhotels = response?.show_hotel_list;
        console.log('Show hotels:', showhotels);
        // Hotel showing logic Flag
        if (showhotels) {
          this.loading = true;
          // this.messages.filter(msg => msg.divtype !== 'hotel');
          // this.messages.filter(msg => msg.sender !== 'divs');
          if (this.voiceChat) this.handleSpeech('Here are some hotels you might like' );
            (async () => {
              const hotelCards = [];
              for (const hotel of response?.hotel_list) {
                try {
                  const data = await this.queryService.getHotelById(hotel);
                  if (data && data.data[0]) {
                    hotelCards.push({
                      id: hotel,
                      name: data.data[0].hotelName,
                      description: data.data[0].discountPrice,
                      image: data.data[0].img,
                      url: '#'
                    });
                  } else {
                    console.warn('Hotel data is null for hotel:', hotel);
                  }
                } catch (err) {
                  console.error('Error fetching hotel data:', err);
                }
              }
              this.loading = false;
              this.messages.push({
                sender: 'divs',
                divtype: 'hotel',
                hotelCards: hotelCards
              });
            })();
        }
        const showRooms = response?.show_room_list;
        console.log('Show rooms:', showRooms);
        if (showRooms) {
          this.loading = true;
          // this.messages.filter(msg => msg.sender !== 'divs');
          // this.messages.filter(msg => msg.divtype !== 'room');
          // this.messages.push({ sender: 'bot', text: 'Here are some rooms we found' });
          if (this.voiceChat) this.handleSpeech('Here are the rooms available' );
          const roomCards: any[] = [];
            (async () => {
              for (const room of response.room_list) {
                try {
                  const data = await this.queryService.getRoomInfoById(room);
                  if (data && data.data) {
                    roomCards.push({
                        id: room,
                        name: data.data.roomType,
                        description: data.data.price,
                        image: data.data.roomImage,
                        hotelId: data.data.hotel_id
                      }
                    );
                  } else {
                    this.loading = false;
                    console.warn('Hotel data is null for hotel:', room);
                  }
                } catch (err) {
                  this.loading = false;
                  console.error('Error fetching hotel data:', err);
                }
              }
              this.loading = false;
              this.messages.push({
                sender: 'divs',
                divtype: 'room',
                roomCards: roomCards
              });
            })();
        }

      },
      error => {
        // console.error('Error sending message:', error);
        this.loading = false;
        this.messages.push({ sender: 'bot', text: 'Error: Unable to get response from bot.' });
        if(this.voiceChat) {
          this.finalSpeech('Error: Unable to get response from bot.');
          this.toggleVoice();
        }
      }
    );
    this.scrollToBottom();
  }

  async bookHotel(hotel: { id: string; name: string; description: string; image: string; url: string }) {
    console.log("Booking hotel:", hotel);

    const observable = await this.chatService.bookHotel(hotel.id);
    observable.subscribe({
      next: (res) => {
        // console.log('Rooms:', res);
      },
      error: (err) => {
        console.error(err);
        this.messages.push({ sender: 'bot', text: `Failed..` });
      }
    });

    const state = this.chatService.chatState(this.chatService.threadId!);
    state.subscribe({
      next: (response) => {
        console.log('Rooms:', response.values?.room_list);
        // this.messages =this.messages.filter(msg => msg.sender !== 'divs'); 
        // this.messages.push({ sender: 'bot', text: 'Here are some rooms we found' });
        if (this.voiceChat) this.handleSpeech('Here are the rooms available' );
            (async () => {
              this.loading = true;
              const roomCards: any[] = [];
              for (const room of response.values.room_list) {
                try {
                  const data = await this.queryService.getRoomInfoById(room);
                  if (data && data.data) {
                    roomCards.push({
                        id: room,
                        name: data.data.roomType,
                        description: data.data.price,
                        image: data.data.roomImage,
                        hotelId: data.data.hotel_id
                      });
                  } else {
                    this.loading = false;
                    console.warn('Hotel data is null for hotel:', room);
                  }
                } catch (err) {
                  this.loading = false;
                  console.error('Error fetching hotel data:', err);
                }
              }
              this.loading = false;
              this.messages.push({
                sender: 'divs',
                divtype: 'room',
                roomCards: roomCards
              });
            })();
        
      },
      error: (err) => {
        console.error(err);
      }
    });
    this.scrollToBottom();
  }

  async confirmBooking(room: { id: string; name: string; description: string; image: string; hotelId: string }) {
    console.log("Confirming booking for room:", room);
    this.loading = true;
    if (this.voiceChat) this.handleSpeech('Here is the invoice for the booking, please confirm the details and click pay now to be redirected to the payment gateway' );
    // this.messages.filter(msg => msg.divtype !== 'invoice');
    const invoice = {
      hotelname: await this.queryService.getHotelNameById(room.hotelId) || 'Unknown Hotel',
      roomType: room.name,
      price: room.description ? parseFloat(room.description) : 0
    };
    // this.messages =this.messages.filter(msg => msg.sender !== 'divs'); 
    this.loading = false;
    this.messages.push({ sender: 'divs', divtype: 'invoice', invoice: invoice });
    this.scrollToBottom
  }

  payNow() {
    // this.messages.filter(msg => msg.sender !== 'divs');
    this.loading = true;
    this.speechSvc.stopSTT();
    console.log("Payment initiated");
    setTimeout(() => {
      console.log("Delayed message after 2 seconds");
    }, 2000);
    this.loading = false;
    this.messages.push({ sender: 'bot', text: 'Payment successful! Thank you for booking with us.' });
    if(this.voiceChat) {
      this.finalSpeech('Payment successful! Thank you for booking with us.');
      this.toggleVoice();
    }
    this.scrollToBottom();
    // this.messages = [];
    // this.messages.push({ sender: 'bot', text: "Hello there!! how can i help you?" });
    // localStorage.removeItem('chat_thread_id');
    // this.chatService.threadId = '';
  }



  toggleVoice() {
    this.voiceChat = !this.voiceChat
    console.log('Voice Chat:', this.voiceChat);
    if (this.voiceChat) {
      this.isListening = true;
      this.isSpeaking = false;
      this.speechSvc.initSTT((text: string) => {
      this.userMessage = text;
      this.sendMessage();
    });
    } else {
      this.speechSvc.stopSTT();
      this.isListening = false;
      this.isSpeaking = false;
    }
    if(this.voiceChat && this.messages.length == 1 && this.messages[0].text) {
      console.log('Initializer');
      this.handleSpeech(this.messages[0].text);
    }
  }

  toggleMute() {
    this.muted = !this.muted;
  }

  get isDivsPresent(): boolean {
  return this.messages.some(m => m.sender === 'divs');
}

  get isRoomsPresent(): boolean {
    return this.messages.some(m => m.divtype === 'room');
  }

  get isInvoicePresent(): boolean {
    return this.messages.some(m => m.divtype === 'invoice');
  }


}
