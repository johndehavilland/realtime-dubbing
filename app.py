from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import os
from dotenv import load_dotenv
import azure.cognitiveservices.speech as speechsdk
import time

app = Flask(__name__)
socketio = SocketIO(app)

# Load .env file
load_dotenv()

speech_key = os.environ.get('SPEECH_KEY')
speech_region = os.environ.get('SPEECH_REGION')

def text_to_speech(text: str):
    # This example requires environment variables named "SPEECH_KEY" and "SPEECH_REGION"
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)

    # The language of the voice that speaks.
    speech_config.speech_synthesis_voice_name='es-MX-DaliaNeural'

    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

    
    speech_synthesis_result = speech_synthesizer.speak_text_async(text).get()

    if speech_synthesis_result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print("Speech synthesized for text [{}]".format(text))
    elif speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = speech_synthesis_result.cancellation_details
        print("Speech synthesis canceled: {}".format(cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            if cancellation_details.error_details:
                print("Error details: {}".format(cancellation_details.error_details))
                print("Did you set the speech resource key and region values?")

def translation_continuous(audio_file):
    """performs continuous speech translation from an audio file"""
    # <TranslationContinuous>
    # set up translation parameters: source language and target languages
    translation_config = speechsdk.translation.SpeechTranslationConfig(
        subscription=speech_key, region=speech_region,
        speech_recognition_language='en-US',
        target_languages=('es', 'de'), voice_name="es-ES-DarioNeural")
    audio_config = speechsdk.audio.AudioConfig(filename="wikipediaOcelot.wav")

    # Creates a translation recognizer using and audio file as input.
    recognizer = speechsdk.translation.TranslationRecognizer(
        translation_config=translation_config, audio_config=audio_config)
    
    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=translation_config)

    def result_callback(event_type: str, evt: speechsdk.translation.TranslationRecognitionEventArgs):
        """callback to display a translation result"""
        print("{}:\n {}\n\tTranslations: {}\n\tResult Json: {}\n".format(
            event_type, evt, evt.result.translations.items(), evt.result.json))
        speech_synthesizer.speak_text_async(evt.result.translations['es'])

    done = False

    def stop_cb(evt: speechsdk.SessionEventArgs):
        """callback that signals to stop continuous recognition upon receiving an event `evt`"""
        print('CLOSING on {}'.format(evt))
        nonlocal done
        done = True

    def canceled_cb(evt: speechsdk.translation.TranslationRecognitionCanceledEventArgs):
        print('CANCELED:\n\tReason:{}\n'.format(evt.result.reason))
        print('\tDetails: {} ({})'.format(evt, evt.result.cancellation_details.error_details))

    # connect callback functions to the events fired by the recognizer
    recognizer.session_started.connect(lambda evt: print('SESSION STARTED: {}'.format(evt)))
    recognizer.session_stopped.connect(lambda evt: print('SESSION STOPPED {}'.format(evt)))
    # event for intermediate results
    recognizer.recognizing.connect(lambda evt: result_callback('RECOGNIZING', evt))
    # event for final result
    recognizer.recognized.connect(lambda evt: result_callback('RECOGNIZED', evt))
    # cancellation event
    recognizer.canceled.connect(canceled_cb)

    # stop continuous recognition on either session stopped or canceled events
    recognizer.session_stopped.connect(stop_cb)
    recognizer.canceled.connect(stop_cb)

    def synthesis_callback(evt: speechsdk.translation.TranslationRecognitionEventArgs):
        """
        callback for the synthesis event
        """
        print('SYNTHESIZING {}\n\treceived {} bytes of audio. Reason: {}'.format(
            evt, len(evt.result.audio), evt.result.reason))

    # connect callback to the synthesis event
    recognizer.synthesizing.connect(synthesis_callback)

    # start translation
    recognizer.start_continuous_recognition()

    while not done:
        time.sleep(.5)

    recognizer.stop_continuous_recognition()
    # </TranslationContinuous>

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('synthesis')
def handle_synthesis(data):
    text_to_speech(data['text'])

@socketio.on('translation')
def handle_translation(data):
    audio_file = data['audio']
    audio_file.save(os.path.join("uploads", audio_file.filename))
    transcribed_text = translation_continuous(os.path.join("uploads", audio_file.filename))
    emit('transcription_update', {'text': transcribed_text})


@app.route('/synthesize', methods=['POST'])
def synthesize():
    if request.method == 'POST':
        text = request.form['text']
        text_to_speech(text)
    return render_template('index.html')

@app.route('/translate', methods=['POST'])
def translate():
    if request.method == 'POST':
        audio_file = request.files['audio']
        audio_file.save(os.path.join("uploads", audio_file.filename))
        translation_continuous(os.path.join("uploads", audio_file.filename))
    return render_template('index.html')

if __name__ == '__main__':
    socketio.run(app, debug=True)