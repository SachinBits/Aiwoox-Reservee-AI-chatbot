import { Injectable } from '@angular/core';
import { createClient } from '@supabase/supabase-js'
import { from } from 'rxjs';

// Create a single supabase client for interacting with your database
// const supabase = createClient('https://dhbbaorrjrwuagxqqmij.supabase.co', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRoYmJhb3JyanJ3dWFneHFxbWlqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzU0OTIzNTksImV4cCI6MjA1MTA2ODM1OX0.6yGhD1kUX0msvA-VT3KhYX4NlrQcfsjWXmBQTRAgzyo')


import { environment } from '../environments/environment';
const supabase = createClient(environment.SUPABASE_URL, environment.SUPABASE_ANON_KEY)
// import { Database } from './database.types'
// const supabase = createClient<Database>(
//   process.env.SUPABASE_URL,
//   process.env.SUPABASE_ANON_KEY
// )


@Injectable({
  providedIn: 'root'
})
export class Queryservice {

  constructor() { }

  async getHotelById(id: string) {
    // const { data, error } = await supabase.from('hotels natural join hotel_rooms').select('id,hotelName,price,img').eq('id', id).single();
    const { data, error } = await supabase
        .rpc('get_cheapest_hotel_price', { id_input: id });

    if (error) {
      console.error('Error fetching cheapest room:', error);
    } else {
      // console.log('Cheapest room:', data);
    }

    return { data, error };
  }



  async getRoomsByHotelId(hotelId: string) {
    const { data, error } = await supabase.from('hotel_rooms').select('id').eq('hotel_id', hotelId);
    return { data, error };
  }

  async getHotelNameById(hotelId: string): Promise<string | null> {
    const { data, error } = await supabase
      .from('hotels')
      .select('hotelName')
      .eq('id', hotelId)
      .single();

    if (error || !data) {
      console.error('Error fetching hotel name:', error);
      return null;
    }

    return data.hotelName

  }

  async getRoomInfoById(roomId: string) {
    const { data, error } = await supabase.from('hotel_rooms').select('id,hotel_id,roomType,roomImage,price').eq('id', roomId).single();
    return { data, error };
  }
}
