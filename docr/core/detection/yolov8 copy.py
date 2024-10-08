# import sys
# sys.path.append('/home/zyj/project/MOP/mop/dla')

import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from docr.config import __model_path__
from docr.utils import visual


class YOLOv8:
    def __init__(self, model_path, labels, **params):

        self.enable_cpu_mem_arena = params.get("enable_cpu_mem_arena", False)
        self.execution_mode = params.get(
            "execution_mode", ort.ExecutionMode.ORT_SEQUENTIAL
        )
        self.intra_op_num_threads = params.get("intra_op_num_threads", 2)
        self.inter_op_num_threads = params.get("inter_op_num_threads", 2)

        self.conf_thres = params.get("conf_thres", 0.7)
        self.iou_thres = params.get("iou_thres", 0.5)

        self.class_names = labels

        # Initialize model
        model_path = Path(__model_path__) / model_path
        self.load_model(model_path)

    def __call__(self, image):
        start = time.perf_counter()
        input_tensor = self.pre_process(image)

        # Perform inference on the image
        outputs = self.inference(input_tensor)

        self.boxes, self.scores, self.class_ids = self.post_process(outputs)
        print(f"Inference time: {(time.perf_counter() - start)*1000:.2f} ms")
        return self.boxes, self.scores, self.class_ids

    def load_model(self, model_path):
        assert Path(model_path).exists(), f"Model path {model_path} does not exist."
        options = ort.SessionOptions()
        options.enable_cpu_mem_arena = self.enable_cpu_mem_arena
        options.execution_mode = self.execution_mode
        options.intra_op_num_threads = self.intra_op_num_threads
        options.inter_op_num_threads = self.inter_op_num_threads

        self.session = ort.InferenceSession(
            model_path, options=options, providers=ort.get_available_providers()
        )
        # Get model info
        self.get_model_input()
        self.get_model_output()

    def pre_process(self, image: np.array):
        self.img_height, self.img_width = image.shape[:2]

        input_img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Resize input image
        input_img = cv2.resize(input_img, (self.input_width, self.input_height))

        # Scale input pixel values to 0 to 1
        input_img = input_img / 255.0
        input_img = input_img.transpose(2, 0, 1)
        input_tensor = input_img[np.newaxis, :, :, :].astype(np.float32)

        return input_tensor

    def inference(self, input_tensor):
        # start = time.perf_counter()
        outputs = self.session.run(
            self.output_names, {self.input_names[0]: input_tensor}
        )

        # print(f"Inference time: {(time.perf_counter() - start)*1000:.2f} ms")
        return outputs

    def post_process(self, output):
        predictions = np.squeeze(output[0]).T

        # Filter out object confidence scores below thres
        scores = np.max(predictions[:, 4:], axis=1)
        predictions = predictions[scores > self.conf_thres, :]
        scores = scores[scores > self.conf_thres]

        if len(scores) == 0:
            return [], [], []

        # Get the class with the highest confidence
        class_ids = np.argmax(predictions[:, 4:], axis=1)

        # Get bounding boxes for each object
        boxes = self.extract_boxes(predictions)

        # Apply non-maxima suppression to suppress weak, overlapping bounding boxes
        # indices = nms(boxes, scores, self.iou_thres)
        indices = multiclass_nms(boxes, scores, class_ids, self.iou_thres)

        return boxes[indices], scores[indices], class_ids[indices]

    def extract_boxes(self, predictions):
        # Extract boxes from predictions
        boxes = predictions[:, :4]

        # Scale boxes to original image dimensions
        boxes = self.rescale_boxes(boxes)

        # Convert boxes to xyxy format
        boxes = xywh2xyxy(boxes)

        return boxes

    # 框坐标还原
    def rescale_boxes(self, boxes):

        # Rescale boxes to original image dimensions
        input_shape = np.array(
            [self.input_width, self.input_height, self.input_width, self.input_height]
        )
        boxes = np.divide(boxes, input_shape, dtype=np.float32)
        boxes *= np.array(
            [self.img_width, self.img_height, self.img_width, self.img_height]
        )
        return boxes

    def draw_detections(self, image, draw_scores=True, mask_alpha=0.4):
        return visual(
            image,
            self.boxes,
            self.class_ids,
            class_names=self.class_names,
            scores=self.scores,
            mask_alpha=mask_alpha,
        )

    def get_model_input(self):
        model_inputs = self.session.get_inputs()
        self.input_names = [model_inputs[i].name for i in range(len(model_inputs))]

        self.input_shape = model_inputs[0].shape
        self.input_height = self.input_shape[2]
        self.input_width = self.input_shape[3]

    def get_model_output(self):
        model_outputs = self.session.get_outputs()
        self.output_names = [model_outputs[i].name for i in range(len(model_outputs))]


def xywh2xyxy(x):
    # Convert bounding box (x, y, w, h) to bounding box (x1, y1, x2, y2)
    y = np.copy(x)
    y[..., 0] = x[..., 0] - x[..., 2] / 2
    y[..., 1] = x[..., 1] - x[..., 3] / 2
    y[..., 2] = x[..., 0] + x[..., 2] / 2
    y[..., 3] = x[..., 1] + x[..., 3] / 2
    return y


def nms(boxes, scores, iou_thres):
    # Sort by score
    sorted_indices = np.argsort(scores)[::-1]

    keep_boxes = []
    while sorted_indices.size > 0:
        # Pick the last box
        box_id = sorted_indices[0]
        keep_boxes.append(box_id)

        # Compute IoU of the picked box with the rest
        ious = compute_iou(boxes[box_id, :], boxes[sorted_indices[1:], :])

        # Remove boxes with IoU over the threshold
        keep_indices = np.where(ious < iou_thres)[0]

        # print(keep_indices.shape, sorted_indices.shape)
        sorted_indices = sorted_indices[keep_indices + 1]

    return keep_boxes


def multiclass_nms(boxes, scores, class_ids, iou_thres):

    unique_class_ids = np.unique(class_ids)

    keep_boxes = []
    for class_id in unique_class_ids:
        class_indices = np.where(class_ids == class_id)[0]
        class_boxes = boxes[class_indices, :]
        class_scores = scores[class_indices]

        class_keep_boxes = nms(class_boxes, class_scores, iou_thres)
        keep_boxes.extend(class_indices[class_keep_boxes])

    return keep_boxes


def compute_iou(box, boxes):
    # Compute xmin, ymin, xmax, ymax for both boxes
    xmin = np.maximum(box[0], boxes[:, 0])
    ymin = np.maximum(box[1], boxes[:, 1])
    xmax = np.minimum(box[2], boxes[:, 2])
    ymax = np.minimum(box[3], boxes[:, 3])

    # Compute intersection area
    intersection_area = np.maximum(0, xmax - xmin) * np.maximum(0, ymax - ymin)

    # Compute union area
    box_area = (box[2] - box[0]) * (box[3] - box[1])
    boxes_area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    union_area = box_area + boxes_area - intersection_area

    # Compute IoU
    iou = intersection_area / union_area

    return iou


if __name__ == "__main__":
    # from imread_from_url import imread_from_url

    model_path = "/home/zyj/project/MOP/docr/core/detection/yolov8n_cdla.onnx"

    # Initialize YOLOv8 object detector
    yolov8_detector = YOLOv8(model_path, conf_thres=0.3, iou_thres=0.5)

    # img_url = "https://live.staticflickr.com/13/19041780_d6fd803de0_3k.jpg"
    # img = imread_from_url(img_url)
    img = cv2.imread("/home/zyj/project/MOP/test_img/page_p6.png")

    # Detect Objects
    yolov8_detector(img)

    # Draw detections
    combined_img = yolov8_detector.draw_detections(img)
    cv2.imwrite("output.jpg", combined_img)
    # cv2.namedWindow("Output", cv2.WINDOW_NORMAL)
    # cv2.imshow("Output", combined_img)
    # cv2.waitKey(0)
