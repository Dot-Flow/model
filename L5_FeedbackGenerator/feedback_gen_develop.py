import difflib
import numpy as np
import json

def generate_ground_truth(extracted_json):
    # 1. 점자 문자열과 수정된 텍스트의 번역
    predicted_brl = extracted_json['prediction']['brl']
    corrected_brl = extracted_json['correction']['brl']
    image_coordinates = extracted_json['predicton']['boxes']
    
    # 2. 문자열 정렬을 통한 매핑
    matcher = difflib.SequenceMatcher(None, predicted_brl, corrected_brl)
    mapping = []
    for opcode in matcher.get_opcodes():
        tag, i1, i2, j1, j2 = opcode
        if tag == 'equal':
            for o, c in zip(range(i1, i2), range(j1, j2)):
                mapping.append((o, c, image_coordinates[o]))
        elif tag == 'replace':
            for o, c in zip(range(i1, i2), range(j1, j2)):
                mapping.append((o, c, image_coordinates[o]))
        elif tag == 'delete':
            for o in range(i1, i2):
                mapping.append((o, None, image_coordinates[o]))
        elif tag == 'insert':
            for c in range(j1, j2):
                mapping.append((None, c, None))
    
    # 3. 위치 정보 보완
    # 여기서 매핑된 각 문자에 대해 이미지 좌표를 재할당하거나 보완
    
    # 4. 오류 유형 처리
    ground_truth = []
    for map_item in mapping:
        o_idx, c_idx, coord = map_item
        if o_idx is not None and c_idx is not None:
            ground_truth.append({
                'ocr_char': predicted_brl[o_idx],
                'correct_char': corrected_brl[c_idx],
                'coordinates': coord
            })
        elif o_idx is not None:
            ground_truth.append({
                'ocr_char': predicted_brl[o_idx],
                'correct_char': None,
                'coordinates': coord
            })
        elif c_idx is not None:
            ground_truth.append({
                'ocr_char': None,
                'correct_char': corrected_brl[c_idx],
                'coordinates': None
            })
    
    return ground_truth

if __name__ == '__main__':
    with open('extracted.json', 'r') as f:
        extracted_json = json.load(f)
    
    ground_truth = generate_ground_truth(extracted_json)
    with open('ground_truth.json', 'w') as f:
        json.dump(ground_truth, f)