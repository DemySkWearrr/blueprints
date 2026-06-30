import telebot
import asyncio
import websockets
import json
import base64
import io
from pydub import AudioSegment

API_TOKEN = 'ваш телеграм токен'
OPENAI_API_KEY = 'ваш openai токен'
REALTIME_API_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"

bot = telebot.TeleBot(API_TOKEN)

async def connect_to_realtime_api():
    print("Устанавливаем WebSocket-соединение с Realtime API...")
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }
    try:
        ws = await websockets.connect(REALTIME_API_URL, extra_headers=headers)
        print("Соединение установлено!")
        
        # Устанавливаем голос "shimmer" для сессии
        session_update = {
            "type": "session.update",
            "session": {
                "voice": "shimmer"
            }
        }
        await ws.send(json.dumps(session_update))
        print("Установлен голос 'shimmer' для сессии.")
        
        return ws
    except Exception as e:
        print(f"Ошибка при подключении к WebSocket: {e}")
        raise

@bot.message_handler(content_types=['text'])
def handle_text_message(message):
    text = message.text
    print(f"Получено текстовое сообщение от пользователя: {text}")
    asyncio.run(handle_realtime_response_text(message, text))

@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    print("Получено голосовое сообщение от пользователя.")
    try:
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        audio_base64 = convert_voice_to_pcm(downloaded_file)
        print("Аудио сообщение конвертировано и отправлено в Realtime API.")
        asyncio.run(handle_realtime_response_audio(message, audio_base64))
    except Exception as e:
        print(f"Ошибка при обработке голосового сообщения: {e}")
        import traceback
        print(traceback.format_exc())

def convert_voice_to_pcm(downloaded_file):
    try:
        print("Конвертация аудио в PCM формат...")
        audio = AudioSegment.from_file(io.BytesIO(downloaded_file), format="ogg")
        audio = audio.set_frame_rate(24000).set_channels(1).set_sample_width(2)
        raw_data = audio.raw_data
        audio_base64 = base64.b64encode(raw_data).decode('utf-8')
        print("Конвертация завершена.")
        return audio_base64
    except Exception as e:
        print(f"Ошибка при конвертации аудио: {e}")
        raise

async def handle_realtime_response_text(message, text):
    try:
        ws = await connect_to_realtime_api()
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}]
            }
        }
        await ws.send(json.dumps(event))
        print("Текстовое сообщение отправлено.")

        response_event = {
            "type": "response.create",
            "response": {
                "modalities": ["text"],
                "instructions": "Ответь на сообщение пользователя"
            }
        }
        await ws.send(json.dumps(response_event))
        print("Запрос на генерацию ответа отправлен.")

        full_response = ""
        async for response in ws:
            response_data = json.loads(response)
            print(f"Получен ответ от Realtime API: {response_data}")
            if response_data['type'] == 'response.text.delta':
                delta = response_data.get('delta', '')
                full_response += delta
                print(f"Получена часть ответа: {delta}")
            elif response_data['type'] == 'response.done':
                break

        if full_response:
            bot.send_message(message.chat.id, full_response)
            print(f"Отправлено сообщение пользователю: {full_response}")
        else:
            print("Не получен текстовый ответ от API.")

    except Exception as e:
        print(f"Ошибка при обработке текстового сообщения: {e}")
        import traceback
        print(traceback.format_exc())
    finally:
        await ws.close()
        print("WebSocket-соединение закрыто.")

async def handle_realtime_response_audio(message, audio_base64):
    try:
        ws = await connect_to_realtime_api()
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_audio", "audio": audio_base64}]
            }
        }
        await ws.send(json.dumps(event))
        print("Аудио сообщение отправлено.")

        response_event = {
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": "Ответь на голосовое сообщение",
                "voice": "shimmer"
            }
        }
        await ws.send(json.dumps(response_event))
        print("Запрос на генерацию голосового ответа отправлен с голосом 'shimmer'.")

        full_audio_data = b''
        full_text_response = ""
        async for response in ws:
            response_data = json.loads(response)
            print(f"Получен ответ от Realtime API: {response_data}")

            if response_data['type'] == 'response.audio.delta':
                audio_data = base64.b64decode(response_data["delta"])
                full_audio_data += audio_data
                print(f"Получена аудио дельта, размер: {len(audio_data)} байт")
            elif response_data['type'] == 'response.text.delta':
                delta = response_data.get('delta', '')
                full_text_response += delta
                print(f"Получена часть текстового ответа: {delta}")
            elif response_data['type'] == 'response.done':
                print("Ответ API завершен.")
                break

        if full_audio_data:
            print(f"Аудио ответ завершен, общий размер: {len(full_audio_data)} байт")
            audio_segment = AudioSegment.from_raw(io.BytesIO(full_audio_data), sample_width=2, frame_rate=24000, channels=1)
            ogg_bytes = io.BytesIO()
            audio_segment.export(ogg_bytes, format="ogg", codec="libopus")
            ogg_bytes.seek(0)

            file_size = ogg_bytes.getbuffer().nbytes
            print(f"Размер OGG файла: {file_size} байт")

            if file_size <= 50 * 1024 * 1024:
                bot.send_voice(message.chat.id, ogg_bytes.getvalue())
                print("Голосовой ответ отправлен пользователю.")
            else:
                print("Ошибка: Аудиофайл слишком большой для отправки в Telegram.")
                bot.send_message(message.chat.id, "Извините, но аудиоответ слишком длинный для отправки.")
        else:
            print("Ошибка: Не получены аудио данные от API.")
            bot.send_message(message.chat.id, "Извините, но произошла ошибка при генерации аудиоответа.")

        if full_text_response:
            bot.send_message(message.chat.id, full_text_response)
            print(f"Отправлен текстовый ответ пользователю: {full_text_response}")

    except Exception as e:
        print(f"Ошибка при обработке аудио сообщения: {e}")
        import traceback
        print(traceback.format_exc())
        bot.send_message(message.chat.id, "Извините, произошла ошибка при обработке вашего голосового сообщения.")
    finally:
        await ws.close()
        print("WebSocket-соединение закрыто.")

if __name__ == "__main__":
    print("Запуск бота...")
    bot.polling(none_stop=True)