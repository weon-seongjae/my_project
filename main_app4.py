import streamlit as st
from gtts import gTTS
import re
import json
from PIL import Image
import os
import time
import tempfile
import uuid
from pydub import AudioSegment
import requests
import shutil
import random


def load_conversations_and_modifications():
    with open("conversations.json", "r", encoding='utf-8') as file:
        conversations_data = json.load(file)

    with open("chapter_modification.json", "r", encoding='utf-8') as file:
        modifications_data = json.load(file)

    modifications_dict = {modification['chapter']: modification for modification in modifications_data}

    return conversations_data, modifications_dict

knowledge_base, modifications_dict = load_conversations_and_modifications()

temp_files = []

def synthesize_speech(text, filename):
    tts = gTTS(text, lang='en')
    filename = f"./audio/{filename}"
    tts.save(filename)
    return filename

def speak_and_mixed(text):
    print(f"Received text for conversion: {text}")
    if text.startswith("./audio_"):
        return [], [], 0

    audio_urls = []
    text_chunks = []

    clean_text = re.sub('<[^<]+?>', '', text)
    unique_id = uuid.uuid4()
    filename = f"0_{unique_id}.mp3"
    audio_path = synthesize_speech(clean_text, filename)
    print(f"audio_path {audio_path}")
    audio_url = f"http://127.0.0.1:8001/audio/{os.path.basename(audio_path)}"

    # 음성 파일의 길이를 직접 여기서 계산합니다.
    audio = AudioSegment.from_mp3(audio_path)
    audio_length = len(audio) / 1000

    # 음성 파일을 버퍼 디렉토리로 복사합니다.
    # buffer_path = os.path.join('./audio', filename)
    # shutil.copyfile(audio_path, buffer_path)

    print(f"Generated audio for conversation: '{clean_text}', Audio URL: '{audio_url}', Audio Length: {audio_length}")
    
    audio_urls.append(audio_url)
    text_chunks.append(clean_text)

    return audio_urls, text_chunks, audio_length

def prepare_speakers_and_messages(selected_chapter, chapter_conversations, modifications_dict):
    speakers_and_messages = [{'chapter': selected_chapter, 'speaker': message['speaker'], 'message': message['message']} 
                         for message in chapter_conversations 
                         if message['speaker'] == 'user']
    speakers_and_messages.insert(0, {'chapter': selected_chapter, 'speaker': "user", 'message': ""})

    for msg in speakers_and_messages:
        if msg['speaker'] != 'user':
            print("에러: bot의 메시지가 포함되었습니다:", msg)

    if selected_chapter in modifications_dict:
        for add in modifications_dict[selected_chapter]['add']:
            speakers_and_messages.append({'chapter': selected_chapter, 'speaker': add['speaker'], 'message': add['message']})

        for remove in modifications_dict[selected_chapter]['remove']:
            speakers_and_messages = [i for i in speakers_and_messages if not (i['speaker'] == remove['speaker'] and i['message'] == remove['message'])]

    return speakers_and_messages

def handle_chapter_and_conversation_selection(knowledge_base):
    chapters = [data['chapter_title'] for data in knowledge_base]

    if "selected_chapter" not in st.session_state or st.session_state.selected_chapter not in chapters:
        st.session_state.selected_chapter = chapters[0]

    if st.session_state.selected_chapter in chapters:
        selected_chapter = st.selectbox(
            "Choose a chapter:",
            chapters,
            index=chapters.index(st.session_state.selected_chapter),
        )
        if st.session_state.selected_chapter != selected_chapter:
            st.session_state.selected_chapter = selected_chapter
            if "selected_message" in st.session_state:
                del st.session_state.selected_message
            if "chat_history" in st.session_state:
                del st.session_state.chat_history
                st.experimental_rerun()

    chapter_conversations = next((data['conversations'] for data in knowledge_base if data['chapter_title'] == st.session_state.selected_chapter), None)

    speakers_and_messages = prepare_speakers_and_messages(st.session_state.selected_chapter, chapter_conversations, modifications_dict)

    all_messages = [sm['message'] for sm in speakers_and_messages]
    if not all_messages:
        raise ValueError("all_messages is empty. Check the function prepare_speakers_and_messages.")

    if "" not in all_messages:
        raise ValueError("Empty string is not in all_messages. Check the function prepare_speakers_and_messages.")

    if "selected_message" not in st.session_state or st.session_state.selected_message not in all_messages:
        st.session_state.selected_message = all_messages[0]

    if st.session_state.selected_message in all_messages:
        selected_message = st.selectbox(
            "Choose a conversation:",
            all_messages,
            index=all_messages.index(st.session_state.selected_message) if st.session_state.selected_message != "" else 0,
        )
        if st.session_state.selected_message != selected_message:
            st.session_state.selected_message = selected_message
            st.experimental_rerun()

    if st.session_state.selected_chapter and st.session_state.selected_message and st.session_state.selected_message != "":
        chapter_name = st.session_state.selected_chapter
        chapter_data = next(chap_data for chap_data in knowledge_base if chap_data["chapter_title"] == chapter_name)
        speakers_and_messages = chapter_data["conversations"]

        return chapter_name, chapter_data, speakers_and_messages
    return None, None, None

css_style = """
<style>
.styled-message {
    background-color: white;
    border-radius: 5px;
    padding: 0;
    margin: 0;  /* Adjust margin to control the gap */
    box-shadow: none;  /* Remove shadow effect */
}
.question-dialogue-gap {
    margin: 20px 0; /* Add a larger margin for the gap */
}
</style>
"""

def display_chat_history(chapter_data):
    selected_message = st.session_state.selected_message
    selected_conversation = []

    conversations = chapter_data["conversations"]
    for idx, conv in enumerate(conversations):
        if conv["message"] == selected_message:
            if idx + 1 < len(conversations):
                selected_conversation = [conversations[idx], conversations[idx+1]]
            break

    if not selected_conversation:
        st.write("Error: Selected message and the corresponding answer not found.")
        return

    if not hasattr(st.session_state, "chat_history"):
        st.session_state.chat_history = []

    # Add 'is_new' attribute to the new conversation
    st.session_state.chat_history.insert(0, {"conversation": selected_conversation, "is_new": True})

    for idx, conv in enumerate(st.session_state.chat_history):
        st.markdown("<hr>", unsafe_allow_html=True)
        for i, msg in enumerate(conv["conversation"]):
            icon = "👩‍🦰" if msg['speaker'] == 'user' else "👩"
            messages = [msg['message']] if isinstance(msg['message'], str) else msg['message']
            for selected_message in messages: # 여러 개의 메시지가 있는 경우 모두 처리
                styled_message = f'<div class="styled-message">{icon} {selected_message}</div>'

                if conv["is_new"]:
                    audio_urls, _, audio_length = speak_and_mixed(selected_message)
                    for audio_url in audio_urls:
                        audio_tag = f'<audio autoplay src="{audio_url}" style="display: none;"></audio>'
                        st.markdown(audio_tag, unsafe_allow_html=True)
                        time.sleep(audio_length)

                st.markdown(styled_message, unsafe_allow_html=True)

        # Deleting audio files
        if conv["is_new"] and msg['speaker'] == 'bot':
            for audio_url in audio_urls:
                filename = audio_url.split('/')[-1]
                # requests.post(f"http://127.0.0.1:8001/delete/audio/{filename}")

        # Once a conversation has been displayed, it's not new anymore
        if conv["is_new"]:
            st.session_state.chat_history[idx]["is_new"] = False

    st.markdown(css_style, unsafe_allow_html=True)

def main():
    st.title("English Again Conversations")

    _, chapter_data, speakers_and_messages = handle_chapter_and_conversation_selection(knowledge_base)

    if speakers_and_messages and chapter_data:
        display_chat_history(chapter_data)

def safe_delete(file):
    for _ in range(10):
        try:
            os.remove(file)
            print(f"Successfully deleted {file}")
            break
        except Exception as e:
            print(f"Failed to delete {file}: {e}")
            time.sleep(0.5)

if __name__ == "__main__":
    main()
    for file in temp_files:
        safe_delete(file)