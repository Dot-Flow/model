import numpy as np
from PIL import Image, ImageDraw

def calc_avg_margin(box_lines):
    # 박스간 간격 계산
    dist_list = []
    for box_line in box_lines:
        for i in range(1, len(box_line)):
            dist_list.append(box_line[i][0] - box_line[i-1][2])
    
    # 이상치 기준 설정
    q1 = np.percentile(dist_list, 25)    
    q3 = np.percentile(dist_list, 75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    # 이상치 제거 후 margin 평균 계산
    return np.mean([dist for dist in dist_list if lower_bound <= dist <= upper_bound])

def calc_avg_box_x(box_lines):
    avg_box_x = 0
    for box_line in box_lines:
        for box in box_line:
            avg_box_x += box[2] - box[0]
    return avg_box_x / sum([len(box_line) for box_line in box_lines])

def make_new_boxes(spaces, pre_box, cur_box, avg_margin, avg_box_x):
    # 기울기 계산
    if cur_box[0] - pre_box[2] == 0:
        slope = 0
    else:
        slope = (cur_box[1] - pre_box[1]) / (cur_box[0] - pre_box[2])
    
    # 공백 생성
    new_boxes = [
        pre_box[2] + avg_margin,
        pre_box[1] + slope * avg_margin,
        pre_box[2] + avg_margin + avg_box_x,
        pre_box[3] + slope * (avg_margin + avg_box_x)
    ]
    for _ in range(spaces-1):
        new_boxes.append([
            new_boxes[-1][2] + avg_margin,
            new_boxes[-1][1] + slope * avg_margin,
            new_boxes[-1][2] + avg_margin + avg_box_x,
            new_boxes[-1][3] + slope * (avg_margin + avg_box_x)
        ])
    return new_boxes

def make_spaces_by_lines(box_lines, label_lines, image_path):
    avg_box_x = calc_avg_box_x(box_lines)
    avg_margin = calc_avg_margin(box_lines)
    avg_width = avg_box_x + avg_margin
    
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    
    # 공백 찾기
    refined_box_lines = []
    refined_label_lines = []
    for box_line, label_line in zip(box_lines, label_lines):
        refined_box_line = []
        refined_label_line = []
        for i, box, label in zip(range(len(box_line)), box_line, label_line):
            if i == 0:
                refined_box_line.append(box)
                refined_label_line.append(label)
                continue
            
            pre_box = box_line[i-1]
            cur_box = box_line[i]
            spaces = int((cur_box[0] - pre_box[2]) / (avg_width * 0.9))
            
            if spaces > 0:
                new_boxes = make_new_boxes(spaces, pre_box, cur_box, avg_margin, avg_box_x)
                draw.rectangle(list(new_boxes), outline='blue')
                refined_box_line.append(new_boxes)
                for _ in range(spaces):
                    refined_label_line.append(0)
            
            refined_box_line.append(cur_box)
            refined_label_line.append(label)    
        
        refined_box_lines.append(refined_box_line)
        refined_label_lines.append(refined_label_line)
    image.save(image_path)
    return refined_box_lines, refined_label_lines

def labels_to_brl(label_lines):
    brl_lines = []
    for label_line in label_lines:
        brl = ""
        for label in label_line:
            brl += chr(label + 0x2800)
        brl_lines.append(brl)
    return brl_lines
    
    
def main(json_result, boxes, labels):
    image_path = json_result['image_path']
    refined_boxes, refined_labels = make_spaces_by_lines(boxes, labels, image_path)
    brl_lines = labels_to_brl(refined_labels)
    
    json_result['prediction']['boxes'] = refined_boxes
    json_result['prediction']['labels'] = refined_labels
    json_result['prediction']['brl'] = brl_lines
    
    
    return json_result
