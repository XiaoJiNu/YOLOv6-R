import os,math,pathlib
import numpy as np
from PIL import Image 
from yolov6.utils.events import LOGGER, load_yaml
from yolov6.layers.common import DetectBackend
from yolov6.utils.nms import non_max_suppression
from yolov6.data.data_augment import letterbox
from yolov6.core.inferer import Inferer
import torch 
from typing import List, Optional
import cv2
import matplotlib.pyplot as plt 

PATH_YOLOv6 = pathlib.Path(__file__).parent
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
CLASS_NAMES = load_yaml(str(PATH_YOLOv6/"data/coco.yaml"))['names']

def visualize_detections(
    image, boxes, classes, scores,
    min_score = 0.4, figsize=(16, 16), linewidth=2, color='lawngreen'
):
    image = np.array(image, dtype=np.uint8)
    fig = plt.figure(figsize=figsize)
    plt.axis("off")
    plt.imshow(image)
    ax = plt.gca()
    for box, name, score in zip(boxes, classes, scores):
        if score>=min_score:
            text = "{}: {:.2f}".format(name, score)
            x1, y1, x2, y2 = box
            w, h = x2 - x1, y2 - y1
            patch = plt.Rectangle(
                [x1, y1], w, h, fill=False, edgecolor=color, linewidth=linewidth
            )
            ax.add_patch(patch)
            ax.text(
                x1,
                y1,
                text,
                bbox={"facecolor": color, "alpha": 0.8},
                clip_box=ax.clipbox,
                clip_on=True,
            )
    plt.show()
    

def check_img_size(img_size, s=32, floor=0):
    def make_divisible( x, divisor):
        return math.ceil(x / divisor) * divisor
    if isinstance(img_size, int):  # integer i.e. img_size=640
        new_size = max(make_divisible(img_size, int(s)), floor)
    elif isinstance(img_size, list):  # list i.e. img_size=[640, 480]
        new_size = [max(make_divisible(x, int(s)), floor) for x in img_size]
    else:
        raise Exception(f"Unsupported type of img_size: {type(img_size)}")

    if new_size != img_size:
        print(f'WARNING: --img-size {img_size} must be multiple of max stride {s}, updating to {new_size}')
    return new_size if isinstance(img_size,list) else [new_size]*2

def precess_image(path, img_size, stride):
    '''Process image before image inference.'''
    from PIL import Image
    img_src = np.asarray(Image.open(path).convert('RGB'))
    image = letterbox(img_src, img_size, stride=stride)[0]
    # Convert
    image = image.transpose((2, 0, 1))[::-1]  # HWC to CHW, BGR to RGB
    image = torch.from_numpy(np.ascontiguousarray(image))
    image = image.float()  
    image /= 255  
    return image, img_src


class Detector(DetectBackend):
    def __init__(self,
        ckpt_path,class_names,device,
         img_size = 640, conf_thres=0.25, 
         iou_thres=0.45, max_det = 1000):
        super().__init__(ckpt_path,device)
        self.class_names = class_names
        self.model.float()   
        self.device = device
        self.img_size = check_img_size(img_size)
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.max_det = max_det 
        
    def forward(self,x:torch.Tensor,src_shape:tuple[int]):
        pred_results = super().forward(x)
        classes = None # the classes to keep
        det = non_max_suppression(pred_results, self.conf_thres, self.iou_thres,
                                  classes, agnostic=False, max_det=self.max_det)[0]
        
        det[:, :4] = Inferer.rescale(x.shape[2:], det[:, :4], src_shape).round()
        boxes = det[:,:4]
        scores = det[:,4]
        labels = det[:,5].long()
        prediction = {'boxes':boxes,'scores':scores,'labels':labels}
        return prediction
        
    
    def predict(self,img_path:str):
        img, img_src = precess_image(img_path, self.img_size, 32)
        img = img.to(self.device)
        if len(img.shape) == 3:
            img = img[None]
            
        prediction = self.forward(img,img_src.shape)
        out = {k:v.cpu().numpy() for k,v in prediction.items()}
        out['classes'] = [self.class_names[i] for i in out['labels']]
        return out 
    
    def show_predict(self,img_path:str, min_score=0.5,
                     figsize=(16, 16),color='lawngreen',linewidth=2):
        prediction = self.predict(img_path)
        boxes,scores,classes = prediction['boxes'],prediction['scores'],prediction['classes']
        visualize_detections(Image.open(img_path),
                             boxes,classes,scores,
                             min_score=min_score,color=color
                            )
        
def create_model(model_name,class_names=CLASS_NAMES,device=DEVICE,
                 img_size = 640, conf_thres=0.25, iou_thres=0.45, max_det = 1000):
    import os 
    if not os.path.exists(str(PATH_YOLOv6/'weights')):
        os.mkdir(str(PATH_YOLOv6/'weights'))
    if not os.path.exists(str(PATH_YOLOv6/'weights')+f'/{model_name}.pt'):
        torch.hub.load_state_dict_from_url(
            f"https://github.com/meituan/YOLOv6/releases/download/0.3.0/{model_name}.pt",
            str(PATH_YOLOv6/'weights'))
    return Detector(str(PATH_YOLOv6/'weights')+f'/{model_name}.pt',
                    class_names,device,img_size = img_size, conf_thres=conf_thres, 
                    iou_thres=iou_thres, max_det = max_det)


def yolov6n(class_names=CLASS_NAMES,device=DEVICE, img_size = 640, conf_thres=0.25, iou_thres=0.45, max_det = 1000):
    return create_model('yolov6n',class_names,device,img_size = img_size, conf_thres=conf_thres, 
                    iou_thres=iou_thres, max_det = max_det)


def yolov6s(class_names=CLASS_NAMES,device=DEVICE,img_size = 640, conf_thres=0.25, iou_thres=0.45, max_det = 1000):
    return create_model('yolov6s',class_names,device,img_size = img_size, conf_thres=conf_thres, 
                    iou_thres=iou_thres, max_det = max_det)

def yolov6m(class_names=CLASS_NAMES,device = DEVICE,img_size = 640, conf_thres=0.25, iou_thres=0.45, max_det = 1000):
    return create_model('yolov6m',class_names,device,img_size = img_size, conf_thres=conf_thres, 
                    iou_thres=iou_thres, max_det = max_det)


def yolov6l(class_names=CLASS_NAMES,device = DEVICE,img_size = 640, conf_thres=0.25, iou_thres=0.45, max_det = 1000):
    return create_model('yolov6l',class_names,device,img_size = img_size, conf_thres=conf_thres, 
                    iou_thres=iou_thres, max_det = max_det)

def yolov6x(class_names=CLASS_NAMES,device=DEVICE,img_size = 640, conf_thres=0.25, iou_thres=0.45, max_det = 1000):
    return create_model('yolov6x',class_names,device,img_size = img_size, conf_thres=conf_thres, 
                    iou_thres=iou_thres, max_det = max_det)


def custom(ckpt_path,class_names,device=DEVICE,img_size = 640, conf_thres=0.25, iou_thres=0.45, max_det = 1000):
    return Detector(ckpt_path,class_names,device,img_size = img_size, conf_thres=conf_thres, 
                    iou_thres=iou_thres, max_det = max_det)