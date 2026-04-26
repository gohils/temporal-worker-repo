from openai import OpenAI

from app.functions.database import get_recent_messages
import os

# Retrieve Enviornment Variables
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
   
# Open AI - Whisper
# Convert audio to text openai_client.audio.transcriptions.create(model="whisper-1", file=audio_file)
def convert_audio_to_text(audio_file):
  try:
    transcript = openai_client.audio.transcriptions.create(model="whisper-1", file=audio_file)
    message_text = transcript.text
    return message_text
  except Exception as e:
    return

# Open AI - Chat GPT
# Convert audio to text
def get_chat_response(message_input):

  messages = get_recent_messages()
  user_message = {"role": "user", "content": message_input}
  messages.append(user_message)
  # print("=======gpt==input=======",messages)

  try:
      response = openai_client.chat.completions.create(
          model="gpt-3.5-turbo",
          messages=messages
      )
      return response.choices[0].message.content

  except Exception as e:
    print(e)
    return
