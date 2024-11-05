#!/usr/bin/env python
# coding: utf-8
import enum
try:
    import fitz
except:
    pass
import os
import json
import glob
import sys
import OCR.local_config as local_config
sys.path.append(local_config.global_3rd_party)
from os.path import join
from ovotools.params import AttrDict
import numpy as np
from collections import OrderedDict
import torch
import timeit
import copy
from pathlib import Path
import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont
from pathlib import Path
import zipfile
import data_utils.data as data
import braille_utils.letters as letters
import braille_utils.label_tools as lt
import model.create_model_retinanet as create_model_retinanet
import pytorch_retinanet as pytorch_retinanet
import pytorch_retinanet.encoder
import braille_utils.postprocess as postprocess
import model.refine_json as refine_json
import model.test as test

# import uuid
import datetime
import pytz
import csv

VALID_IMAGE_EXTENTIONS = tuple('.jpg,.jpe,.jpeg,.png,.gif,.svg,.bmp,.tiff,.tif,.jfif'.split(','))
inference_width = 1024
model_weights = 'model.t7'
params_fn = join(local_config.data_path, 'weights', 'param.txt')
model_weights_fn = join(local_config.data_path, 'weights', model_weights)
device = 'cuda:0'
#device = 'cpu'
cls_thresh = 0.3
nms_thresh = 0.02
REFINE_COEFFS = [0.083, 0.092, -0.083, -0.013]  # Коэффициенты (в единицах h символа) для эмпирической коррекции
                        # получившихся размеров, чтобы исправить неточность результатов для последующей разметки

class OrientationAttempts(enum.IntEnum):
    NONE = 0
    ROT180 = 1
    INV = 2
    INV_ROT180 = 3
    ROT90 = 4
    ROT270 = 5
    INV_ROT90 = 6
    INV_ROT270 = 7


class BraileInferenceImpl(torch.nn.Module):
    def __init__(self, params, model, device, label_is_valid, verbose=0):
        super(BraileInferenceImpl, self).__init__()
        self.verbose = verbose
        self.device = device
        if isinstance(model, torch.nn.Module):
            self.model_weights_fn = ""
            self.model = model
        else:
            self.model_weights_fn = model
            self.model, _, _ = create_model_retinanet.create_model_retinanet(params, device=device)
            self.model = self.model.to(device)
            self.model.load_state_dict(torch.load(self.model_weights_fn, map_location = 'cpu'))
        self.model.eval()
        #self.model = torch.jit.script(self.model)

        self.encoder = pytorch_retinanet.encoder.DataEncoder(**params.model_params.encoder_params)
        #self.encoder = encoder
        self.valid_mask = torch.tensor(label_is_valid).long()
        self.cls_thresh = cls_thresh
        self.nms_thresh = nms_thresh
        self.num_classes = [] if not params.data.get('class_as_6pt', False) else [1]*6

    def calc_letter_statistics(self, cls_preds, cls_thresh, orientation_attempts):
        # type: (List[Tensor], float)->Tuple[int, Tuple[Tensor, Tensor, Tensor]]
        device = cls_preds[min(orientation_attempts)].device
        stats = [torch.zeros((1, 64,), device=device)]*8
        for i, cls_pred in enumerate(cls_preds):
            if i in orientation_attempts:
                scores = cls_pred.sigmoid()
                scores[scores<cls_thresh] = torch.tensor(0.).to(scores.device)
                stat = scores.sum(1)
                assert list(stat.shape) == [1, 64]
                stats[i] = stat
        stat = torch.cat(stats, dim=0)
        valid_mask = self.valid_mask.to(stat.device)
        sum_valid = (stat*valid_mask).sum(1)
        sum_invalid = (stat*(1-valid_mask)).sum(1)
        err_score = (sum_invalid+1)/(sum_valid+1)
        best_idx = torch.argmin(err_score/(sum_valid+1)) # эвристика так себе придуманная
        return best_idx.item(), (err_score, sum_valid, sum_invalid)

    def forward(self, input_tensor, input_tensor_rotated, find_orientation, process_2_sides):
        # type: (Tensor, Tensor, int)->Tuple[Tensor,Tensor,Tensor,int, Tuple[Tensor, Tensor, Tensor]]
        t = timeit.default_timer()
        orientation_attempts = [OrientationAttempts.NONE]
        if find_orientation:
            orientation_attempts += [OrientationAttempts.ROT180, OrientationAttempts.ROT90, OrientationAttempts.ROT270]
        if process_2_sides:
            orientation_attempts += [OrientationAttempts.INV]
            if find_orientation:
                orientation_attempts += [OrientationAttempts.INV_ROT180, OrientationAttempts.INV_ROT90, OrientationAttempts.INV_ROT270]
        if len(self.num_classes) > 1:
            assert not find_orientation and not process_2_sides
        input_data = [None]*8
        input_data[OrientationAttempts.NONE]= input_tensor.unsqueeze(0)
        if find_orientation:
            input_data[OrientationAttempts.ROT180] = torch.flip(input_data[OrientationAttempts.NONE], [2,3])
            input_data[OrientationAttempts.ROT90] = input_tensor_rotated.unsqueeze(0)
            input_data[OrientationAttempts.ROT270] = torch.flip(input_data[OrientationAttempts.ROT90], [2, 3])
        if process_2_sides:
            input_data[OrientationAttempts.INV] = torch.flip(-input_data[OrientationAttempts.NONE], [3])
            if find_orientation:
                input_data[OrientationAttempts.INV_ROT180] = torch.flip(-input_data[OrientationAttempts.ROT180], [3])
                input_data[OrientationAttempts.INV_ROT90] = torch.flip(-input_data[OrientationAttempts.ROT90], [3])
                input_data[OrientationAttempts.INV_ROT270] = torch.flip(-input_data[OrientationAttempts.ROT270], [3])
        loc_preds: List[Tensor] = [torch.tensor(0)]*8
        cls_preds: List[Tensor] = [torch.tensor(0)]*8
        if self.verbose >= 2:
            print("        forward.prepare", timeit.default_timer() - t)
            t = timeit.default_timer()
        for i, input_data_i in enumerate(input_data):
            if i in orientation_attempts:
                loc_pred, cls_pred = self.model(input_data_i)
                loc_preds[i] = loc_pred
                cls_preds[i] = cls_pred
        if self.verbose >= 2:
            print("        forward.model", timeit.default_timer() - t)
            t = timeit.default_timer()
        if find_orientation:
            best_idx, err_score = self.calc_letter_statistics(cls_preds, self.cls_thresh, orientation_attempts)
        else:
            best_idx, err_score = OrientationAttempts.NONE, (torch.tensor([0.]),torch.tensor([0.]),torch.tensor([0.]))
        if self.verbose >= 2 and self.device != 'cpu':
            torch.cuda.synchronize(self.device)

        if best_idx in [OrientationAttempts.INV, OrientationAttempts.INV_ROT180, OrientationAttempts.INV_ROT90, OrientationAttempts.INV_ROT270]:
            best_idx -= 2
        if self.verbose >= 2:
            print("        forward.calc_letter_statistics", timeit.default_timer() - t)
            t = timeit.default_timer()
        h,w = input_data[best_idx].shape[2:]
        boxes, labels, scores = self.encoder.decode(loc_preds[best_idx][0].cpu().data,
                                                    cls_preds[best_idx][0].cpu().data, (w,h),
                                                    cls_thresh = self.cls_thresh, nms_thresh = self.nms_thresh,
                                                    num_classes=self.num_classes)
        if len(self.num_classes) > 1:
            labels = torch.tensor([lt.label010_to_int([str(s.item()+1) for s in lbl101]) for lbl101 in labels])
        if process_2_sides:
            boxes2, labels2, scores2 = self.encoder.decode(loc_preds[best_idx+2][0].cpu().data,
                                                           cls_preds[best_idx+2][0].cpu().data, (w, h),
                                                           cls_thresh=self.cls_thresh, nms_thresh=self.nms_thresh,
                                                           num_classes=self.num_classes)
        else:
            boxes2, labels2, scores2 = None, None, None
        if self.verbose >= 2:
            print("        forward.decode", timeit.default_timer() - t)
            t = timeit.default_timer()
        return boxes, labels, scores, best_idx, err_score, boxes2, labels2, scores2


class BrailleInference:

    DRAW_NONE = 0
    DRAW_ORIGINAL = 1
    DRAW_REFINED = 2
    DRAW_BOTH = DRAW_ORIGINAL | DRAW_REFINED  # 3
    DRAW_FULL_CHARS = 4

    def __init__(self, params_fn=params_fn, model_weights_fn=model_weights_fn, create_script = None,
                 verbose=1, inference_width=inference_width, device=device):
        self.verbose = verbose
        if not torch.cuda.is_available() and device != 'cpu':
            print('CUDA not availabel. CPU is used')
            device = 'cpu'

        params = AttrDict.load(params_fn, verbose=verbose)
        params.data.net_hw = (inference_width,inference_width,) #(512,768) ###### (1024,1536) #
        params.data.batch_size = 1 #######
        params.augmentation = AttrDict(
            img_width_range=(inference_width, inference_width),
            stretch_limit = 0.0,
            rotate_limit=0,
        )
        self.preprocessor = data.ImagePreprocessor(params, mode = 'inference')

        if isinstance(model_weights_fn, torch.nn.Module):
            self.impl = BraileInferenceImpl(params, model_weights_fn, device, lt.label_is_valid, verbose=verbose)
        else:
            model_script_fn = model_weights_fn + '.pth'
            if create_script != False:
                self.impl = BraileInferenceImpl(params, model_weights_fn, device, lt.label_is_valid, verbose=verbose)
                if create_script is not None:
                    self.impl = torch.jit.script(self.impl)
                if isinstance(self.impl, torch.jit.ScriptModule):
                    torch.jit.save(self.impl, model_script_fn)
                    if verbose >= 1:
                        print("Model loaded and saved to " + model_script_fn)
                else:
                    if verbose >= 1:
                        print("Model loaded")
            else:
                self.impl = torch.jit.load(model_script_fn)
                if verbose >= 1:
                    print("Model pth loaded")
        self.impl.to(device)
        
        # self.uuid_int = uuid.uuid1().int
        self.result = None
        
    # def get_uuid(self):
    #     return self.uuid_int
    
    def get_result(self):
        return self.result

    def load_pdf(self, img_fn):
        try:
            pdf_file = fitz.open(img_fn)
            pg = pdf_file.loadPage(0)
            pdf = pg.getPixmap()
            cspace = pdf.colorspace
            if cspace is None:
                mode = "L"
            elif cspace.n == 1:
                mode = "L" if pdf.alpha == 0 else "LA"
            elif cspace.n == 3:
                mode = "RGB" if pdf.alpha == 0 else "RGBA"
            else:
                mode = "CMYK"
            img = PIL.Image.frombytes(mode, (pdf.width, pdf.height), pdf.samples)
            return img
        except Exception as exc:
            return None


    def run(self, img, lang, draw_refined, find_orientation, process_2_sides, align_results, repeat_on_aligned=True, gt_rects=[]):
        """
        :param img: can be 1) PIL.Image 2) filename to image (.jpg etc.) or .pdf file
        """
        
        results_dict = self.run_impl(img, lang, draw_refined, find_orientation,
                                        process_2_sides=process_2_sides, align=align_results, draw=True, gt_rects=gt_rects)
        return results_dict

		
    def refine_lines(self, lines):
        """
        GVNC. Эмпирическая коррекция получившихся размеров чтобы исправить неточность результатов для последующей разметки
        :param boxes:
        :return:
        """
        for ln in lines:
            for ch in ln.chars:
                h = ch.refined_box[3] - ch.refined_box[1]
                coefs = np.array(REFINE_COEFFS)
                deltas = h * coefs
                ch.refined_box = (np.array(ch.refined_box) + deltas).tolist()

    def run_impl(self, img, lang, draw_refined, find_orientation, process_2_sides, align, draw, gt_rects=[]):
        t = timeit.default_timer()
        np_img = np.asarray(img)
        
        if (len(np_img.shape) > 2 and np_img.shape[2] < 3):  # grayscale -> reduce dim
            np_img = np_img[:,:,0]
        aug_img, aug_gt_rects = self.preprocessor.preprocess_and_augment(np_img, gt_rects)
        aug_img = data.unify_shape(aug_img)
        input_tensor = self.preprocessor.to_normalized_tensor(aug_img, device=self.impl.device)
        input_tensor_rotated = torch.tensor(0).to(self.impl.device)
        
        aug_img_rot = None
        if find_orientation:
            np_img_rot = np.rot90(np_img, 1, (0,1))
            aug_img_rot = self.preprocessor.preprocess_and_augment(np_img_rot)[0]
            aug_img_rot = data.unify_shape(aug_img_rot)
            input_tensor_rotated = self.preprocessor.to_normalized_tensor(aug_img_rot, device=self.impl.device)
        
        with torch.no_grad():
            boxes, labels, scores, best_idx, err_score, boxes2, labels2, scores2 = self.impl(
                input_tensor, input_tensor_rotated, find_orientation=find_orientation, process_2_sides=process_2_sides)
        
        #boxes = self.refine_boxes(boxes)
        boxes = boxes.tolist()
        labels = labels.tolist()
        scores = scores.tolist()
        lines = postprocess.boxes_to_lines(boxes, labels, lang = lang)
        self.refine_lines(lines)

        aug_img = PIL.Image.fromarray(aug_img if best_idx < OrientationAttempts.ROT90 else aug_img_rot)
        if best_idx in (OrientationAttempts.ROT180, OrientationAttempts.ROT270):
            aug_img = aug_img.transpose(PIL.Image.ROTATE_180)

        if align and not process_2_sides:
            hom = postprocess.find_transformation(lines, (aug_img.width, aug_img.height))
            if hom is not None:
                aug_img = postprocess.transform_image(aug_img, hom)
                boxes = postprocess.transform_rects(boxes, hom)
                lines = postprocess.boxes_to_lines(boxes, labels, lang=lang)
                self.refine_lines(lines)
                aug_gt_rects = postprocess.transform_rects(aug_gt_rects, hom)
        else:
            hom = None
            
        results_dict = {
            'image': aug_img,
            'best_idx': best_idx,
            'err_scores': list([ten.cpu().data.tolist() for ten in err_score]),
            'gt_rects': aug_gt_rects,
            'homography': hom.tolist() if hom is not None else hom,
        }

        results_dict.update(self.draw_results(aug_img, boxes, lines, labels, scores, False, draw_refined))
        
        return results_dict

    def draw_results(self, aug_img, boxes, lines, labels, scores, reverse_page, draw_refined):
        suff = '.rev' if reverse_page else ''
        aug_img = copy.deepcopy(aug_img)
        draw = PIL.ImageDraw.Draw(aug_img)
        for ln in lines:
            for ch in ln.chars:
                draw.rectangle(list(ch.refined_box), outline='green')
        return {
            'labeled_image' + suff: aug_img,
            'lines' + suff: lines,
            'text' + suff: "",
            'braille' + suff: [],
            'dict' + suff: self.to_dict(aug_img, lines, draw_refined),
            'boxes' + suff: boxes,
            'labels' + suff: labels,
            'scores' + suff: scores,
        }



    def to_dict(self, img, lines, draw_refined = DRAW_NONE):
        '''
        generates dict for LabelMe json format
        :param img:
        :param lines:
        :return: dict
        '''
        shapes = []
        for ln in lines:
            for ch in ln.chars:
                ch_box = ch.refined_box if (draw_refined & self.DRAW_BOTH) != self.DRAW_ORIGINAL else ch.original_box
                shape = {
                    "label": ch.label,
                    "points": [[ch_box[0], ch_box[1]],
                               [ch_box[2], ch_box[3]]],
                    "shape_type": "rectangle",
                    "line_color": None,
                    "fill_color": None,
                }
                shapes.append(shape)
        res = {"shapes": shapes,
               "imageHeight": img.height, "imageWidth": img.width, "imagePath": None, "imageData": None,
               "lineColor": None, "fillColor": None,
               }
        return res

    def save_results(self, result_dict, reverse_page, image, image_name):
        # suff = ".rev" if reverse_page else ""
        
        # data_dir = Path(results_dir) / "data"
        
        # 각 디렉토리 경로 설정
        # img_dir = Path(data_dir) / "images"
        # json_dir = Path(data_dir) / "annotations"
        
        # 디렉토리가 존재하지 않으면 생성
        # data_dir.mkdir(parents=True, exist_ok=True)
        # img_dir.mkdir(parents=True, exist_ok=True)
        # json_dir.mkdir(parents=True, exist_ok=True)
        
        # 경로 설정
        # uuid_str = str(self.uuid_int)
        # marked_image_path = img_dir / (uuid_str + ".jpg")
        # json_path = json_dir / (uuid_str + ".json")
        # marked_image_path = img_dir / image_name
        # json_path = json_dir / image_name.replace(".jpg", ".json")
        
        # 이미지 저장
        # result_dict["labeled_image" + suff].save(marked_image_path)
        
        # JSON 파일 저장
        boxes = []
        labels = []
        
        for line in result_dict["lines"]:
            boxes.append([ch.refined_box for ch in line.chars])
            labels.append([ch.label for ch in line.chars])
        
        # 한국 시간대 설정
        # kst = pytz.timezone('Asia/Seoul')
        
        # 현재 한국 시간 가져오기
        # current_time_kst = datetime.datetime.now(kst)
        
        # print("Height: ", result_dict["dict" + suff]["imageHeight"])
        
        # json_result = {
            # "id": self.uuid_int,
            # "image_path": str(marked_image_path),
            # "date": current_time_kst.strftime("%Y-%m-%d %H:%M:%S"),
            # "imageWidth": result_dict["dict" + suff]["imageWidth"],
            # "imageHeight": result_dict["dict" + suff]["imageHeight"],
            # "prediction": {
            #     "boxes": None,
            #     "labels": None,
            #     "brl": None,
            #     "text": None
            # },
            # "correction": {
            #     "boxes": None,
            #     "labels": None,
            #     "brl": None,
            #     "text": None
            # },
        # }
        
        # json_result = refine_json.main(json_result, boxes, labels)
        # json_result = refine_json.main(boxes, labels, image)
        return refine_json.main(boxes, labels, image, image_name)
        
        # with open(json_path, "w", encoding='utf-8') as f:
        #     json.dump(json_result, f, indent=4, ensure_ascii=False)
        
        # return json_result
    
    def run_and_save(self, image_file, results_dir, target_stem, lang, extra_info, draw_refined,
                     remove_labeled_from_filename, find_orientation, align_results, process_2_sides, repeat_on_aligned,
                     save_development_info=True):
        """
        :param img: can be 1) PIL.Image 2) filename to image (.jpg etc.) or .pdf file
        :param target_stem: starting part of result files names (i.e. <target_stem>.protocol.txt etc.) Is used when
            img is image, not filename. When target_stem is None, it is taken from img stem.
        """
        t = timeit.default_timer()
        image = PIL.Image.open(image_file)
        image_name = image_file.filename
        
        result_dict = self.run(image, lang=lang, draw_refined=draw_refined,
                               find_orientation=find_orientation,
                               process_2_sides=process_2_sides, align_results=align_results, repeat_on_aligned=repeat_on_aligned)
        if result_dict is None:
            return None

        return self.save_results(result_dict, False, image, image_name)
        # os.makedirs(results_dir, exist_ok=True)
        
        # self.result = self.save_results(result_dict, False, image, image_name)
        
        # return self.result

    def process_dir_and_save(self, img_filename_mask, results_dir, lang, extra_info, draw_refined,
                             remove_labeled_from_filename, find_orientation, process_2_sides, align_results,
                             repeat_on_aligned, save_development_info=True):
        if os.path.isfile(img_filename_mask) and os.path.splitext(img_filename_mask)[1] == '.txt':
            list_file = os.path.join(local_config.data_path, img_filename_mask)
            data_dir = os.path.dirname(list_file)
            with open(list_file, 'r') as f:
                files = f.readlines()
            img_files = [os.path.join(data_dir, fn[:-1] if fn[-1] == '\n' else fn) for fn in files]
            img_folders = [os.path.split(fn)[0] for fn in files]
        elif os.path.isfile(img_filename_mask):
            img_files = [img_filename_mask]
            img_folders = [""]
        else:
            root_dir, mask = img_filename_mask.split('*', 1)
            mask = '*' + mask
            img_files = list(Path(root_dir).glob(mask))
            img_folders = [os.path.split(fn)[0].replace(str(Path(root_dir)), '')[1:] for fn in img_files]
        result_list = list()
        for img_file, img_folder in zip(img_files, img_folders):
            print('processing '+str(img_file))
            ith_result = self.run_and_save(
                img_file, os.path.join(results_dir, img_folder), target_stem=None,
                lang=lang, extra_info=extra_info,
                draw_refined=draw_refined,
			    remove_labeled_from_filename=remove_labeled_from_filename,
                find_orientation=find_orientation,
                process_2_sides=process_2_sides,
                align_results=align_results,
                repeat_on_aligned=repeat_on_aligned,
                save_development_info=save_development_info)
            if ith_result is None:
                print('Error processing file: '+ str(img_file))
                continue
            result_list += ith_result
        return result_list

    def process_archive_and_save(self, arch_path, results_dir, lang, extra_info, draw_refined,
                    remove_labeled_from_filename, find_orientation, align_results, process_2_sides, repeat_on_aligned,
                    save_development_info=True):
        arch_name = Path(arch_path).name
        result_list = list()
        with zipfile.ZipFile(arch_path, 'r') as archive:
            for entry in archive.infolist():
                with archive.open(entry) as file:
                    if not Path(file.name).suffix.lower() in VALID_IMAGE_EXTENTIONS:
                        continue
                    try:
                        img = PIL.Image.open(file)
                    except:
                        print('Error processing file: ' + str(entry.filename) + ' in ' + str(arch_path))
                        continue
                    ith_result = self.run_and_save(
                        img, results_dir, target_stem=arch_name + '.'+ Path(entry.filename).stem,
                        lang=lang, extra_info=extra_info,
                        draw_refined=draw_refined,
                        remove_labeled_from_filename=remove_labeled_from_filename,
                        find_orientation=find_orientation,
                        process_2_sides=process_2_sides,
                        align_results=align_results,
                        repeat_on_aligned=repeat_on_aligned,
                        save_development_info=save_development_info)
                    if ith_result is None:
                        # print('Error processing file: ' + str(img_file))
                        continue
                    result_list += ith_result
        return result_list


if __name__ == '__main__':

    #img_filename_mask = r'D:\Programming.Data\Braille\web_uploaded\data\raw\*.*'
    #img_filename_mask = r'D:\Programming.Data\Braille\ASI\Braile Photos and Scans\Turlom_Copybook_3-18\Turlom_Copybook10\Photo_Turlom_C10\Photo_Turlom_C10_8.jpg'
    #img_filename_mask = r'D:\Programming.Data\Braille\ASI\Student_Book\56-61\IMG_20191109_195953.jpg'
    img_filename_mask = r'D:\Programming.Data\Braille\ASI\Braile Photos and Scans\**\*.*'

    #results_dir =       r'D:\Programming.Data\Braille\web_uploaded\re-processed200823'
    results_dir =       r'D:\Programming.Data\Braille\ASI_results_NEW_EN\Braile Photos and Scans'
    #results_dir =       r'D:\Programming.Data\Braille\Temp\New'

    lang = 'RU'
    remove_labeled_from_filename = False
    find_orientation = True
    process_2_sides = False
    repeat_on_aligned = False
    verbose = 0
    draw_redined = BrailleInference.DRAW_REFINED

    recognizer = BrailleInference(verbose=verbose)
    recognizer.process_dir_and_save(img_filename_mask, results_dir, lang=lang, extra_info=None, draw_refined=draw_redined,
                                    remove_labeled_from_filename=remove_labeled_from_filename,
                                    find_orientation=find_orientation,
                                    process_2_sides=process_2_sides,
                                    align_results=True,
                                    repeat_on_aligned=repeat_on_aligned)

    #recognizer.process_dir_and_save(r'D:\Programming.Data\Braille\My\raw\ang_redmi\*.jpg', r'D:\Programming.Data\Braille\tmp\flip_inv\ang_redmi', lang = 'RU')