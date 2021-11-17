import sys
import cv2
from pycocotools.coco import COCO
import numpy as np
import skimage.io as io


class CoCoDataGenrator:
    def __init__(self,
                 coco_annotation_file,
                 img_shape=(640, 640, 3),
                 batch_size=1,
                 max_instances=100,
                 include_crowd=False,
                 include_mask=False,
                 include_keypoint=False):
        self.img_shape = img_shape
        self.batch_size = batch_size
        self.max_instances = max_instances
        self.include_crowd = include_crowd
        self.include_mask = include_mask
        self.include_keypoint = include_keypoint

        self.current_batch_index = 0
        self.total_batch_size = 0
        self.img_ids = []
        self.coco = COCO(annotation_file=coco_annotation_file)
        self.load_data()

    def load_data(self):
        # 初步过滤数据是否包含crowd
        target_img_ids = []
        for k in self.coco.imgToAnns:
            annos = self.coco.imgToAnns[k]
            print(annos)
            if annos:
                annos = list(filter(lambda x: x['iscrowd'] == self.include_crowd, annos))
                if annos:
                    target_img_ids.append(k)
        self.total_batch_size = len(target_img_ids) // self.batch_size
        self.img_ids = target_img_ids

    def next_batch(self):
        if self.current_batch_index >= self.total_batch_size:
            self.current_batch_index = 0
            self._on_epoch_end()

        batch_img_ids = self.img_ids[self.current_batch_index * self.batch_size:
                                     (self.current_batch_index + 1) * self.batch_size]
        batch_imgs = []
        batch_bboxes = []
        batch_labels = []
        batch_masks = []
        batch_keypoints = []
        for img_id in batch_img_ids:
            # {"img":, "bboxes":, "labels":, "masks":, "key_points":}
            data = self._data_generation(image_id=img_id)
            if len(np.shape(data['img'])) > 0:
                batch_imgs.append(data['img'])

                if len(data['labels']) > self.max_instances:
                    batch_bboxes.append(data['bboxes'][:self.max_instances, :])
                    batch_labels.append(data['labels'][:self.max_instances])
                else:
                    pad_num = self.max_instances - len(data['labels'])
                    batch_bboxes.append(np.pad(data['bboxes'], [(0,pad_num), (0, 0)]))
                    batch_labels.append(np.pad(data['labels'], [(0,pad_num)]))

                if self.include_mask:
                    batch_masks.append(data['masks'])

                if self.include_keypoint:
                    batch_keypoints.append(data['keypoints'])

        self.current_batch_index += 1

        if len(batch_imgs) < self.batch_size:
            return self.next_batch()

        output = {
            'imgs': np.array(batch_imgs, dtype=np.int32),
            'bboxes': np.array(batch_bboxes, dtype=np.int16),
            'labels':np.array(batch_labels,dtype=np.int8),
            'masks':np.array(batch_masks, dtype=np.int8),
            'keypoints':np.array(batch_keypoints, dtype=np.int16)
        }

        return output

    def _on_epoch_end(self):
        np.random.shuffle(self.img_ids)

    def _resize_im(self, origin_im, bboxes):
        """ 对图片/mask/box resize

        :param origin_im
        :param bboxes
        :return im_blob: [h, w, 3]
                gt_boxes: [N, [ymin, xmin, ymax, xmax]]
        """
        im_shape = np.shape(origin_im)
        im_size_max = np.max(im_shape[0:2])
        im_scale = float(self.img_shape[0]) / float(im_size_max)

        # resize原始图片
        im_resize = cv2.resize(origin_im, None, None, fx=im_scale, fy=im_scale, interpolation=cv2.INTER_LINEAR)
        im_resize_shape = np.shape(im_resize)
        im_blob = np.zeros(self.img_shape, dtype=np.float32)
        im_blob[0:im_resize_shape[0], 0:im_resize_shape[1], :] = im_resize

        # resize对应边框
        bboxes_resize = np.array(bboxes * im_scale, dtype=np.int16)

        return im_blob, bboxes_resize

    def _resize_mask(self, origin_masks):
        """ resize mask数据
        :param origin_mask:
        :return: mask_resize: [h, w, instance]
                 gt_boxes: [N, [ymin, xmin, ymax, xmax]]
        """
        mask_shape = np.shape(origin_masks)
        mask_size_max = np.max(mask_shape[0:2])
        im_scale = float(self.img_shape[0]) / float(mask_size_max)

        # resize mask/box
        gt_boxes = []
        masks_resize = []
        for m in origin_masks:
            m = np.array(m, dtype=np.float32)
            m_resize = cv2.resize(m, None, None, fx=im_scale, fy=im_scale, interpolation=cv2.INTER_LINEAR)
            m_resize = np.array(m_resize >= 0.5, dtype=np.int8)

            # 计算bdbox
            h, w = np.shape(m_resize)
            rows, cols = np.where(m_resize)
            # [xmin, ymin, xmax, ymax]
            xmin = np.min(cols) if np.min(cols) >= 0 else 0
            ymin = np.min(rows) if np.min(rows) >= 0 else 0
            xmax = np.max(cols) if np.max(cols) <= w else w
            ymax = np.max(rows) if np.max(rows) <= h else h
            bdbox = [xmin, ymin, xmax, ymax]
            gt_boxes.append(bdbox)

            mask_blob = np.zeros((self.img_shape[0], self.img_shape[1], 1), dtype=np.float32)
            mask_blob[0:h, 0:w, 0] = m_resize
            masks_resize.append(mask_blob)

        # [instance_num, [ymin, xmin, ymax, xmax]]
        gt_boxes = np.array(gt_boxes, dtype=np.int16)
        # [h, w, instance_num]
        masks_resize = np.concatenate(masks_resize, axis=-1)

        return masks_resize, gt_boxes

    def _data_generation(self, image_id):
        """ 拉取coco标记数据, 目标边框, 类别, mask
        :param image_id:
        :return:
        """

        anno_ids = self.coco.getAnnIds(imgIds=image_id, iscrowd=self.include_crowd)
        bboxes = []
        labels = []
        masks = []
        keypoints = []
        for i in anno_ids:
            # 边框, 处理成左上右下坐标
            ann = self.coco.anns[i]
            bbox = ann['bbox']
            xmin, ymin, w, h = bbox
            xmin = int(xmin)
            ymin = int(ymin)
            xmax = int(xmin + w)
            ymax = int(ymin + h)
            bboxes.append([xmin, ymin, xmax, ymax])
            # 类别ID
            label = ann['category_id']
            labels.append(label)
            # 实例分割
            if self.include_mask:
                mask = self.coco.annToMask(ann)
                masks.append(mask)
            if self.include_keypoint and ann.get('keypoints'):
                keypoint = ann['keypoints']
                # 处理成[x,y,v] 其中v=0表示没有此点,v=1表示被挡不可见,v=2表示可见
                keypoint = np.reshape(keypoint, [-1, 3])
                keypoints.append(keypoint)

        # 输出包含5个东西, 不需要则为空
        outputs = {
            "img":[],
            "labels":[],
            "bboxes":[],
            "masks":[],
            "keypoints":[]
        }

        # 处理最终数据 mask
        if self.include_mask:
            # [N, h, w]
            masks, bboxes = self._resize_mask(origin_masks=masks)
            outputs['masks'] = masks
            outputs['bboxes'] = bboxes

        # 处理最终数据 keypoint
        if self.include_keypoint:
            keypoints = np.array(keypoints, dtype=np.int8)
            outputs['keypoints'] = keypoints

        img = io.imread(self.coco.imgs[image_id]['coco_url'])
        if len(np.shape(img)) < 2:
            return outputs
        elif len(np.shape(img)) == 2:
            img = np.expand_dims(img, axis=-1)
            img = np.pad(img, [(0,0), (0,0), (0,2)])

        labels = np.array(labels, dtype=np.int8)
        bboxes = np.array(bboxes, dtype=np.int16)
        img_resize, bboxes_resize = self._resize_im(origin_im=img, bboxes=bboxes)
        outputs['img'] = img_resize
        outputs['labels'] = labels
        outputs['bboxes'] = bboxes_resize

        return outputs


if __name__ == "__main__":
    file = "./instances_val2017.json"
    coco = CoCoDataGenrator(coco_annotation_file=file,include_mask=True,include_keypoint=True)
    # data = coco.next_batch()
    # print(data)
    # data = coco.next_batch()
    # print(data)
    # for i in coco.coco.cats:
    #     print(coco.coco.cats[i])
    # class_names = list(map(lambda x:x['name'],coco.coco.cats))

    # coco = COCO(annotation_file=file)
    #
    # print("---------------------------")
    # for anno in coco.dataset['info']:
    #     print(anno, coco.dataset['info'][anno])
    #
    # print("---------------------------")
    # for anno in coco.dataset['licenses']:
    #     print(anno)
    #
    # print("---------------------------")
    # for anno in coco.dataset['categories']:
    #     print(anno)
    #
    # print("---------------------------")
    # for anno in coco.dataset['images']:
    #     print(anno)

    # print("---------------------------")
    # for anno in coco.dataset['annotations']:
    #     print(anno)
    # anno = coco.anns[900100259690]