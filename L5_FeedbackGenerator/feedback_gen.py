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
    with open('test.json', 'r') as f:
        extracted_json = json.load(f)
    predicted_brl = extracted_json['prediction']['brl']
    corrected_brl = extracted_json['correction']['brl']
    image_coordinates = extracted_json['prediction']['boxes']
    
    p_brl = ""
    c_brl = ""
    i_list = []
    
    for p in predicted_brl:
        p_brl += p + "⠀"
    p_brl = p_brl[:-1]
    for c in corrected_brl:
        c_brl += c + "⠀"
    c_brl = c_brl[:-1]
        
    for i_line in image_coordinates:
        for i_box in i_line:
            i_list.append(i_box)
        i_list.append(0)
    i_list = i_list[:-1]
    
    img = Image.open('test.jpg')
    draw = ImageDraw.Draw(img)
    
    result = generate_ground_truth(p_brl, c_brl, i_list)
    for r in result:
        if r['ocr_char'] != r['correct_char']:
            print(r)
            coordinates = r['coordinates']
            if coordinates is None:
                continue
            if not isinstance(coordinates, (list, tuple)):
                coordinates = list(coordinates)
            draw.rectangle(coordinates, outline='red')
            char_to_draw = str(ord(r['ocr_char']) - 0x2800)
            char_to_draw += "->"
            char_to_draw += str(ord(r['correct_char']) - 0x2800)
            draw.text((coordinates[0], coordinates[1] - 10), char_to_draw, fill='black')
            
    img.save('result.jpg')