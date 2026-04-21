import pyopenjtalk

def convert_to_pitch(text):
    pitch = pyopenjtalk.extract_fullcontext(text)
    print(pitch)
    return pitch