import difflib
import json
from PIL import Image, ImageDraw

def generate_ground_truth(predicted_brl, corrected_brl, image_coordinates):
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
    """
    case 1. 점자가 아닌 부분을 점자로 인식한 경우
            tag == 'delete'인 경우에 해당
            -> label을 0으로 변경
    case 2. 점자인 부분을 점자가 아닌 부분으로 인식한 경우
            tag == 'insert'인 경우에 해당
            -> 공백으로 찾아진 경우
                -> label만 변경
            -> 아예 없는 경우
                -> label 추가 및 box 할당
    case 3. 점자를 다른 점자로 인식한 경우
            tag == 'replace'인 경우에 해당
            
    case 4. 원본 점자에 2개 이상의 공백이 있는 경우
            tag == 'delete'이며, 
    """
    
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
                'correct_char': '⠀',
                'coordinates': coord
            })
        elif c_idx is not None:
            ground_truth.append({
                'ocr_char': '⠀',
                'correct_char': corrected_brl[c_idx],
                'coordinates': None
            })
    
    return ground_truth

def brl_to_labels(brl_by_lines):
    labels_by_lines = []
    for brl in brl_by_lines:
        labels = []
        for char in brl:
            if char == '⠀':
                continue
            label = ord(char) - 0x2800
            labels.append(label)
        labels_by_lines.append(labels)
    return labels_by_lines

def main(extracted_json):
    predicted_brl_by_lines = extracted_json['prediction']['brl']
    corrected_brl_by_lines = extracted_json['correction']['brl']
    boxes_by_lines = extracted_json['prediction']['boxes']
    
    img = Image.open('test.jpg')
    draw = ImageDraw.Draw(img)
    
    corrected_coordinates_by_lines = []
    for predicted_brl, corrected_brl, boxes in zip(predicted_brl_by_lines, corrected_brl_by_lines, boxes_by_lines):
        # print(corrected_brl)
        ground_truth = generate_ground_truth(predicted_brl, corrected_brl, boxes)
        corrected_coordinates = []
        for gt in ground_truth:
            coordinates = gt['coordinates']
            
            if coordinates is None:
                """
                TODO: 이미지 좌표가 없는 경우 처리
                case 1. OCR이 인식하지 못한 문자
                    -> 줄의 시작이나 끝에 있는 문자일 가능성이 높음.
                case 2. 교정 결과에 없는 문자
                    -> 점자가 아닌 부분을 점자로 인식한 경우일 가능성이 높음.
                """
                pass
            
            if gt['ocr_char'] == gt['correct_char']:
                if gt['correct_char'] != '⠀':
                    print(gt)
                    corrected_coordinates.append(coordinates)
                continue
    
            
            corrected_coordinates.append(coordinates)
            
            draw.rectangle(coordinates, outline='red')
            char_to_draw = str(ord(gt['ocr_char']) - 0x2800) + "->" + str(ord(gt['correct_char']) - 0x2800)
            draw.text((coordinates[0], coordinates[1] - 10), char_to_draw, fill='black')
        corrected_coordinates_by_lines.append(corrected_coordinates)
    
    extracted_json['correction']['boxes'] =  corrected_coordinates_by_lines
    extracted_json['correction']['labels'] = brl_to_labels(corrected_brl_by_lines)
    img.save('result.jpg')
    print('Done.')
    print('Result image is saved as result.jpg')
    print('Retruned JSON is updated.')
    return extracted_json
    
    
if __name__ == '__main__':
    with open('test.json', 'r') as f:
        extracted_json = json.load(f)

    with open('test.json', 'w') as f:
        json.dump(main(extracted_json), f, indent=4, ensure_ascii=False)