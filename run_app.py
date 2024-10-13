import L1_OCR.run_ocr_app as run_ocr_app
import L2_BrailleToText.brl_to_txt as b2t
import L3_ContextualErrorCorrection.contextual_error_correction as cec
import L4_TextToBraille.txt_to_brl as t2b
# import L5_FeedbackGenerator.feedback_gen as fg

import logging
import json
from flask import Flask, request, jsonify, Response

app = Flask(__name__)


def proccess_L1_OCR(image):
    print("Process L1: OCR")
    if 'image' not in request.files:
        return jsonify({'error': '이미지 파일이 요청에 포함되어 있지 않습니다.'}), 400

    image = request.files['image']
    if image.filename == '':
        return jsonify({'error': '선택된 파일이 없습니다.'}), 400

    try:
        return run_ocr_app.run_ocr(image)  # 이미지 처리 함수
    except KeyError as e:
        return jsonify({'error': '키 오류 발생'}), 500
    except Exception as e:
        return jsonify({'error': '서버 오류 발생'}), 500

@app.route('/L1_OCR', methods=['POST'])
def L1_OCR(image):
    extracted_json = proccess_L1_OCR(image)
    response = json.dumps({'brl': extracted_json['prediction']['brl']}, ensure_ascii=False)
    return Response(response, content_type='application/json; charset=utf-8')


def proccess_L2_BrailleToText(extracted_json):
    print("Process L2: BrailleToText")
    
    extracted_brl = extracted_json['prediction']['brl']
    
    if extracted_brl is None:
        return jsonify({'error': '점자 인식 오류'}), 500
    
    try:
        extracted_json['prediction']['text'] = b2t.translate(extracted_brl)  # 점자 번역 함수
        return extracted_json
    except Exception as e:
        return jsonify({'error': '서버 오류 발생'}), 500

@app.route('/L2_BrailleToText', methods=['POST'])
def L2_BrailleToText(extracted_json):
    extracted_json = proccess_L2_BrailleToText(extracted_json)
    response = json.dumps({'text': extracted_json['prediction']['text']}, ensure_ascii=False)
    return Response(response, content_type='application/json; charset=utf-8')


def proccess_L3_ContextualErrorCorrection(extracted_json):
    print("Process L3: ContextualErrorCorrection")
    
    extracted_text = extracted_json['prediction']['text']
    
    if extracted_text is None:
        return jsonify({'error': '텍스트 추출 오류'}), 500
    
    try:
        extracted_json['correction']['text'] = cec.correct(extracted_text)  # 텍스트 오류 수정 함수
        return extracted_json
    except Exception as e:
        return jsonify({'error': '서버 오류 발생'}), 500

@app.route('/L3_ContextualErrorCorrection', methods=['POST'])
def L3_ContextualErrorCorrection(extracted_json):
    extracted_json = proccess_L3_ContextualErrorCorrection(extracted_json)
    response = json.dumps({'corrected_text': extracted_json['correction']['text']}, ensure_ascii=False)
    return Response(response, content_type='application/json; charset=utf-8')


def proccess_L4_TextToBraille(extracted_json):
    print("Process L4: TextToBraille")
    
    extracted_text = extracted_json['correction']['text']
    
    if extracted_text is None:
        return jsonify({'error': '텍스트 오류 수정 오류'}), 500
    
    try:
        extracted_json['correction']['brl'] = t2b.translate(extracted_text)  # 텍스트를 점자로 변환 함수
        return extracted_json
    except Exception as e:
        return jsonify({'error': '서버 오류 발생'}), 500
    
@app.route('/L4_TextToBraille', methods=['POST'])
def L4_TextToBraille(extracted_json):
    extracted_json = proccess_L4_TextToBraille(extracted_json)
    response = json.dumps({'brl': extracted_json['correction']['brl']}, ensure_ascii=False)
    return Response(response, content_type='application/json; charset=utf-8')


# curl -X POST -F "image=@KakaoTalk_20241008_234355161_04.jpg" http://127.0.0.1:5000/run_ocr_loop


@app.route('/run_ocr_loop', methods=['POST'])
def run_ocr_loop():
    image = request.files['image']
    extracted_json = proccess_L1_OCR(image)
    extracted_json = proccess_L2_BrailleToText(extracted_json)
    
    # GPT api 돈 없어서 일단 패스
    # extracted_json = proccess_L3_ContextualErrorCorrection(extracted_json)
    extracted_json['correction']['text'] = extracted_json['prediction']['text']
    with open('test.json', 'w') as f:
        json.dump(extracted_json, f, ensure_ascii=False, indent=4, encoding='utf-8')
    extracted_json = proccess_L4_TextToBraille(extracted_json)
    
    response = json.dumps(extracted_json, ensure_ascii=False)
    
    return Response(response, content_type='application/json; charset=utf-8')

if __name__ == '__main__':
    app.run(debug=False)
