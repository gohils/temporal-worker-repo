import requests
# from decouple import config
import os
from base64 import decodebytes

GCP_API_KEY = os.getenv("GCP_API_KEY")
AZURE_SPEECH_API_KEY = os.getenv("AZURE_SPEECH_API_KEY")

# Convert text to speech
def gcp_convert_text_to_speech(message):
    
    url = "https://texttospeech.googleapis.com/v1/text:synthesize"
    headers = {
    "X-Goog-Api-Key": f"{GCP_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json"
    }
    payload = {
        "audioConfig": {
            "audioEncoding": "MP3",
            "pitch": 0,
            "speakingRate": 0,
            "sampleRateHertz": 0,
            "volumeGainDb": 0
        },
        "input": {
            "text": f"{message}"
        },
        "voice": {
            "languageCode": "en-GB",
            "name": "en-GB-Neural2-A",
            "ssmlGender": "FEMALE"
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        response_data = response.json()["audioContent"]
        audio_data = decodebytes(response_data.encode('utf-8'))
        # with open("gcp_test_output.mp3", "wb") as f:
        #     f.write(audio_data)
        return audio_data
    else:
        print("Error:", response.status_code, response.text)

# Convert text to speech
def azure_convert_text_to_speech(message):
    url = "https://australiaeast.tts.speech.microsoft.com/cognitiveservices/v1"

    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_API_KEY,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",  # Adjust the output format as needed
    }

    voice_name = 'en-US-AriaNeural'
    ssml = f"""<speak version='1.0' xmlns='https://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
    <voice name='en-US-AriaNeural'>{message}</voice>
    </speak>"""

    response = requests.post(url, headers=headers, data=ssml.encode('utf-8'))
    if response.status_code == 200:
        audio_data = response.content
        # # Save the audio output to a file
        # with open("output_azure.mp3", "wb") as file:
        #     file.write(response.content)        
        return audio_data
    else:
        print("Error:", response.status_code, response.text)
