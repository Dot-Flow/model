import L1_OCR.run_ocr_app as run_ocr_app
import L2_BrailleToText.brl_to_txt as b2t
import L3_ContextualErrorCorrection.contextual_error_correction as cec
import L4_TextToBraille.txt_to_brl as t2b
import L5_FeedbackGenerator.feedback_gen as fg

import json
import base64
import PIL.Image
import io

def lambda_handler(event, context):
    # 요청 경로와 HTTP 메서드에 따라 처리
    path = event['path']
    http_method = event['httpMethod']
    if path == '/run' and http_method == 'POST':
        return handle_run(event)
    elif path == '/feedback_gen' and http_method == 'POST':
        return handle_feedback_gen(event)
    elif path == '/L1_OCR' and http_method == 'POST':
        return handle_L1_OCR(event)
    elif path == '/L2_BrailleToText' and http_method == 'POST':
        return handle_L2_BrailleToText(event)
    elif path == '/L3_ContextualErrorCorrection' and http_method == 'POST':
        return handle_L3_ContextualErrorCorrection(event)
    elif path == '/L4_TextToBraille' and http_method == 'POST':
        return handle_L4_TextToBraille(event)
    else:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Not Found'}, ensure_ascii=False)
        }

def handle_run(image):
    print("Process Run")
    print("Process L1: OCR")
    extracted_json = run_ocr_app.run_ocr(image)
    print("Process L2: BrailleToText")
    extracted_json = b2t.translate(extracted_json)
    print("Process L3: ContextualErrorCorrection")
    extracted_json = cec.correct(extracted_json)
    return extracted_json['correction']['text']

def handle_feedback_gen(event):
    pass
    
def handle_L1_OCR(event):
    image_data = event['body']['image']
    image = decode_image_from_base64(image_data)
    
    # OCR 처리 로직
    extracted_json = process_L1_OCR(image)
    return {
        'statusCode': 200,
        'body': json.dumps(extracted_json, ensure_ascii=False)
    }

def handle_L2_BrailleToText(event):
    extracted_json = json.loads(event['body'])
    # Braille to Text 처리 로직
    extracted_json = process_L2_BrailleToText(extracted_json)
    return {
        'statusCode': 200,
        'body': json.dumps(extracted_json, ensure_ascii=False)
    }

def handle_L3_ContextualErrorCorrection(event):
    extracted_json = json.loads(event['body'])
    # Contextual Error Correction 처리 로직
    extracted_json = process_L3_ContextualErrorCorrection(extracted_json)
    return {
        'statusCode': 200,
        'body': json.dumps(extracted_json, ensure_ascii=False)
    }

def handle_L4_TextToBraille(event):
    extracted_json = json.loads(event['body'])
    # Text to Braille 처리 로직
    extracted_json = process_L4_TextToBraille(extracted_json)
    return {
        'statusCode': 200,
        'body': json.dumps(extracted_json, ensure_ascii=False)
    }

# Base64 이미지 디코딩 함수
def decode_image_from_base64(base64_string):
    image_data = base64.b64decode(base64_string)
    image = PIL.Image.open(io.BytesIO(image_data))
    return image

def process_L1_OCR(image):
    print("Process L1: OCR")
    try:
        return run_ocr_app.run_ocr(image)  # 이미지 처리 함수
    except KeyError as e:
        print('키 오류 발생')
        # Flask의 jsonify 대신 Lambda에서는 json.dumps를 사용해 응답 생성
        return {
            'statusCode': 500,
            'body': json.dumps({'error': '키 오류 발생'}, ensure_ascii=False)
        }
    except Exception as e:
        print('서버 오류 발생')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': '서버 오류 발생'}, ensure_ascii=False)
        }

def process_L2_BrailleToText(extracted_json):
    print("Process L2: BrailleToText")
    try:
        return b2t.translate(extracted_json)  # 이미지 처리 함수
    except KeyError as e:
        print('키 오류 발생')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': '키 오류 발생'}, ensure_ascii=False)
        }
    except Exception as e:
        print('서버 오류 발생')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': '서버 오류 발생'}, ensure_ascii=False)
        }

def process_L3_ContextualErrorCorrection(extracted_json):
    print("Process L3: ContextualErrorCorrection")
    try:
        return cec.correct(extracted_json)  # 이미지 처리 함수
    except KeyError as e:
        print('키 오류 발생')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': '키 오류 발생'}, ensure_ascii=False)
        }
    except Exception as e:
        print('서버 오류 발생')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': '서버 오류 발생'}, ensure_ascii=False)
        }
        
def process_L4_TextToBraille(extracted_json):
    print("Process L4: TextToBraille")
    try:
        return t2b.translate(extracted_json)  # 이미지 처리 함수
    except KeyError as e:
        print('키 오류 발생')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': '키 오류 발생'}, ensure_ascii=False)
        }
    except Exception as e:
        print('서버 오류 발생')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': '서버 오류 발생'}, ensure_ascii=False)
        }

# curl -X POST -F "image=@kakao/KakaoTalk_20241008_234355161_04.jpg" http://127.0.0.1:5000/run_ocr_loop
