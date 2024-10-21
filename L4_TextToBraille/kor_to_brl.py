import json
from KorToBraille.KorToBraille import KorToBraille

b = KorToBraille()
with open("test.json", "r", encoding="utf-8") as f:
    json_data = json.load(f)
text_list = json_data['correction']['text']
brl_list = []
for text in text_list:
    brl_list.append(b.korTranslate(text))
json_data["correction"]["brl"] = brl_list
with open("test.json", "w", encoding="utf-8") as f:
    json.dump(json_data, f, ensure_ascii=False, indent=4)
