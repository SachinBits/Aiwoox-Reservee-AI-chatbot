import { Injectable } from '@angular/core';
import * as SpeechSDK from 'microsoft-cognitiveservices-speech-sdk';
import { environment } from '../environments/environment';

@Injectable({ providedIn: 'root' })
export class SpeechService {
  private speechConfig = SpeechSDK.SpeechConfig.fromSubscription(
    environment.azureSpeechKey,
    environment.azureSpeechRegion
  );

  private recognizer?: SpeechSDK.SpeechRecognizer;
  private sttCallback?: (text: string) => void;

  isSpeaking = false;
  isListening = false;


  // Global TTS + STT logic
  async speakAndListen(text: string) {
    console.log('Stopping')
    this.stopSTT(); // Stop listening to avoid self-feedback
    this.isSpeaking = true;
    this.isListening = false;
    console.log('Speech Begins');
    await this.initTTS(text);
    if (this.sttCallback) {
      this.isListening = true;
      this.isSpeaking = false;
      this.initSTT(this.sttCallback); // Restart recognition
      // console.log('Speech Ended');
    }
  }



  initTTS(text: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const audioDestination = new SpeechSDK.SpeakerAudioDestination();

      const audioConfig = SpeechSDK.AudioConfig.fromSpeakerOutput(audioDestination);
      const synthesizer = new SpeechSDK.SpeechSynthesizer(this.speechConfig, audioConfig);

      audioDestination.onAudioEnd = () => {
        // synthesizer.close();
        resolve();
        // console.log('Speech Ended');
      };

      synthesizer.speakTextAsync(
        text,
        result => {
          synthesizer.close();
          if (result.reason !== SpeechSDK.ResultReason.SynthesizingAudioCompleted) {
            reject(new Error('Synthesis did not complete'));
          }
        },
        err => {
          synthesizer.close();
          reject(err);
        }
      );
    });
  }



  initSTT(onResult: (text: string) => void): void {
    this.sttCallback = onResult;

    const audioConfig = SpeechSDK.AudioConfig.fromDefaultMicrophoneInput();
    this.recognizer = new SpeechSDK.SpeechRecognizer(this.speechConfig, audioConfig);

    this.recognizer.recognized = (s, e) => {
      if (e.result.reason === SpeechSDK.ResultReason.RecognizedSpeech && e.result.text) {
        onResult(e.result.text);
      }
    };

    this.recognizer.startContinuousRecognitionAsync();
    console.log('STT Running')
  }

  stopSTT(): void {
    console.log('Stop function called')
    this.isListening = false;
    if (this.recognizer) {
      this.recognizer.stopContinuousRecognitionAsync(() => {
        this.recognizer?.close();
        this.recognizer = undefined;
        console.log('STT stopped');
        this.isListening = false;
        this.isSpeaking = false;
      });
    }
  }
}
