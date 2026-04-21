from flask import Flask, jsonify, request
from flask_cors import CORS
from pitch import convert_to_pitch

app = Flask(__name__)
CORS(app)


@app.route('/text-to-pitch', methods=['POST'])
def text_to_pitch():
    data = request.json
    text = data.get('text', '')
    pitch = convert_to_pitch(text)
    return jsonify({'text': text, 'pitch': pitch})

if __name__ == '__main__':
    app.run(debug=True)
